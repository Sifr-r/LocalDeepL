"""FastAPI router for voice transcription operations, model discovery, and config."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from omniscribe.api.routers.common import _stable_server_error
from omniscribe.api.routers.config import _config, _mask_api_key
from omniscribe.api.schemas.requests import TranscriptionConfigUpdate
from omniscribe.api.schemas.responses import (
    ModelsResponse,
    TranscriptionConfigResponse,
    TranscriptionJobResponse,
)
from omniscribe.api.services.transcription import TranscriptionService
from omniscribe.core.transcription import AudioValidationError, TranscriptionError

logger = logging.getLogger(__name__)
router = APIRouter()
_service = TranscriptionService()


@router.post("/api/transcribe", response_model=TranscriptionJobResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    engine: str | None = Form(None),
    api_base: str | None = Form(None),
    api_key: str | None = Form(None),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    temperature: float = Form(0.0),
    channel_id: str | None = Form(None),
) -> Any:
    """Transcribe an uploaded audio file into text and structured segments.

    Accepts audio formats (.mp3, .wav, .m4a, .flac, .ogg, .webm, etc.) up to configured upload cap.
    """
    file_bytes = await file.read()

    try:
        res = await _service.transcribe_audio(
            file_bytes=file_bytes,
            filename=file.filename or "audio.wav",
            content_type=file.content_type,
            engine_type=str(engine or _config.get("transcription_engine", "api")),
            model=str(model or _config.get("transcription_model", "whisper-1")),
            api_base=str(
                api_base
                or _config.get("transcription_api_base", "https://api.openai.com/v1")
            ),
            api_key=str(api_key or _config.get("transcription_api_key", "")) or None,
            language=str(language or _config.get("transcription_language") or "")
            or None,
            prompt=str(prompt or _config.get("transcription_prompt") or "") or None,
            temperature=temperature,
            channel_id=channel_id,
        )
        return res
    except AudioValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except TranscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception:
        logger.exception("Voice transcription request failed")
        return _stable_server_error()


@router.get("/api/models/transcription", response_model=ModelsResponse)
async def get_transcription_models() -> Any:
    """Discover available audio transcription models from the configured backend endpoint."""
    api_base = str(_config.get("transcription_api_base", "https://api.openai.com/v1"))
    api_key = str(_config.get("transcription_api_key", "")) or None

    try:
        import httpx

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_base.rstrip('/')}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return ModelsResponse(models=models)
    except Exception as exc:
        logger.warning(
            "Failed to fetch models from transcription api_base %s: %s", api_base, exc
        )

    # Standard fallback models list
    fallback_models = [
        "whisper-1",
        "whisper-large-v3",
        "whisper-medium",
        "whisper-base",
        "whisper-small",
        "whisper-tiny",
    ]
    return ModelsResponse(models=fallback_models)


@router.get("/api/config/transcription", response_model=TranscriptionConfigResponse)
async def get_transcription_config() -> Any:
    """Get the current voice transcription runtime configuration."""
    from omniscribe.api.services.security_config import SecuritySettings

    sec = SecuritySettings.from_env()

    return TranscriptionConfigResponse(
        transcription_api_base=str(
            _config.get("transcription_api_base", "https://api.openai.com/v1")
        ),
        transcription_api_key=_mask_api_key(
            str(_config.get("transcription_api_key", ""))
        )
        or "",
        transcription_model=str(_config.get("transcription_model", "whisper-1")),
        transcription_engine=str(_config.get("transcription_engine", "api")),
        transcription_auth_token=_mask_api_key(sec.transcription_auth_token),
        language=str(_config.get("transcription_language", "")) or None,
        prompt=str(_config.get("transcription_prompt", "")) or None,
        temperature=float(_config.get("transcription_temperature", 0.0)),
    )


@router.post("/api/config/transcription", response_model=TranscriptionConfigResponse)
async def update_transcription_config(body: TranscriptionConfigUpdate) -> Any:
    """Update runtime configuration for voice transcription."""
    if body.api_base is not None:
        _config["transcription_api_base"] = body.api_base
    if body.transcription_api_key is not None:
        _config["transcription_api_key"] = body.transcription_api_key
    elif body.api_key is not None:
        _config["transcription_api_key"] = body.api_key
    if body.model is not None:
        _config["transcription_model"] = body.model
    if body.engine is not None:
        _config["transcription_engine"] = body.engine.value
    if body.language is not None:
        _config["transcription_language"] = body.language
    if body.prompt is not None:
        _config["transcription_prompt"] = body.prompt
    if body.temperature is not None:
        _config["transcription_temperature"] = body.temperature

    return await get_transcription_config()
