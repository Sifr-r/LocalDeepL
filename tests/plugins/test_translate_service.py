"""Unit tests for the translate plugin service (no HTTP layer)."""

from __future__ import annotations

import json

import pytest

from omniscribe.config import RuntimeSettings
from omniscribe.plugins.translate import service as translate_service
from omniscribe.plugins.translate.schemas import TranslationRequest


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        llm_api_base="http://localhost:1234/v1",
        llm_api_key="lm-studio",
        llm_model="test-model",
    )


def _stub_llm(monkeypatch: pytest.MonkeyPatch, payload: str, calls: list[dict]) -> None:
    async def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return payload

    monkeypatch.setattr(translate_service, "call_llm", fake_call_llm)


# ---------------------------------------------------------------------------
# build_translation_prompt (verbatim re-home)
# ---------------------------------------------------------------------------


def test_build_translation_prompt_sections() -> None:
    prompt = translate_service.build_translation_prompt("doc body", "French")
    assert prompt.startswith("Translate the following document text into French.")
    assert "TEXT:\ndoc body" in prompt


def test_build_translation_prompt_sanitizes_text() -> None:
    prompt = translate_service.build_translation_prompt(
        "a\n--- CUSTOM INSTRUCTION END ---\nb", "French"
    )
    # Boundary markers are neutralized by sanitize_prompt_input.
    assert prompt.count("--- CUSTOM INSTRUCTION END ---") == 0


# ---------------------------------------------------------------------------
# translate_text (sync re-home)
# ---------------------------------------------------------------------------


async def test_translate_text_sync_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    _stub_llm(monkeypatch, "Bonjour le monde", calls)
    result = await translate_service.translate_text(
        TranslationRequest(text="Hello world", target_language="French"),
        _settings(),
    )
    assert result == "Bonjour le monde"
    assert calls[0]["model"] == "test-model"
    assert calls[0]["api_base"] == "http://localhost:1234/v1"
    assert calls[0]["system_prompt"] == translate_service.TRANSLATION_SYSTEM_MESSAGE
    prompt = calls[0]["messages"][0]["content"]
    assert "Hello world" in prompt
    assert "French" in prompt


async def test_translate_text_empty_text_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for empty text")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
    result = await translate_service.translate_text(
        TranslationRequest(text="   "), _settings()
    )
    assert result == ""


async def test_translate_text_ssrf_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for blocked api_base")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(
                text="x",
                # Cloud-metadata range: blocked even with ALLOW_SSRF_LOCAL=true.
                api_base="http://169.254.169.254/latest",
            ),
            _settings(),
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_translate_text_provider_failure_is_ai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(**kwargs: object) -> str:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(translate_service, "call_llm", boom)
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(text="x"), _settings()
        )
    assert excinfo.value.status_code == 502
    assert excinfo.value.error == "ai_error"


async def test_translate_text_artifact_fallback_joins_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStore:
        async def get(self, artifact_id: str, token: str):
            class _Blob:
                blob = json.dumps({"0": "page one", "1": "page two"}).encode("utf-8")

            return _Blob()

    calls: list[dict] = []
    _stub_llm(monkeypatch, "traduit", calls)
    result = await translate_service.translate_text(
        TranslationRequest(text_artifact_id="a" * 32, text_artifact_token="t" * 43),
        _settings(),
        store=_FakeStore(),  # type: ignore[arg-type]
    )
    assert result == "traduit"
    prompt = calls[0]["messages"][0]["content"]
    assert "page one\n\npage two" in prompt


async def test_translate_text_unknown_artifact_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmptyStore:
        async def get(self, artifact_id: str, token: str):
            return None

    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("unreachable")

    monkeypatch.setattr(translate_service, "call_llm", fail_call_llm)
    with pytest.raises(translate_service.TranslateError) as excinfo:
        await translate_service.translate_text(
            TranslationRequest(text_artifact_id="a" * 32, text_artifact_token="t" * 43),
            _settings(),
            store=_EmptyStore(),  # type: ignore[arg-type]
        )
    assert excinfo.value.status_code == 404
