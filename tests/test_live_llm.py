"""Live VLM integration tests + offline mock-based regression tests.

This file mixes two tiers of coverage:

- ``@pytest.mark.live_llm``: requires a real OpenAI-compatible VLM
  endpoint (e.g. LM Studio on ``localhost:1234/v1``). Skipped in CI
  by default; run manually via ``uv run pytest -m live_llm`` against
  a local LM Studio instance.

- Default tier: mock-based regression tests that patch
  ``httpx.AsyncClient.post`` to return canned VLM responses. These
  run in the fast tier and catch prompt-formatting / response-parsing
  regressions that the live test alone would miss (the live test
  asserts only that the response is non-empty; it does not pin the
  exact prompt construction or the response shape contract).

F4.3 audit fix (HIGH): the live_llm marker is never run in CI
because the only test that carried it required a real endpoint.
The default-tier mock tests below let the fast gate cover the
prompt/parsing contract that the live test would only catch by
accident on a manual run.
"""

from __future__ import annotations

import base64
import io
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from PIL import Image, ImageDraw

from omniscribe.core.ocr.processor import OCRProcessor
from omniscribe.core.ocr.prompts import (
    CROP_PROMPT,
    DUAL_ENGINE_OCR_SYSTEM_MESSAGE,
    HANDWRITING_CROP_PROMPT,
    HANDWRITING_OCR_SYSTEM_MESSAGE,
    HANDWRITING_PAGE_PROMPT,
    OCR_SYSTEM_MESSAGE,
    OLMOCR_PAGE_PROMPT,
    PROMPT_VERSION,
    model_supports_system_role,
)

# ---------------------------------------------------------------------------
# Live tier — requires a running LM Studio / Ollama / OpenAI-compatible
# endpoint. Skipped in CI; see AGENTS.md for the manual command.
# ---------------------------------------------------------------------------


@pytest.fixture
def ensure_live_endpoint() -> str:
    """Check that the live VLM endpoint is reachable and return the base URL."""
    api_base = os.getenv("LLM_API_BASE", "http://localhost:1234/v1").rstrip("/")
    models_url = f"{api_base}/models"
    try:
        resp = httpx.get(models_url, timeout=2.0)
        if resp.status_code != 200:
            pytest.skip(
                f"Live LLM endpoint at {models_url} returned status code {resp.status_code}"
            )
    except Exception as exc:
        pytest.skip(f"Live LLM endpoint not reachable at {api_base}: {exc}")
    return api_base


