"""Providers plugin — LLM provider catalog, model discovery, active provider.

The catalog is settings-only (no disk persistence in this build). Model
discovery fans out to the provider's own ``GET {base}/models`` endpoint
(``/api/tags`` for Ollama) with a bounded timeout and falls back to the
static preset list on error — the frontend treats ``models`` as the source
of truth and ``error`` as a non-blocking warning.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from omniscribe.config import RuntimeSettings, load_settings
from omniscribe.core.llm.providers import ProviderConfig, ProviderFormatEnum
from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin

_LOGGER = logging.getLogger("omniscribe.plugins.providers")

_O = ProviderFormatEnum.OPENAI_COMPATIBLE
_A = ProviderFormatEnum.ANTHROPIC_COMPATIBLE
_OL = ProviderFormatEnum.OLLAMA_COMPATIBLE

#: Static catalog of known providers. Shapes mirror the frontend's
#: ``ProviderPreset`` contract (id, name, category, description,
#: recommended_base_url, default_model, requires_key, notes).
PROVIDER_TEMPLATES: dict[str, ProviderConfig] = {
    "lmstudio": ProviderConfig(
        id="lmstudio",
        display_name="LM Studio",
        format=_O,
        api_url="http://localhost:1234/v1",
        models=["allenai/olmocr-2-7b"],
        requires_auth=False,
    ),
    "openai": ProviderConfig(
        id="openai",
        display_name="OpenAI",
        format=_O,
        api_url="https://api.openai.com/v1",
        models=["gpt-4o", "gpt-4o-mini"],
    ),
    "anthropic": ProviderConfig(
        id="anthropic",
        display_name="Anthropic",
        format=_A,
        api_url="https://api.anthropic.com",
        models=["claude-sonnet-4-5"],
    ),
    "openrouter": ProviderConfig(
        id="openrouter",
        display_name="OpenRouter",
        format=_O,
        api_url="https://openrouter.ai/api/v1",
        models=[],
    ),
    "ollama": ProviderConfig(
        id="ollama",
        display_name="Ollama",
        format=_OL,
        api_url="http://localhost:11434",
        models=[],
        requires_auth=False,
    ),
    "databricks": ProviderConfig(
        id="databricks",
        display_name="Databricks",
        format=_O,
        api_url="",
        models=[],
    ),
    "azure": ProviderConfig(
        id="azure",
        display_name="Azure OpenAI",
        format=_O,
        api_url="",
        models=[],
    ),
    "groq": ProviderConfig(
        id="groq",
        display_name="Groq",
        format=_O,
        api_url="https://api.groq.com/openai/v1",
        models=[],
    ),
    "deepseek": ProviderConfig(
        id="deepseek",
        display_name="DeepSeek",
        format=_O,
        api_url="https://api.deepseek.com/v1",
        models=["deepseek-chat"],
    ),
    "minimax": ProviderConfig(
        id="minimax",
        display_name="MiniMax",
        format=_O,
        api_url="https://api.minimaxi.com/v1",
        models=[],
    ),
    "litellm": ProviderConfig(
        id="litellm",
        display_name="LiteLLM Proxy",
        format=_O,
        api_url="http://localhost:4000",
        models=[],
        requires_auth=False,
    ),
}

_CATEGORIES = {
    "lmstudio": "local",
    "ollama": "local",
    "litellm": "local",
}
_DESCRIPTIONS = {
    "lmstudio": "Local OpenAI-compatible server (the OmniScribe default).",
    "openai": "OpenAI hosted models.",
    "anthropic": "Anthropic hosted Claude models.",
    "openrouter": "Router across many hosted model vendors.",
    "ollama": "Local models via the Ollama runtime.",
    "databricks": "Databricks model-serving endpoints.",
    "azure": "Azure OpenAI service deployments.",
    "groq": "Groq inference endpoints.",
    "deepseek": "DeepSeek hosted models.",
    "minimax": "MiniMax hosted models.",
    "litellm": "Self-hosted LiteLLM proxy.",
}


def _to_preset(config: ProviderConfig) -> dict[str, Any]:
    """Map a catalog entry onto the frontend ``ProviderPreset`` shape."""
    return {
        "id": config.id,
        "name": config.display_name,
        "category": _CATEGORIES.get(config.id, "cloud"),
        "description": _DESCRIPTIONS.get(config.id, ""),
        "recommended_base_url": config.api_url,
        "api_base": config.api_url or None,
        "default_model": config.models[0] if config.models else "",
        "requires_key": config.requires_auth,
        "notes": "" if config.requires_auth else "No API key required.",
    }


@runtime_checkable
class ProviderManager(Protocol):
    """Provider catalog + discovery + active-provider seam."""

    def list_providers(self) -> list[dict[str, Any]]: ...

    def get_provider(self, provider_id: str) -> dict[str, Any] | None: ...

    async def discover_models(
        self,
        provider_id: str,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]: ...

    def get_active(self) -> dict[str, str]: ...

    def set_active(
        self, *, provider_id: str | None = None, api_base: str, model: str
    ) -> dict[str, str]: ...


class ProviderManagerImpl:
    """Settings-backed manager; discovery goes through ``httpx.AsyncClient``."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        discovery_timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._timeout = discovery_timeout_seconds
        self._client = http_client

    def list_providers(self) -> list[dict[str, Any]]:
        return [_to_preset(config) for config in PROVIDER_TEMPLATES.values()]

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        config = PROVIDER_TEMPLATES.get(provider_id)
        return _to_preset(config) if config is not None else None

    async def discover_models(
        self,
        provider_id: str,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        config = PROVIDER_TEMPLATES.get(provider_id)
        fallback = list(config.models) if config is not None else []
        base = (api_base or (config.api_url if config else "")).rstrip("/")
        if not base:
            return {"models": fallback, "error": "no base URL for provider"}
        url = f"{base}/api/tags" if provider_id == "ollama" else f"{base}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout)
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            finally:
                if self._client is None:
                    await client.aclose()
            if provider_id == "ollama":
                models = [str(entry["name"]) for entry in payload.get("models", [])]
            else:
                models = [str(entry["id"]) for entry in payload.get("data", [])]
            return {"models": models or fallback, "error": None}
        except Exception as exc:
            _LOGGER.warning("model discovery failed for %s: %s", provider_id, exc)
            return {"models": fallback, "error": str(exc)}

    def get_active(self) -> dict[str, str]:
        return {
            "api_base": self._settings.llm_api_base,
            "model": self._settings.llm_model,
        }

    def set_active(
        self, *, provider_id: str | None = None, api_base: str, model: str
    ) -> dict[str, str]:
        self._settings.llm_api_base = api_base
        self._settings.llm_model = model
        if provider_id:
            config = PROVIDER_TEMPLATES.get(provider_id)
            if config is not None and not api_base:
                self._settings.llm_api_base = config.api_url
        return self.get_active()


class ProvidersSchema(BaseModel):
    discovery_timeout_seconds: float = 5.0


def build_providers_router(manager: ProviderManagerImpl) -> APIRouter:
    """Catalog, details, and live model discovery routes."""
    router = APIRouter(prefix="/api/providers", tags=["providers"])

    @router.get("")
    async def list_providers() -> dict[str, list[dict[str, Any]]]:
        return {"providers": manager.list_providers()}

    @router.get("/{provider_id}")
    async def provider_details(provider_id: str) -> dict[str, Any]:
        preset = manager.get_provider(provider_id)
        if preset is None:
            raise HTTPException(status_code=404, detail="unknown provider")
        return preset

    @router.get("/{provider_id}/models")
    async def provider_models(
        provider_id: str,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        if manager.get_provider(provider_id) is None:
            raise HTTPException(status_code=404, detail="unknown provider")
        return await manager.discover_models(
            provider_id, api_base=api_base, api_key=api_key
        )

    return router


class ProvidersPlugin(Plugin):
    """Registers the settings-backed ProviderManager and its routes."""

    Schema = ProvidersSchema

    async def apply(self, ctx: Context) -> None:
        manager = ProviderManagerImpl(
            load_settings(),
            discovery_timeout_seconds=float(
                self.config.get("discovery_timeout_seconds", 5.0)
            ),
        )
        ctx.service(ProviderManager, manager)
        ctx.mount_router(build_providers_router(manager))


plugin = ProvidersPlugin()
