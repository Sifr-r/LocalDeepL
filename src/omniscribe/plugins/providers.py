"""Providers plugin — LLM provider catalog, model discovery, active provider.

The catalog is settings-only (no disk persistence in this build). Model
discovery fans out to the provider's own ``GET {base}/models`` endpoint
(``/api/tags`` for Ollama) with a bounded timeout and falls back to the
static preset list on error — the frontend treats ``models`` as the source
of truth and ``error`` as a non-blocking warning.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from omniscribe.config import RuntimeSettings, load_settings
from omniscribe.core.llm.providers import ProviderConfig, ProviderFormatEnum
from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.utils.security import is_ssrf_target

_LOGGER = logging.getLogger("omniscribe.plugins.providers")


def _rewrite_url_with_resolved_ip(url: str, resolved_ip: str) -> str:
    """Rewrite ``url`` so the connection goes to ``resolved_ip``.

    H-1 audit fix: ``httpx`` re-resolves DNS on connect, opening a
    DNS-rebinding TOCTOU window after ``is_ssrf_target`` validated the
    original hostname. We rewrite the URL to use the validated IP
    directly; callers should also preserve the original ``Host``
    header so HTTPS SNI / virtual hosting still match.

    The port is preserved (the validated IP replaces only the
    hostname slot). When ``url`` has no port we drop the port slot
    entirely so the rewritten URL is well-formed. IPv6 literals are
    wrapped in ``[ ]`` so urlsplit / httpx parse them correctly.
    """
    import ipaddress
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    port = parts.port
    try:
        ip = ipaddress.ip_address(resolved_ip)
        host_literal = (
            f"[{resolved_ip}]" if isinstance(ip, ipaddress.IPv6Address) else resolved_ip
        )
    except ValueError:
        host_literal = resolved_ip
    if port is None:
        netloc = host_literal
    else:
        netloc = f"{host_literal}:{port}"
    return urlunsplit(parts._replace(netloc=netloc))


def _base_hostname(base: str) -> str:
    """Return the hostname component of a base URL string, or empty."""
    from urllib.parse import urlsplit

    try:
        return (urlsplit(base).hostname or "").strip().lower()
    except ValueError:
        return ""


class SetActiveProviderRequest(BaseModel):
    """Payload for ``POST /api/providers/active``.

    ``populate_by_name=True`` accepts both the snake_case field names
    (the Flutter client's actual payload shape — see
    ``client/lib/data/models/provider_preset.dart`` ``SetActiveProviderRequest.toJson``)
    and the camelCase aliases (used by the curl smoke test and any
    non-Flutter client). The response is always snake_case because the
    response model has no aliases.
    """

    model_config = ConfigDict(populate_by_name=True)
    provider_id: str = Field(alias="providerId")
    api_base: str = Field(alias="apiBase")
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str


class SetActiveProviderResponse(BaseModel):
    """Ack for ``POST /api/providers/active`` — echoes the persisted state.

    snake_case output (no aliases); the Flutter client parses
    ``provider_id`` / ``api_base`` / ``model`` directly.
    """

    status: Literal["ok"]
    provider_id: str
    api_base: str
    model: str


class ValidateProviderRequest(BaseModel):
    """Payload for ``POST /api/providers/validate``.

    ``populate_by_name=True`` accepts both the snake_case field names
    (the Flutter client's actual payload shape — see
    ``client/lib/data/repositories/provider_repository.dart`` ``validateProvider``)
    and the camelCase aliases (used by the curl smoke test and any
    non-Flutter client). The response is always snake_case because the
    response model has no aliases.
    """

    model_config = ConfigDict(populate_by_name=True)
    provider_id: str = Field(alias="providerId")
    api_base: str = Field(alias="apiBase")
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None


class ValidateProviderResponse(BaseModel):
    """Result of ``POST /api/providers/validate`` — wire probe of provider reachability.

    snake_case output (no aliases); the Flutter client parses
    ``valid`` / ``model_count`` / ``error`` directly.
    """

    valid: bool
    model_count: int
    error: str | None = None


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
        self,
        *,
        provider_id: str | None = None,
        api_base: str,
        model: str,
        api_key: str | None = None,
    ) -> dict[str, str]: ...

    async def validate(
        self,
        provider_id: str,
        *,
        api_base: str,
        api_key: str | None = None,
    ) -> ValidateProviderResponse: ...


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
        ssrf_check = await is_ssrf_target(base)
        if not ssrf_check.allowed:
            return {
                "models": fallback,
                "error": f"Invalid provider URL (SSRF blocked: {ssrf_check.reason})",
            }
        url = f"{base}/api/tags" if provider_id == "ollama" else f"{base}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # H-1 audit fix: pin the TCP connection to the validated IP so
        # a DNS-rebinding attacker cannot bypass the SSRF check by
        # returning a different IP at connect time. The original
        # hostname is preserved in the ``Host`` header so HTTPS SNI /
        # virtual hosting still work. We rewrite only when the URL
        # hostname and the resolved IP differ (a no-op for IP-literal
        # URLs and for hosts that already resolved to themselves).
        if ssrf_check.resolved_ip and _base_hostname(base) != ssrf_check.resolved_ip:
            original_host = _base_hostname(base)
            url = _rewrite_url_with_resolved_ip(url, ssrf_check.resolved_ip)
            # Preserve the original Host header so virtual-hosted servers
            # and HTTPS SNI / cert verification still match.
            headers = {**headers, "Host": original_host}
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
        self,
        *,
        provider_id: str | None = None,
        api_base: str,
        model: str,
        api_key: str | None = None,
    ) -> dict[str, str]:
        self._settings.llm_api_base = api_base
        self._settings.llm_model = model
        if api_key:
            self._settings.llm_api_key = api_key
        if provider_id:
            config = PROVIDER_TEMPLATES.get(provider_id)
            if config is not None and not api_base:
                self._settings.llm_api_base = config.api_url
        return self.get_active()

    async def validate(
        self,
        provider_id: str,
        *,
        api_base: str,
        api_key: str | None = None,
    ) -> ValidateProviderResponse:
        config = PROVIDER_TEMPLATES.get(provider_id)
        if config is None:
            return ValidateProviderResponse(
                valid=False, model_count=0, error="unknown provider"
            )
        fallback = list(config.models)
        base = (api_base or config.api_url or "").rstrip("/")
        if not base:
            return ValidateProviderResponse(
                valid=False, model_count=0, error="no base URL for provider"
            )
        ssrf_check = await is_ssrf_target(base)
        if not ssrf_check.allowed:
            return ValidateProviderResponse(
                valid=False,
                model_count=0,
                error=f"Invalid provider URL (SSRF blocked: {ssrf_check.reason})",
            )
        url = f"{base}/api/tags" if provider_id == "ollama" else f"{base}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # H-1 audit fix: pin TCP to validated IP (see discover_models).
        if ssrf_check.resolved_ip and _base_hostname(base) != ssrf_check.resolved_ip:
            original_host = _base_hostname(base)
            url = _rewrite_url_with_resolved_ip(url, ssrf_check.resolved_ip)
            headers = {**headers, "Host": original_host}
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
            return ValidateProviderResponse(
                valid=True, model_count=len(models or fallback), error=None
            )
        except Exception as exc:
            _LOGGER.warning("validate failed for %s: %s", provider_id, exc)
            return ValidateProviderResponse(valid=False, model_count=0, error=str(exc))


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

    @router.post("/active", status_code=200)
    async def set_active(
        payload: SetActiveProviderRequest,
    ) -> SetActiveProviderResponse:
        manager.set_active(
            provider_id=payload.provider_id,
            api_base=payload.api_base,
            model=payload.model,
            api_key=payload.api_key,
        )
        return SetActiveProviderResponse(
            status="ok",
            provider_id=payload.provider_id,
            api_base=payload.api_base,
            model=payload.model,
        )

    @router.post("/validate", status_code=200)
    async def validate_provider(
        payload: ValidateProviderRequest,
    ) -> ValidateProviderResponse:
        return await manager.validate(
            payload.provider_id,
            api_base=payload.api_base,
            api_key=payload.api_key,
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
