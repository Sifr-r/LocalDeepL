"""Transcribe service: validation → engine → artifacts → response dict.

Verbatim re-home of the pre-harness `api/services/transcription.py`
(`44ef123^`) semantics onto the harness ArtifactStore. The old service
stored page-dict artifacts (`{0: [lines]}`) through a typed artifact
service; the harness store takes opaque bytes, so the same page-dict is
serialized as JSON using the text-artifact convention
`{"<page_index>": "<lines joined by \n>"}`.
"""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from collections.abc import Mapping
from typing import Any

from omniscribe.core.transcription import (
    AudioValidationError,
    TranscriptionEngineProtocol,
    TranscriptionError,
    get_transcription_engine,
    validate_audio_input,
)
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.transcribe.schemas import TranscribeRequest
from omniscribe.utils.security import check_ssrf_target_sync

_LOGGER = logging.getLogger("omniscribe.plugins.transcribe")

DEFAULT_TRANSCRIPTION_API_BASE = "https://api.openai.com/v1"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_TRANSCRIPTION_ENGINE = "api"


class TranscribeError(Exception):
    """User-facing transcribe error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def resolve_engine_settings(
    request: TranscribeRequest, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Form → config store → default, per field (old fallback chain)."""
    return {
        "model": str(request.model or config.get("transcription_model", "whisper-1")),
        "engine": str(request.engine or config.get("transcription_engine", "api")),
        "api_base": str(
            request.api_base
            or config.get("transcription_api_base", DEFAULT_TRANSCRIPTION_API_BASE)
        ),
        "api_key": str(request.api_key or config.get("transcription_api_key", ""))
        or None,
        "language": str(request.language or config.get("transcription_language") or "")
        or None,
        "prompt": str(request.prompt or config.get("transcription_prompt") or "")
        or None,
        "temperature": request.temperature,
    }


def _engine_call_kwargs(
    engine: TranscriptionEngineProtocol, context: dict[str, Any]
) -> dict[str, Any]:
    """Trim the engine call context to the engine's declared call surface.

    The resolved settings chain rides along for context-aware engines (any
    ``**kwargs`` transcribe); the core engines keep their exact
    ``TranscriptionEngineProtocol`` call and receive their settings through
    the factory constructor instead.
    """
    params = inspect.signature(engine.transcribe).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return context
    return {k: v for k, v in context.items() if k in params}


async def transcribe(
    request: TranscribeRequest,
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    store: ArtifactStore,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Sync transcription; verbatim old response shape."""
    # SSRF-check the caller-supplied override only (translate precedent):
    # config-store/default values are trusted operator config.
    if request.api_base and request.api_base.strip():
        check = check_ssrf_target_sync(request.api_base.strip())
        if not check.allowed:
            raise TranscribeError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason}",
            )

    try:
        validate_audio_input(
            filename=filename,
            content_type=content_type,
            file_size=len(file_bytes),
        )
    except AudioValidationError as exc:
        raise TranscribeError(400, "bad_request", exc.message) from exc

    resolved = resolve_engine_settings(request, config)
    engine = get_transcription_engine(
        engine_type=resolved["engine"],
        model=resolved["model"],
        api_base=resolved["api_base"],
        api_key=resolved["api_key"],
    )
    try:
        result = await engine.transcribe(
            **_engine_call_kwargs(
                engine,
                {
                    "file_bytes": file_bytes,
                    "filename": filename,
                    **resolved,
                },
            )
        )
    except TranscriptionError as exc:
        raise TranscribeError(503, "backend_unavailable", exc.message) from exc
    except Exception as exc:
        _LOGGER.exception("Voice transcription request failed")
        raise TranscribeError(
            502, "ai_error", "The AI service request failed."
        ) from exc

    job_id = f"job-{uuid.uuid4().hex[:12]}"
    lines = [s.text for s in result.segments] if result.segments else [result.text]
    text_handle = await store.put(
        json.dumps({"0": "\n".join(lines)}).encode("utf-8"),
        content_type="application/json",
        owner_job_id=job_id,
    )
    doc_result = result.to_document_result()
    page_metadata = doc_result.pages[0].metadata if doc_result.pages else {}
    meta_handle = await store.put(
        json.dumps({"0": json.dumps(page_metadata)}).encode("utf-8"),
        content_type="application/json",
        owner_job_id=job_id,
    )
    return {
        "text": result.text,
        "language": result.language,
        "duration": result.duration,
        "text_artifact_id": text_handle.id,
        "text_artifact_token": text_handle.token,
        "metadata_artifact_id": meta_handle.id,
        "metadata_artifact_token": meta_handle.token,
        "job_id": job_id,
        "segments": [
            {
                "id": s.id,
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "confidence": s.confidence,
            }
            for s in result.segments
        ],
    }
