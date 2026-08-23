"""``/api/models*`` routes — model discovery for the four backends.

Phase C / Task 9: extracted from ``routers/config.py`` (3 routes) +
``routers/transcription.py`` (1 route) to consolidate the
``/api/models*`` family in one place. The 4 routes here share a single
responsibility — listing available models for the four backends
(general, OCR, translation, transcription) — and nothing else.

Backwards-compat re-exports in ``routers/config.py`` and
``routers/transcription.py`` keep old import paths working for plugin
context providers + tests.

The bodies below are lifted verbatim from the source modules with only
import-path adjustments (the private ``_load_config_from_store`` was
replaced with the public ``load_config_from_store`` from
:mod:`omniscribe.api.services.helpers` per Task 8).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.api.schemas.responses import ModelsResponse
from omniscribe.api.services.envelope import SSRFBlocked
from omniscribe.api.services.helpers import load_config_from_store
from omniscribe.api.services.uploads import SERVER_ERROR_MESSAGE
from omniscribe.utils.security import is_ssrf_target

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model discovery helper (moved from routers/config.py)
# ---------------------------------------------------------------------------


async def _discover_models_for_endpoint(
    api_base: str, api_key: str | None = None
) -> list[str]:
    """Query available models from an arbitrary LLM endpoint with multi-URL and multi-format support."""
    import httpx

    from omniscribe.api.services.provider_manager import extract_model_ids_from_response

    base = api_base.rstrip("/")
    headers = {}
    if api_key and api_key != "lm-studio":
        headers["Authorization"] = f"Bearer {api_key}"

    candidate_urls: list[str] = []
    if base.endswith("/v1"):
        candidate_urls.append(f"{base}/models")
    else:
        candidate_urls.append(f"{base}/v1/models")
        candidate_urls.append(f"{base}/models")
    candidate_urls.append(f"{base}/api/tags")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in candidate_urls:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        models = extract_model_ids_from_response(resp.json())
                        if models:
                            return models
                except Exception:
                    continue
    except Exception:
        pass

    try:
        from openai import AsyncOpenAI

        client_sdk = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key or "lm-studio",
        )
        response = await client_sdk.models.list()
        if response.data:
            return [m.id for m in response.data]
    except Exception:
        pass

    return []


# ---------------------------------------------------------------------------
# /api/models  — general-purpose model discovery
# ---------------------------------------------------------------------------


@router.get("/api/models")
async def list_models():
    """Query available models using the active provider from ProviderManager or configured api_base."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    active_provider = mgr.get_active_provider()
    config = load_config_from_store()

    custom_base = config.get("api_base")
    if custom_base and custom_base != active_provider.api_url:
        ssrf_check = await is_ssrf_target(custom_base)
        if not ssrf_check.allowed:
            raise SSRFBlocked(url=custom_base, reason=ssrf_check.reason or "blocked")
        try:
            models = await _discover_models_for_endpoint(
                custom_base, config.get("api_key")
            )
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("Model discovery failed")
            return JSONResponse(
                status_code=200,
                content={
                    "models": [],
                    "error": "internal_error",
                    "detail": SERVER_ERROR_MESSAGE,
                },
            )

    if active_provider.api_url:
        ssrf_check = await is_ssrf_target(active_provider.api_url)
        if not ssrf_check.allowed:
            raise SSRFBlocked(
                url=active_provider.api_url,
                reason=ssrf_check.reason or "blocked",
            )

    try:
        models = await mgr.async_list_provider_models(active_provider.id)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("Model discovery failed")
        return JSONResponse(
            status_code=200,
            content={
                "models": [],
                "error": "internal_error",
                "detail": SERVER_ERROR_MESSAGE,
            },
        )


# ---------------------------------------------------------------------------
# /api/models/ocr  — OCR-namespace model discovery
# ---------------------------------------------------------------------------


@router.get("/api/models/ocr")
async def list_ocr_models():
    """Model discovery for the OCR namespace (uses ProviderManager or ``ocr_api_base``)."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    config = load_config_from_store()
    ocr_provider_id = config.get("ocr_provider")

    if ocr_provider_id and mgr.get_provider(ocr_provider_id):
        provider = mgr.get_provider(ocr_provider_id)
        if provider and provider.api_url:
            ssrf_check = await is_ssrf_target(provider.api_url)
            if not ssrf_check.allowed:
                raise SSRFBlocked(
                    url=provider.api_url,
                    reason=ssrf_check.reason or "blocked",
                )
        try:
            models = await mgr.async_list_provider_models(ocr_provider_id)
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("OCR model discovery failed")
            return JSONResponse(
                status_code=200,
                content={
                    "models": [],
                    "error": "internal_error",
                    "detail": SERVER_ERROR_MESSAGE,
                },
            )

    api_base = config.get("ocr_api_base") or config["api_base"]
    api_key = config.get("ocr_api_key") or config["api_key"]
    ssrf_check = await is_ssrf_target(api_base)
    if not ssrf_check.allowed:
        raise SSRFBlocked(url=api_base, reason=ssrf_check.reason or "blocked")
    try:
        models = await _discover_models_for_endpoint(api_base, api_key)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("OCR model discovery failed")
        return JSONResponse(
            status_code=200,
            content={
                "models": [],
                "error": "internal_error",
                "detail": SERVER_ERROR_MESSAGE,
            },
        )


# ---------------------------------------------------------------------------
# /api/models/translation  — translation-namespace model discovery
# ---------------------------------------------------------------------------


@router.get("/api/models/translation")
async def list_translation_models():
    """Model discovery for the translation namespace (uses ProviderManager or ``translation_api_base``)."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    config = load_config_from_store()
    trans_provider_id = config.get("translation_provider")

    if trans_provider_id and mgr.get_provider(trans_provider_id):
        provider = mgr.get_provider(trans_provider_id)
        if provider and provider.api_url:
            ssrf_check = await is_ssrf_target(provider.api_url)
            if not ssrf_check.allowed:
                raise SSRFBlocked(
                    url=provider.api_url,
                    reason=ssrf_check.reason or "blocked",
                )
        try:
            models = await mgr.async_list_provider_models(trans_provider_id)
            return JSONResponse(content={"models": models})
        except Exception:
            logger.exception("Translation model discovery failed")
            return JSONResponse(
                status_code=200,
                content={
                    "models": [],
                    "error": "internal_error",
                    "detail": SERVER_ERROR_MESSAGE,
                },
            )

    api_base = config.get("translation_api_base") or config["api_base"]
    api_key = config.get("translation_api_key") or config["api_key"]
    ssrf_check = await is_ssrf_target(api_base)
    if not ssrf_check.allowed:
        raise SSRFBlocked(url=api_base, reason=ssrf_check.reason or "blocked")
    try:
        models = await _discover_models_for_endpoint(api_base, api_key)
        return JSONResponse(content={"models": models})
    except Exception:
        logger.exception("Translation model discovery failed")
        return JSONResponse(
            status_code=200,
            content={
                "models": [],
                "error": "internal_error",
                "detail": SERVER_ERROR_MESSAGE,
            },
        )


# ---------------------------------------------------------------------------
# /api/models/transcription  — transcription-namespace model discovery
# (moved from routers/transcription.py)
# ---------------------------------------------------------------------------


@router.get("/api/models/transcription", response_model=ModelsResponse)
async def get_transcription_models() -> Any:
    """Discover available audio transcription models from the configured backend endpoint."""
    config = load_config_from_store()
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


__all__ = [
    "_discover_models_for_endpoint",
    "get_transcription_models",
    "list_models",
    "list_ocr_models",
    "list_translation_models",
    "router",
]
