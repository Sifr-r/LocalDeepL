"""FastAPI router for LLM provider discovery and catalog management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from omniscribe.api.schemas.requests import (
    ActiveProviderUpdate,
    ProviderConfig,
    ProviderCreateRequest,
    ProviderTemplate,
)
from omniscribe.api.services.provider_manager import get_provider_manager
from omniscribe.api.services.security import SAFE_API_BASE_ERROR
from omniscribe.utils.security import is_ssrf_target

router = APIRouter()
logger = logging.getLogger(__name__)


def _format_provider_config(p: ProviderConfig) -> dict[str, Any]:
    data = p.model_dump(mode="json")
    data["api_base"] = p.api_url
    data["name"] = p.display_name
    from omniscribe.core.providers import get_provider as get_cat_provider

    cat = get_cat_provider(p.id)
    if cat and cat.get_api_key_url:
        data["get_api_key_url"] = cat.get_api_key_url
    return data


def _format_provider_template(t: ProviderTemplate) -> dict[str, Any]:
    data = t.model_dump(mode="json")
    data["api_base"] = t.api_url
    data["name"] = t.display_name
    return data


@router.get("/api/providers")
async def get_providers() -> JSONResponse:
    """Return list of all configured ProviderConfig objects."""
    mgr = get_provider_manager()
    providers = mgr.get_providers()
    return JSONResponse(
        content={"providers": [_format_provider_config(p) for p in providers]}
    )


@router.get("/api/providers/templates")
async def get_provider_templates() -> JSONResponse:
    """Return list of all ProviderTemplate objects."""
    mgr = get_provider_manager()
    templates = mgr.get_templates()
    return JSONResponse(
        content={"templates": [_format_provider_template(t) for t in templates]}
    )


@router.get("/api/providers/active")
async def get_active_provider() -> JSONResponse:
    """Return current ProviderConfig active provider."""
    mgr = get_provider_manager()
    active = mgr.get_active_provider()
    return JSONResponse(content=_format_provider_config(active))


@router.post("/api/providers/active")
async def update_active_provider(body: ActiveProviderUpdate) -> JSONResponse:
    """Update active provider and optional model selection."""
    mgr = get_provider_manager()
    try:
        updated = mgr.set_active_provider(body.provider_id, model=body.model)
        return JSONResponse(content=_format_provider_config(updated))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail=f"Provider '{body.provider_id}' not found"
        ) from exc


@router.post("/api/providers")
async def create_or_update_provider(body: ProviderCreateRequest) -> JSONResponse:
    """Create or update a provider configuration."""
    if await is_ssrf_target(body.api_url):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})

    mgr = get_provider_manager()
    created = mgr.create_provider(body)
    return JSONResponse(content=_format_provider_config(created))


@router.delete("/api/providers/{provider_id}")
async def delete_provider(provider_id: str) -> JSONResponse:
    """Delete custom provider (or disable template provider)."""
    mgr = get_provider_manager()
    success = mgr.delete_provider(provider_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )
    return JSONResponse(content={"status": "deleted", "provider_id": provider_id})


@router.get("/api/providers/{provider_id}/models")
async def list_provider_models(provider_id: str) -> JSONResponse:
    """Query model list for the given provider (handling openai_compatible, anthropic_compatible, ollama_compatible)."""
    mgr = get_provider_manager()
    provider = mgr.get_provider(provider_id)
    if provider is None:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )

    if provider.api_url and await is_ssrf_target(provider.api_url):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})

    models = await mgr.async_list_provider_models(provider_id)
    return JSONResponse(content={"models": models})


@router.get("/api/providers/{provider_id}")
async def get_provider_details(provider_id: str) -> JSONResponse:
    """Return details for a specific provider ID or 404."""
    mgr = get_provider_manager()
    provider = mgr.get_provider(provider_id)
    if provider is None:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )
    return JSONResponse(content=_format_provider_config(provider))


__all__ = ["router"]