def _create_sample_crop_base64(text: str = "OmniScribe Live OCR Test") -> str:
    """Generate a clean image crop with text and return base64 PNG string."""
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 25), text, fill=(0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_vlm_crop_ocr(ensure_live_endpoint: str):
    """Test single crop OCR against live VLM endpoint."""
    api_base = ensure_live_endpoint
    api_key = os.getenv("LLM_API_KEY", "lm-studio")
    model = os.getenv("LLM_MODEL", "allenai/olmocr-2-7b")

    processor = OCRProcessor(api_base=api_base, api_key=api_key, model=model)

    # Verify model is loaded on the endpoint
    await processor.ensure_model_loaded()

    crop_b64 = _create_sample_crop_base64("TESTING CROP OCR")
    result = await processor.perform_ocr_on_crop(crop_b64)

    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ---------------------------------------------------------------------------
# Default tier — mock-based regression coverage for prompt/parsing contract.
#
# These tests are not marked ``live_llm`` and run in the fast tier. They
# pin the exact prompt the OCR pipeline sends, the response parsing logic,
# and the model-specific behaviour (OlmOCR-2 dropping the system role,
# Qwen sending one, etc.) so regressions surface in PR CI rather than only
# on a manual LM Studio run.
# ---------------------------------------------------------------------------


def _make_chat_completion_response(content: str) -> dict[str, object]:
    """Return a fake OpenAI-compatible chat completion response payload."""
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "model": "mock",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _make_models_response(model_id: str) -> dict[str, object]:
    """Return a fake ``/v1/models`` response that lists ``model_id`` as loaded."""
    return {"object": "list", "data": [{"id": model_id, "object": "model"}]}


class _VLMRecorder:
    """Capture-and-replay mock for ``httpx.AsyncClient.post``.

    The recorder stores every call's URL, JSON payload, and headers
    so tests can assert on the exact prompt the OCR pipeline sent.
    The ``chat_response`` and ``models_response`` payloads control
    what ``/v1/chat/completions`` and ``/v1/models`` return.

    Implementation note: ``AsyncMock(side_effect=...)`` does not
    await coroutine callables. An earlier version of this helper
    used ``async def __call__`` and silently produced 'coroutine
    object has no attribute status_code' failures because the
    awaited response was actually a coroutine. The current
    implementation uses ``AsyncMock`` + ``side_effect`` set to a
    plain function that records and returns a ``Response``; the
    ``AsyncMock`` framework awaits the return value itself.
    """

    def __init__(
        self,
        chat_response: dict[str, object] | None = None,
        models_response: dict[str, object] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.chat_response = chat_response or _make_chat_completion_response("OCR text")
        self.models_response = models_response or _make_models_response("mock-model")
        # AsyncMock with a sync side_effect: the framework awaits
        # the return value, so the side_effect function must return
        # a Response, not a coroutine.
        self._mock = AsyncMock(side_effect=self._respond)

    def _respond(self, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append(
            {
                "url": str(url),
                "json": kwargs.get("json", {}),
                "headers": dict(kwargs.get("headers", {}) or {}),
            }
        )
        if "/models" in str(url):
            return httpx.Response(200, json=self.models_response)
        return httpx.Response(200, json=self.chat_response)

    def install(self) -> _VLMRecorder:
        """Install the recorder as the global ``httpx.AsyncClient.post``.

        Returns ``self`` so the test can use the recorder as
        ``rec = _VLMRecorder().install()`` and read ``rec.calls``
        after the production code path returns.
        """
        self._patcher = patch("httpx.AsyncClient.post", new=self._mock)
        self._patcher.start()
        return self

    def stop(self) -> None:
        self._patcher.stop()


@pytest.fixture
def vlm_mock():
    """Yield a :class:`_VLMRecorder` already installed as the global
    ``httpx.AsyncClient.post``. Tests use it to assert on the exact
    request payload while feeding the OCR pipeline a canned response.
    """
    rec = _VLMRecorder().install()
    try:
        yield rec
    finally:
        rec.stop()


class TestPromptFormatContract:
    """Pin the exact prompt the OCR pipeline sends to the VLM.

    These tests catch prompt-formatting regressions (a stray
    constant, a model-specific branch that was removed, an
    image-prefix change, etc.) that the live test alone would
    only catch by accident on a manual LM Studio run.
    """

    @pytest.mark.asyncio
    async def test_crop_ocr_sends_user_role_image_url(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """The single-crop path's user message has a text part and an
        ``image_url`` data-URL part. The Qwen default also adds a
        system message, which is covered by the sibling test; this
        test pins the user-turn shape."""
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=")

        chat_calls = [c for c in vlm_mock.calls if "/chat/completions" in c["url"]]
        assert len(chat_calls) == 1
        body = chat_calls[0]["json"]
        assert isinstance(body, dict)
        messages = body["messages"]  # type: ignore[index]
        assert isinstance(messages, list)
        assert len(messages) >= 1
        # The Qwen default sends a system message; pin that the
        # user-role message is the *last* one (mirrors the OpenAI
        # convention that the system message precedes the user turn).
        user = messages[-1]
        assert user["role"] == "user"
        # The text part is the CROP prompt; verify it matches the
        # canonical constant. Catching a prompt-rename regression
        # matters because the model was RL-trained on the canonical
        # string.
        content = user["content"]
        assert isinstance(content, list)
        text_parts = [p for p in content if p.get("type") == "text"]
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(text_parts) == 1
        assert len(image_parts) == 1
        assert text_parts[0]["text"] == CROP_PROMPT
        # Image is sent as a data URL with the base64 payload inlined.
        assert image_parts[0]["image_url"]["url"] == "data:image/jpeg;base64,aW1hZ2U="

    @pytest.mark.asyncio
    async def test_crop_ocr_sends_ocr_system_message_for_qwen(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """Qwen + crop path → the OCR system message is sent.

        The system role is only dropped for OlmOCR-2 (RL-trained on
        a user-only distribution). All other models get the system
        role layered on top of the user prompt.
        """
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=")

        chat_call = next(c for c in vlm_mock.calls if "/chat/completions" in c["url"])
        messages = chat_call["json"]["messages"]  # type: ignore[index]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == OCR_SYSTEM_MESSAGE
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_olmocr_page_path_drops_system_message(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """OlmOCR-2 + page path → no system role. Regression guard
        for the field-reported bug: LM Studio + OlmOCR-2 fails on the
        crop / handwriting / dual-engine paths when a system role is
        layered on top of the model's RL training."""
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="allenai/olmocr-2-7b",
        )
        await proc.perform_ocr(image_base64="aW1hZ2U=")

        chat_call = next(c for c in vlm_mock.calls if "/chat/completions" in c["url"])
        messages = chat_call["json"]["messages"]  # type: ignore[index]
        # Pure user message — no system role.
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        # The text part is the OLMOCR canonical page prompt.
        content = messages[0]["content"]
        assert isinstance(content, list)
        text_parts = [p for p in content if p.get("type") == "text"]
        assert text_parts[0]["text"] == OLMOCR_PAGE_PROMPT

    @pytest.mark.asyncio
    async def test_handwriting_page_path_sends_handwriting_system_message_for_qwen(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """Qwen + handwriting mode → handwriting system message."""
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        proc.handwriting_mode = True
        await proc.perform_ocr(image_base64="aW1hZ2U=")

        chat_call = next(c for c in vlm_mock.calls if "/chat/completions" in c["url"])
        messages = chat_call["json"]["messages"]  # type: ignore[index]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == HANDWRITING_OCR_SYSTEM_MESSAGE
        # The user-role text part is the HANDWRITING page prompt,
        # not the canonical OLMOCR page prompt.
        text_parts = [p for p in messages[1]["content"] if p.get("type") == "text"]
        assert text_parts[0]["text"] == HANDWRITING_PAGE_PROMPT

    @pytest.mark.asyncio
    async def test_handwriting_crop_path_uses_handwriting_crop_prompt(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """Qwen + handwriting mode + crop path → HANDWRITING_CROP_PROMPT
        and HANDWRITING system message."""
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        proc.handwriting_mode = True
        await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=")

        chat_call = next(c for c in vlm_mock.calls if "/chat/completions" in c["url"])
        messages = chat_call["json"]["messages"]  # type: ignore[index]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == HANDWRITING_OCR_SYSTEM_MESSAGE
        text_parts = [p for p in messages[1]["content"] if p.get("type") == "text"]
        assert text_parts[0]["text"] == HANDWRITING_CROP_PROMPT

    @pytest.mark.asyncio
    async def test_dual_engine_crop_path_sends_dual_engine_system_message(
        self, vlm_mock: _VLMRecorder
    ) -> None:
        """Qwen + dual_engine=True → DUAL_ENGINE_OCR_SYSTEM_MESSAGE."""
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        # No Tesseract available in the test env, so dual_engine
        # is effectively a no-op for the draft (the prompt falls
        # back to the default CROP_PROMPT, not the
        # ``fill_dual_engine_crop`` variant). The system message
        # is still set, and the call returns the fake response.
        await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=", dual_engine=True)

        chat_call = next(c for c in vlm_mock.calls if "/chat/completions" in c["url"])
        messages = chat_call["json"]["messages"]  # type: ignore[index]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == DUAL_ENGINE_OCR_SYSTEM_MESSAGE


class TestResponseParsingContract:
    """Pin the response-shape contract the OCR pipeline relies on.

    A VLM that returns a non-standard JSON shape (missing
    ``choices``, different ``content`` key, streaming-style
    incremental deltas, etc.) should still produce a sensible
    result without crashing the OCR pipeline.
    """

    @pytest.mark.asyncio
    async def test_empty_choices_returns_empty_string(self) -> None:
        """An empty ``choices`` array is treated as a blank response
        (the OCR pipeline returns ``""`` from ``perform_ocr_on_crop``
        and falls through to the next page's retry)."""
        rec = _VLMRecorder(chat_response={"choices": []}).install()
        try:
            proc = OCRProcessor(
                api_base="http://mock-llm.local/v1",
                api_key="x",
                model="qwen/qwen3-vl-8b",
            )
            result = await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=")
        finally:
            rec.stop()
        assert result == ""

    @pytest.mark.asyncio
    async def test_yaml_front_matter_is_stripped(self) -> None:
        """A response with the canonical OlmOCR YAML front matter
        (rotation / language / is_table flags) is stripped before
        the OCR pipeline returns the body. Regression guard for
        the YAML front-matter filter (audit A-11)."""
        rec = _VLMRecorder(
            chat_response=_make_chat_completion_response(
                "---\n"
                "primary_language: en\n"
                "is_rotation_valid: true\n"
                "rotation_correction: 0\n"
                "is_table: false\n"
                "is_diagram: false\n"
                "---\n"
                "# Document Title\n\nBody paragraph."
            )
        ).install()
        try:
            proc = OCRProcessor(
                api_base="http://mock-llm.local/v1",
                api_key="x",
                model="qwen/qwen3-vl-8b",
            )
            result = await proc.perform_ocr(image_base64="aW1hZ2U=")
        finally:
            rec.stop()
        assert isinstance(result, list)
        joined = "\n".join(result)
        assert "primary_language" not in joined
        assert "Document Title" in joined
        assert "Body paragraph" in joined

    @pytest.mark.asyncio
    async def test_hallucination_fallback_is_dropped(self) -> None:
        """The OlmOCR-2 fallback phrase (``The quick brown fox...``)
        is recognised and dropped to ``""`` from the crop path."""
        rec = _VLMRecorder(
            chat_response=_make_chat_completion_response(
                "The quick brown fox jumps over the lazy dog"
            )
        ).install()
        try:
            proc = OCRProcessor(
                api_base="http://mock-llm.local/v1",
                api_key="x",
                model="qwen/qwen3-vl-8b",
            )
            result = await proc.perform_ocr_on_crop(image_base64="aW1hZ2U=")
        finally:
            rec.stop()
        assert result == ""


class TestPreFlightModelCheck:
    """Pin the ``/v1/models`` pre-flight behaviour.

    ``ensure_model_loaded`` is called once at pipeline startup to
    guard against LM Studio's silent model fallback (issue #7).
    These tests cover the success and fail paths.

    Note: ``ensure_model_loaded`` uses the OpenAI SDK's
    ``client.models.list()`` (not the shared ``httpx.AsyncClient``
    used by the chat path), so this suite patches the SDK call
    directly. The chat-path tests above patch
    ``httpx.AsyncClient.post`` to cover the prompt/response shape.
    """

    @staticmethod
    def _patch_models_list(
        monkeypatch: pytest.MonkeyPatch, model_ids: list[str]
    ) -> None:
        """Patch ``AsyncOpenAI.models.list`` to return ``model_ids``."""
        from types import SimpleNamespace

        fake_page = SimpleNamespace(data=[SimpleNamespace(id=mid) for mid in model_ids])

        async def fake_list(self):
            return fake_page

        monkeypatch.setattr("openai.resources.models.AsyncModels.list", fake_list)

    @pytest.mark.asyncio
    async def test_ensure_model_loaded_passes_when_model_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_models_list(monkeypatch, ["qwen/qwen3-vl-8b"])
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        await proc.ensure_model_loaded()  # should not raise

    @pytest.mark.asyncio
    async def test_ensure_model_loaded_raises_when_model_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from omniscribe.core.ocr.exceptions import ModelNotLoadedError

        self._patch_models_list(monkeypatch, ["some-other-model"])
        proc = OCRProcessor(
            api_base="http://mock-llm.local/v1",
            api_key="x",
            model="qwen/qwen3-vl-8b",
        )
        with pytest.raises(ModelNotLoadedError):
            await proc.ensure_model_loaded()


class TestPromptVersioning:
    """Pin ``PROMPT_VERSION`` to a stable identifier.

    ``PROMPT_VERSION`` is the dispatch key for cached calibrations
    and the model-quality dashboard. Bumping it without a release
    note is a regression; a missing or wrong constant is a bug.
    """

    def test_prompt_version_is_a_nonempty_string(self) -> None:
        assert isinstance(PROMPT_VERSION, str)
        assert PROMPT_VERSION, "PROMPT_VERSION must not be empty"

    def test_model_supports_system_role_is_consistent(self) -> None:
        """``model_supports_system_role`` must be a pure function of
        the model id (no I/O, no module state). The OlmOCR-2 family
        is the canonical ``False`` case; everything else is ``True``."""
        assert model_supports_system_role("allenai/olmocr-2-7b") is False
        assert model_supports_system_role("allenai/olmocr-7b") is False
        assert model_supports_system_role("qwen/qwen3-vl-8b") is True
        assert model_supports_system_role("anthropic/claude-3-5-sonnet") is True
