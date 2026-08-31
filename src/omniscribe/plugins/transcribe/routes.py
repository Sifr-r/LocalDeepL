"""HTTP routes for the transcribe plugin (client-frozen contract).

Routes whose handler may answer with the error envelope declare a union
return type; FastAPI cannot build a response model from such unions, so
those decorators pass ``response_model=None``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe.plugins.transcribe.schemas import (
    TranscribeRequest,
    TranscriptionConfigResponse,
    TranscriptionConfigUpdate,
)
from omniscribe.plugins.transcribe.service import (
    TranscribeError,
    TranscriptionService,
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def build_transcribe_router(service: TranscriptionService) -> APIRouter:
    router = APIRouter(tags=["transcribe"])

    @router.post("/api/transcribe", response_model=None)
    async def transcribe_audio(request: Request) -> Any:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            return _envelope(400, "bad_request", "missing 'file' field")
        file_bytes: bytes = await upload.read()
        fields: dict[str, Any] = {
            key: value
            for key, value in form.items()
            if key != "file" and isinstance(value, str)
        }
        try:
            options = TranscribeRequest.model_validate(fields)
        except ValidationError as exc:
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors(include_url=False)},
            )
        filename = str(getattr(upload, "filename", "") or "") or "audio.wav"
        content_type = getattr(upload, "content_type", "") or None
        try:
            result = await service.transcribe(
                options,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        except TranscribeError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return result

    @router.get("/api/config/transcription", response_model=None)
    async def get_transcription_config() -> TranscriptionConfigResponse:
        return service.get_config()

    @router.post("/api/config/transcription", response_model=None)
    async def update_transcription_config(
        body: TranscriptionConfigUpdate,
    ) -> TranscriptionConfigResponse | JSONResponse:
        try:
            return service.update_config(body)
        except TranscribeError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/models/transcription", response_model=None)
    async def get_transcription_models() -> dict[str, Any]:
        return {"models": await service.discover_models()}

    return router
