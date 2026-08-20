"""FastAPI router for voice transcription operations, model discovery, and config."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from omniscribe.api.routers.config import (
    _CONFIG_BACKEND_INCOMPATIBLE_MESSAGE,
    _ConfigBackendIncompatible,
    _load_config_from_store,
    _mask_api_key,
    _persist_config,
)
from omniscribe.api.schemas.requests import (
    TranscriptionConfigUpdate,
)
from omniscribe.api.schemas.responses import (
    ModelsResponse,
    TranscriptionConfigResponse,
    TranscriptionJobResponse,
)
from omniscribe.api.services.api_helpers import stable_server_error
from omniscribe.api.services.security import (
    SAFE_API_BASE_ERROR,
    UploadValidationError,
    cleanup_files,
    save_validated_upload,
)
from omniscribe.api.services.transcription import TranscriptionService
from omniscribe.core.transcription import AudioValidationError, TranscriptionError
from omniscribe.utils.security import is_ssrf_target

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
    try:
        upload = await save_validated_upload(file)
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        with open(upload.path, "rb") as f:
            file_bytes = f.read()
        config = _load_config_from_store()

        resolved_api_base = str(
            api_base
            or config.get("transcription_api_base", "https://api.openai.com/v1")
        )
        if not (await is_ssrf_target(resolved_api_base)).allowed:
            raise HTTPException(status_code=403, detail=SAFE_API_BASE_ERROR)

        res = await _service.transcribe_audio(
            file_bytes=file_bytes,
            filename=file.filename or f"audio{upload.suffix}",
            content_type=file.content_type,
            engine_type=str(engine or config.get("transcription_engine", "api")),
            model=str(model or config.get("transcription_model", "whisper-1")),
            api_base=resolved_api_base,
            api_key=str(api_key or config.get("transcription_api_key", "")) or None,
            language=str(language or config.get("transcription_language") or "")
            or None,
            prompt=str(prompt or config.get("transcription_prompt") or "") or None,
            temperature=temperature,
            channel_id=channel_id,
        )
        return res
    except AudioValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except TranscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Voice transcription request failed")
        return stable_server_error()
    finally:
        cleanup_files(upload.path)


@router.get("/api/models/transcription", response_model=ModelsResponse)
async def get_transcription_models() -> Any:
    """Discover available audio transcription models from the configured backend endpoint."""
    config = _load_config_from_store()
    api_base = str(config.get("transcription_api_base", "https://api.openai.com/v1"))
    api_key = str(config.get("transcription_api_key", "")) or None

    fallback_models = [
        "whisper-1",
        "whisper-large-v3",
        "whisper-medium",
        "whisper-base",
        "whisper-small",
        "whisper-tiny",
    ]

    if not (await is_ssrf_target(api_base)).allowed:
        return ModelsResponse(models=fallback_models)

    try:
        import httpx

        from omniscribe.api.services.provider_manager import (
            extract_model_ids_from_response,
        )

        headers = {}
        if api_key and api_key != "lm-studio":
            headers["Authorization"] = f"Bearer {api_key}"

        base = api_base.rstrip("/")
        candidate_urls: list[str] = []
        if base.endswith("/v1"):
            candidate_urls.append(f"{base}/models")
        else:
            candidate_urls.append(f"{base}/v1/models")
            candidate_urls.append(f"{base}/models")
        candidate_urls.append(f"{base}/api/tags")

        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in candidate_urls:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        models = extract_model_ids_from_response(resp.json())
                        if models:
                            return ModelsResponse(models=models)
                except Exception:
                    continue
    except Exception as exc:
        logger.warning(
            "Failed to fetch models from transcription api_base %s: %s", api_base, exc
        )

    return ModelsResponse(models=fallback_models)


@router.get("/api/config/transcription", response_model=TranscriptionConfigResponse)
async def get_transcription_config() -> Any:
    """Get the current voice transcription runtime configuration.

    Reads go through the StateBackend's config_store (see
    :func:`omniscribe.api.routers.config._load_config_from_store`) so
    a value written by another worker is visible here in a multi-worker
    deployment.
    """
    from omniscribe.api.services.security_config import SecuritySettings

    sec = SecuritySettings.from_env()
    config = _load_config_from_store()
    auth_tok = (
        config.get("transcription_auth_token")
        if "transcription_auth_token" in config
        else sec.transcription_auth_token
    )

    return TranscriptionConfigResponse(
        transcription_api_base=str(
            config.get("transcription_api_base", "https://api.openai.com/v1")
        ),
        transcription_api_key=_mask_api_key(
            str(config.get("transcription_api_key", ""))
        )
        or "",
        transcription_model=str(config.get("transcription_model", "whisper-1")),
        transcription_engine=str(config.get("transcription_engine", "api")),
        transcription_auth_token=_mask_api_key(auth_tok),
        language=str(config.get("transcription_language", "")) or None,
        prompt=str(config.get("transcription_prompt", "")) or None,
        temperature=float(config.get("transcription_temperature", 0.0)),
    )


@router.post("/api/config/transcription", response_model=TranscriptionConfigResponse)
async def update_transcription_config(
    body: TranscriptionConfigUpdate, response: Response
) -> Any:
    """Update runtime configuration for voice transcription.

    Writes go through the StateBackend's config_store (see
    :func:`omniscribe.api.routers.config._persist_config`) so every
    worker sees the new value in a multi-worker deployment. When the
    active backend is the default in-memory one, the request is
    refused with a 503 + a remediation message.
    """
    if body.api_base is not None and not (await is_ssrf_target(body.api_base)).allowed:
        raise HTTPException(status_code=403, detail=SAFE_API_BASE_ERROR)
    updates: dict[str, Any] = {}
    if body.api_base is not None:
        updates["transcription_api_base"] = body.api_base
    if body.transcription_api_key is not None:
        updates["transcription_api_key"] = body.transcription_api_key
    elif body.api_key is not None:
        updates["transcription_api_key"] = body.api_key
    if body.model is not None:
        updates["transcription_model"] = body.model
    if body.engine is not None:
        updates["transcription_engine"] = body.engine.value
    if body.language is not None:
        updates["transcription_language"] = body.language
    if body.prompt is not None:
        updates["transcription_prompt"] = body.prompt
    if body.temperature is not None:
        updates["transcription_temperature"] = body.temperature
    if updates:
        try:
            _persist_config(updates)
        except _ConfigBackendIncompatible:
            raise HTTPException(
                status_code=503, detail=_CONFIG_BACKEND_INCOMPATIBLE_MESSAGE
            ) from None

    return await get_transcription_config()
