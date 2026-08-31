"""Unit tests for the transcribe plugin service (no HTTP layer)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from omniscribe.plugins.transcribe import service as transcribe_service
from omniscribe.plugins.transcribe.schemas import TranscribeRequest


class _FakeStore:
    def __init__(self) -> None:
        self.blobs: dict[str, tuple[str, bytes, str]] = {}

    async def put(
        self,
        blob: bytes,
        *,
        content_type: str,
        owner_job_id: str,
        ttl_seconds: int | None = None,
    ) -> Any:
        artifact_id = f"a{len(self.blobs):031d}"
        token = f"t{len(self.blobs):041d}"
        self.blobs[artifact_id] = (token, blob, content_type)

        class _Handle:
            pass

        handle = _Handle()
        handle.id = artifact_id
        handle.token = token
        return handle

    async def get(self, artifact_id: str, token: str) -> Any:
        entry = self.blobs.get(artifact_id)
        if entry is None or entry[0] != token:
            return None

        class _Blob:
            blob = entry[1]
            content_type = entry[2]
            record = None

        return _Blob()


def _config() -> dict[str, str]:
    return {
        "transcription_api_base": "https://api.openai.com/v1",
        "transcription_model": "whisper-1",
        "transcription_engine": "api",
    }


def _result(text: str = "hello world", language: str | None = "en") -> Any:
    from omniscribe.core.transcription.types import (
        TranscriptionResult,
        TranscriptionSegment,
    )

    return TranscriptionResult(
        text=text,
        language=language,
        duration=2.0,
        segments=[TranscriptionSegment(id=0, start=0.0, end=2.0, text=text)],
    )


def _stub_engine(
    monkeypatch: pytest.MonkeyPatch,
    result: Any,
    calls: list[dict[str, Any]],
    factory_calls: list[dict[str, Any]] | None = None,
) -> None:
    class _Engine:
        async def transcribe(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return result

    def _factory(**kw: Any) -> _Engine:
        if factory_calls is not None:
            factory_calls.append(kw)
        return _Engine()

    monkeypatch.setattr(transcribe_service, "get_transcription_engine", _factory)


async def test_transcribe_happy_path_stores_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    factory_calls: list[dict[str, Any]] = []
    _stub_engine(monkeypatch, _result(), calls, factory_calls)
    store = _FakeStore()
    result = await transcribe_service.transcribe(
        TranscribeRequest(model="whisper-1"),
        file_bytes=b"fake-audio",
        filename="clip.wav",
        content_type="audio/wav",
        store=store,
        config=_config(),
    )
    assert result["text"] == "hello world"
    assert result["language"] == "en"
    assert result["duration"] == 2.0
    assert result["job_id"].startswith("job-")
    assert len(result["segments"]) == 1
    assert result["segments"][0]["text"] == "hello world"
    # Both artifacts stored and referenced with tokens.
    assert result["text_artifact_id"] in store.blobs
    assert result["metadata_artifact_id"] in store.blobs
    text_blob = json.loads(store.blobs[result["text_artifact_id"]][1].decode("utf-8"))
    assert text_blob == {"0": "hello world"}
    meta_blob = json.loads(
        store.blobs[result["metadata_artifact_id"]][1].decode("utf-8")
    )
    assert set(meta_blob) == {"0"}
    # Factory received the resolved chain values.
    assert factory_calls[0]["model"] == "whisper-1"
    assert factory_calls[0]["api_base"] == "https://api.openai.com/v1"
    # Engine received exactly the Protocol call surface.
    assert set(calls[0]) == {
        "file_bytes",
        "filename",
        "language",
        "prompt",
        "temperature",
    }


async def test_transcribe_resolves_form_over_config_over_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    factory_calls: list[dict[str, Any]] = []
    _stub_engine(monkeypatch, _result(), calls, factory_calls)
    await transcribe_service.transcribe(
        TranscribeRequest(model="custom-model", api_key="sk-x"),
        file_bytes=b"x",
        filename="a.mp3",
        content_type="audio/mpeg",
        store=_FakeStore(),
        config={"transcription_model": "config-model"},
    )
    assert factory_calls[0]["model"] == "custom-model"


async def test_transcribe_ssrf_checks_override_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("must not be called")

    monkeypatch.setattr(transcribe_service, "get_transcription_engine", fail_call_llm)
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(api_base="http://169.254.169.254/latest"),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_transcribe_bad_extension_maps_to_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(),
            file_bytes=b"%PDF-1.4",
            filename="doc.pdf",
            content_type="application/pdf",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.error == "bad_request"
    assert "Unsupported audio format" in excinfo.value.detail


async def test_transcribe_engine_error_maps_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omniscribe.core.transcription.types import TranscriptionError

    class _Broken:
        async def transcribe(self, **kwargs: Any) -> Any:
            raise TranscriptionError(
                "Local transcription requires the 'transcription' extra", 503
            )

    monkeypatch.setattr(
        transcribe_service, "get_transcription_engine", lambda **kw: _Broken()
    )
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(engine="local"),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 503
    assert excinfo.value.error == "backend_unavailable"
    assert "transcription" in excinfo.value.detail


async def test_transcribe_unexpected_error_maps_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken:
        async def transcribe(self, **kwargs: Any) -> Any:
            raise RuntimeError("connection reset")

    monkeypatch.setattr(
        transcribe_service, "get_transcription_engine", lambda **kw: _Broken()
    )
    with pytest.raises(transcribe_service.TranscribeError) as excinfo:
        await transcribe_service.transcribe(
            TranscribeRequest(),
            file_bytes=b"x",
            filename="a.wav",
            content_type="audio/wav",
            store=_FakeStore(),
            config=_config(),
        )
    assert excinfo.value.status_code == 502
    assert excinfo.value.error == "ai_error"
    assert excinfo.value.detail == "The AI service request failed."
