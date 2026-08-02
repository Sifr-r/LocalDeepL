"""FastAPI router for LLM provider discovery and catalog management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from local_deepl.core.providers import get_provider, list_providers

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/providers")
async def get_providers_catalog() -> JSONResponse:
    """Return all built-in LLM providers with preset endpoints and model lists."""
    catalog = list_providers()
    return JSONResponse(content={"providers": catalog})


@router.get("/api/providers/{provider_id}")
async def get_provider_details(provider_id: str) -> JSONResponse:
    """Return details for a specific LLM provider."""
    provider = get_provider(provider_id)
    if provider is None:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )
    return JSONResponse(content=provider.to_dict())


__all__ = ["router"]
