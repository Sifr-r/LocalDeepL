"""Unit tests for multi_format_client and llm_client integration."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from omniscribe.api.schemas.requests import ProviderConfig, ProviderFormatEnum
from omniscribe.core.llm_client import call_llm, call_vlm
from omniscribe.core.ocr.exceptions import LLMCallError
from omniscribe.core.ocr.multi_format_client import complete_vlm_prompt


@pytest.fixture
def openai_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-openai",
        display_name="Test OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://mock-llm.local/v1",
        api_key="test-sk-key",
        models=["gpt-4o"],
    )


@pytest.fixture
def anthropic_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-anthropic",
        display_name="Test Anthropic",
        format=ProviderFormatEnum.ANTHROPIC_COMPATIBLE,
        api_url="http://mock-anthropic.local",
        api_key="test-anthropic-key",
        models=["claude-3-5-sonnet"],
    )


@pytest.fixture
def ollama_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-ollama",
        display_name="Test Ollama",
        format=ProviderFormatEnum.OLLAMA_COMPATIBLE,
        api_url="http://mock-ollama.local:11434",
        requires_auth=False,
        models=["llama3.2-vision"],
    )


async def test_openai_compatible_dispatch(openai_config: ProviderConfig) -> None:
    expected_resp = {"choices": [{"message": {"content": "Extracted OCR text"}}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert "chat/completions" in url
        assert headers["Authorization"] == "Bearer test-sk-key"
        assert json["model"] == "gpt-4o"
        assert json["messages"][0]["role"] == "user"
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            openai_config,
            prompt="OCR prompt text",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Extracted OCR text"


async def test_anthropic_compatible_dispatch(anthropic_config: ProviderConfig) -> None:
    expected_resp = {"content": [{"type": "text", "text": "Anthropic response text"}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert "messages" in url
        assert headers["x-api-key"] == "test-anthropic-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert json["model"] == "claude-3-5-sonnet"
        assert json["messages"][0]["content"][0]["type"] == "image"
        assert json["messages"][0]["content"][0]["source"]["data"] == "aW1hZ2VfZGF0YQ=="
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            anthropic_config,
            prompt="Transcribe page",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Anthropic response text"


async def test_ollama_compatible_dispatch(ollama_config: ProviderConfig) -> None:
    expected_resp = {"message": {"content": "Ollama extracted text"}}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert "api/chat" in url
        assert json["model"] == "llama3.2-vision"
        assert json["messages"][0]["images"] == ["aW1hZ2VfZGF0YQ=="]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            ollama_config,
            prompt="Read this image",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Ollama extracted text"


async def test_non_200_raises_llm_call_error(openai_config: ProviderConfig) -> None:
    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        return httpx.Response(400, text="Bad Request: Model not found")

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(LLMCallError) as exc_info:
            await complete_vlm_prompt(openai_config, prompt="Hello")
        assert "400" in str(exc_info.value)


async def test_missing_model_raises_llm_call_error() -> None:
    """F1.3 audit fix (P0): defensive fail-fast when neither ``model`` arg nor
    ``provider_config.models`` resolves a target.

    Previously the code silently fell back to the literal string ``"gpt-4o"``,
    which is meaningless to a non-OpenAI host and can route requests to a
    cloud provider the user never intended to call.
    """
    config = ProviderConfig(
        id="test-no-model",
        display_name="Test No Model",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://mock-llm.local/v1",
        api_key="test-sk-key",
        models=[],
    )

    with pytest.raises(LLMCallError, match="Cannot resolve target model"):
        await complete_vlm_prompt(
            config,
            prompt="OCR prompt text",
            image_base64="aW1hZ2VfZGF0YQ==",
        )


async def test_whitespace_only_model_raises_llm_call_error() -> None:
    """F1.3 sibling: a whitespace-only model arg should not be treated as a valid model."""
    config = ProviderConfig(
        id="test-ws-model",
        display_name="Test WS Model",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://mock-llm.local/v1",
        api_key="test-sk-key",
        models=[],
    )

    with pytest.raises(LLMCallError, match="Cannot resolve target model"):
        await complete_vlm_prompt(
            config,
            prompt="OCR prompt text",
            image_base64="aW1hZ2VfZGF0YQ==",
            model="   ",
        )


async def test_call_vlm_wrapper(openai_config: ProviderConfig) -> None:
    expected_resp = {"choices": [{"message": {"content": "VLM wrapper output"}}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await call_vlm("Recognize this", provider_config=openai_config)
        assert res == "VLM wrapper output"


async def test_call_llm_wrapper_with_messages() -> None:
    expected_resp = {"choices": [{"message": {"content": "LLM wrapper output"}}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Translate this sentence"}],
        )
        assert res == "LLM wrapper output"


# --- Phase 2: timeout forwarding + shared client (fixes the silent 60s
# cap that the OCRProcessor's OMNISCRIBE_VLM_PAGE_TIMEOUT used to be
# overridden by, and removes the per-call TCP+TLS handshake). ---


async def test_timeout_forwarded_to_client_post(openai_config: ProviderConfig) -> None:
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(
            openai_config,
            prompt="p",
            timeout=240.0,
        )
    assert seen["timeout"] == 240.0


async def test_timeout_defaults_to_pool_default_when_unset(
    openai_config: ProviderConfig,
) -> None:
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(openai_config, prompt="p")
    # None → falls back to the shared client's default of 60s.
    assert seen["timeout"] == 60.0


async def test_call_llm_forwards_timeout() -> None:
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            prompt="x",
            timeout=123.0,
        )
    assert seen["timeout"] == 123.0


async def test_shared_client_reused_across_calls() -> None:
    """Two calls must use the same AsyncClient instance (the whole point
    of the cache: keep the connection pool warm)."""
    from omniscribe.core.ocr import multi_format_client

    # Reset the shared client so we observe the lazy-init path.
    await multi_format_client.aclose_shared_client()

    openai_cfg = ProviderConfig(
        id="t",
        display_name="t",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://mock.local/v1",
        api_key="k",
        models=["m"],
    )

    async def ok_post(*args, **kwargs):
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    with patch("httpx.AsyncClient.post", side_effect=ok_post):
        c1 = multi_format_client._get_shared_client()
        await complete_vlm_prompt(openai_cfg, prompt="p")
        c2 = multi_format_client._get_shared_client()
        await complete_vlm_prompt(openai_cfg, prompt="p")

    assert c1 is c2, "shared client must be reused across calls"
    await multi_format_client.aclose_shared_client()


async def test_openai_system_prompt_prepended_to_messages(
    openai_config: ProviderConfig,
) -> None:
    """When system_prompt is set on complete_vlm_prompt, the OpenAI
    payload must contain a system-role entry at index 0, then the user
    entry at index 1. When unset (None), the user entry stays at index 0
    to preserve backward compatibility with existing test assertions
    and any third-party OpenAI-compatible servers that don't accept a
    system role.
    """
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert json["messages"][0]["role"] == "system"
        assert json["messages"][0]["content"] == "You are a careful OCR engine."
        assert json["messages"][1]["role"] == "user"
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(
            openai_config,
            prompt="OCR this",
            image_base64="aW1hZ2VfZGF0YQ==",
            system_prompt="You are a careful OCR engine.",
        )


async def test_openai_no_system_prompt_keeps_user_at_index_zero(
    openai_config: ProviderConfig,
) -> None:
    """Backward-compat guard: with no system_prompt, the user role
    stays at index 0 so existing model clients and the canonical
    OlmOCR-2 page path (which depends on user-only distribution) keep
    working unchanged.
    """
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["messages"] = json["messages"]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(
            openai_config,
            prompt="OCR this",
            image_base64="aW1hZ2VfZGF0YQ==",
        )

    assert seen["messages"][0]["role"] == "user"
    assert all(m["role"] != "system" for m in seen["messages"])


async def test_anthropic_system_prompt_prepended(
    anthropic_config: ProviderConfig,
) -> None:
    expected_resp = {"content": [{"type": "text", "text": "ok"}]}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert json["messages"][0]["role"] == "system"
        assert json["messages"][0]["content"] == "be precise"
        assert json["messages"][1]["role"] == "user"
        assert json["messages"][1]["content"][0]["type"] == "image"
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(
            anthropic_config,
            prompt="OCR this",
            image_base64="aW1hZ2VfZGF0YQ==",
            system_prompt="be precise",
        )


async def test_ollama_system_prompt_prepended(
    ollama_config: ProviderConfig,
) -> None:
    expected_resp = {"message": {"content": "ok"}}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        assert json["messages"][0]["role"] == "system"
        assert json["messages"][0]["content"] == "stay terse"
        assert json["messages"][1]["role"] == "user"
        assert json["messages"][1]["images"] == ["aW1hZ2VfZGF0YQ=="]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await complete_vlm_prompt(
            ollama_config,
            prompt="Read image",
            image_base64="aW1hZ2VfZGF0YQ==",
            system_prompt="stay terse",
        )


async def test_call_llm_passes_system_prompt_through() -> None:
    """``call_llm`` is the entry point used by the OCR / translation /
    extraction call sites. Confirm system_prompt flows from there
    through to the wire payload.
    """
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["messages"] = json["messages"]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            system_prompt="system role content",
            messages=[{"role": "user", "content": "user role content"}],
        )

    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][0]["content"] == "system role content"
    assert seen["messages"][1]["role"] == "user"


async def test_call_llm_drops_system_role_from_messages() -> None:
    """A ``role: system`` entry inside the ``messages`` list is
    silently dropped. The explicit ``system_prompt`` parameter is
    the single source of truth for the system role — if you want
    one, pass it as a parameter, not as a messages-list entry.

    This used to extract the system role from the messages list
    and use it as a fallback. That path had no production caller
    and created two ways to do the same thing; we removed it
    so the explicit parameter is unambiguous.
    """
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["messages"] = json["messages"]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "I am the system role"},
                {"role": "user", "content": "user content here"},
            ],
        )

    # Only the user message survives — no system role leaks onto
    # the wire because the caller didn't use the explicit parameter.
    assert all(m["role"] != "system" for m in seen["messages"])
    assert seen["messages"][0]["role"] == "user"
    assert seen["messages"][0]["content"] == "user content here"


async def test_call_llm_explicit_system_prompt_overrides_messages_system() -> None:
    """When both forms are set, the explicit ``system_prompt``
    parameter wins and the system entry inside ``messages`` is dropped
    (single-sourced, to prevent accidental double-system messages on
    the wire).
    """
    expected_resp = {"choices": [{"message": {"content": "ok"}}]}
    seen: dict = {}

    async def mock_post(url: str, json: dict, headers: dict, **kwargs):
        seen["messages"] = json["messages"]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            system_prompt="explicit",
            messages=[
                {"role": "system", "content": "from-messages"},
                {"role": "user", "content": "user content"},
            ],
        )

    system_msgs = [m for m in seen["messages"] if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == "explicit"
