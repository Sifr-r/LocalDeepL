"""Providers plugin: catalog shape, discovery, active provider, routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.config import load_settings
from omniscribe.harness.context import Context
from omniscribe.plugins import providers as prov
from omniscribe.plugins.providers import (
    PROVIDER_TEMPLATES,
    ProviderManager,
    ProviderManagerImpl,
    build_providers_router,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHttpClient:
    """Records discovery calls and answers with a canned payload."""

    def __init__(
        self, payload: dict[str, Any] | None = None, *, fail: Exception | None = None
    ) -> None:
        self.payload = payload or {}
        self.fail = fail
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.calls.append((url, dict(headers or {})))
        if self.fail is not None:
            raise self.fail
        return _FakeResponse(self.payload)

    async def aclose(self) -> None:
        return None


def _manager(
    client: FakeHttpClient | None = None,
) -> tuple[ProviderManagerImpl, FakeHttpClient]:
    http = client or FakeHttpClient()
    return (
        ProviderManagerImpl(
            load_settings(),
            discovery_timeout_seconds=1.0,
            http_client=http,  # type: ignore[arg-type]
        ),
        http,
    )


# -- catalog ------------------------------------------------------------------


def test_list_providers_maps_every_template_onto_preset_shape() -> None:
    manager, _ = _manager()
    presets = manager.list_providers()
    assert len(presets) == len(PROVIDER_TEMPLATES)
    ids = {preset["id"] for preset in presets}
    assert ids == set(PROVIDER_TEMPLATES)
    for preset in presets:
        assert set(preset) == {
            "id",
            "name",
            "category",
            "description",
            "recommended_base_url",
            "api_base",
            "default_model",
            "requires_key",
            "notes",
        }
    lmstudio = next(preset for preset in presets if preset["id"] == "lmstudio")
    assert lmstudio["category"] == "local"
    assert lmstudio["requires_key"] is False
    openai = next(preset for preset in presets if preset["id"] == "openai")
    assert openai["category"] == "cloud"
    assert openai["requires_key"] is True


def test_get_provider_returns_none_for_unknown_id() -> None:
    manager, _ = _manager()
    assert manager.get_provider("lmstudio") is not None
    assert manager.get_provider("nope") is None


# -- active provider ----------------------------------------------------------


def test_get_active_reflects_runtime_settings() -> None:
    manager, _ = _manager()
    active = manager.get_active()
    settings = load_settings()
    assert active == {
        "api_base": settings.llm_api_base,
        "model": settings.llm_model,
    }


def test_set_active_writes_back_into_settings() -> None:
    manager, _ = _manager()
    active = manager.set_active(
        provider_id="openai", api_base="https://api.openai.com/v1", model="gpt-4o"
    )
    assert active == {"api_base": "https://api.openai.com/v1", "model": "gpt-4o"}
    assert manager.get_active() == active
    # the shared settings object observed the write-through
    assert manager._settings.llm_model == "gpt-4o"


# -- discovery ------------------------------------------------------------------


async def test_discover_models_openai_compatible_parses_data_ids() -> None:
    manager, http = _manager(
        FakeHttpClient({"data": [{"id": "model-a"}, {"id": "model-b"}]})
    )
    result = await manager.discover_models("openai", api_key="sk-test")
    assert result == {"models": ["model-a", "model-b"], "error": None}
    url, headers = http.calls[0]
    # H-1 audit fix: the URL host is rewritten to the SSRF-validated IP
    # so a DNS-rebinding attacker cannot bypass the guard. The original
    # hostname is preserved in the ``Host`` header. ``api.openai.com``
    # resolves to multiple Cloudflare IPs at different times; we accept
    # any of them.
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    assert all(c in "0123456789." for c in host) or ":" in host, (
        f"expected IP literal, got {host!r}"
    )
    assert urlsplit(url).path == "/v1/models"
    assert "api.openai.com" in headers.get("Host", "")
    assert "Bearer sk-test" in headers["Authorization"]


async def test_discover_models_ollama_uses_api_tags() -> None:
    manager, http = _manager(
        FakeHttpClient({"models": [{"name": "llama3"}, {"name": "qwen2.5vl"}]})
    )
    result = await manager.discover_models("ollama")
    assert result == {"models": ["llama3", "qwen2.5vl"], "error": None}
    url, headers = http.calls[0]
    # H-1 audit fix: URL host rewritten to the SSRF-resolved IP.
    # On this test host, ``localhost`` resolves to ``::1`` (IPv6) but
    # could resolve to ``127.0.0.1`` on others; we accept either, and
    # assert the path + Host header are preserved.
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    assert host in {"127.0.0.1", "::1"}, f"expected loopback IP, got {host!r}"
    assert urlsplit(url).port == 11434
    assert urlsplit(url).path == "/api/tags"
    # The Host header preserves the original hostname so virtual
    # hosting / HTTPS SNI still match.
    assert headers.get("Host") == "localhost"


async def test_discover_models_failure_falls_back_to_presets() -> None:
    manager, _ = _manager(FakeHttpClient(fail=httpx.ConnectError("connection refused")))
    result = await manager.discover_models("lmstudio")
    assert result["models"] == list(PROVIDER_TEMPLATES["lmstudio"].models)
    assert result["error"] is not None


async def test_discover_models_without_base_url_reports_error() -> None:
    manager, http = _manager()
    result = await manager.discover_models("azure")
    assert result["models"] == []
    assert result["error"] == "no base URL for provider"
    assert http.calls == []


# -- validate (direct unit tests, no route) ----------------------------------


async def test_validate_ollama_probes_api_tags_endpoint() -> None:
    """The ollama provider must hit /api/tags, not the OpenAI-style /models."""
    manager, http = _manager(
        FakeHttpClient({"models": [{"name": "llama3"}, {"name": "qwen2.5vl"}]})
    )
    result = await manager.validate("ollama", api_base="")
    assert result.valid is True
    assert result.model_count == 2
    assert result.error is None
    assert len(http.calls) == 1
    url, headers = http.calls[0]
    # H-1 audit fix: URL host rewritten to SSRF-resolved IP.
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    assert host in {"127.0.0.1", "::1"}, f"expected loopback IP, got {host!r}"
    assert urlsplit(url).port == 11434
    assert urlsplit(url).path == "/api/tags"
    assert headers.get("Host") == "localhost"


async def test_validate_openai_compatible_probes_models_endpoint() -> None:
    manager, http = _manager(
        FakeHttpClient({"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})
    )
    result = await manager.validate(
        "openai", api_base="https://api.openai.com/v1", api_key="sk-test"
    )
    assert result.valid is True
    assert result.model_count == 2
    assert result.error is None
    url, headers = http.calls[0]
    # H-1 audit fix: URL host rewritten to SSRF-resolved IP.
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    # ``api.openai.com`` resolves to multiple Cloudflare IPs at
    # different times; we accept any IP literal.
    assert all(c in "0123456789." for c in host) or ":" in host, (
        f"expected IP literal, got {host!r}"
    )
    assert urlsplit(url).path == "/v1/models"
    assert headers.get("Host") == "api.openai.com"
    assert headers["Authorization"] == "Bearer sk-test"


async def test_validate_unknown_provider_short_circuits() -> None:
    manager, http = _manager()
    result = await manager.validate("bogus", api_base="http://does.not.matter")
    assert result.valid is False
    assert result.model_count == 0
    assert result.error == "unknown provider"
    assert http.calls == []


async def test_validate_connection_error_returns_classified_failure() -> None:
    manager, _ = _manager(FakeHttpClient(fail=httpx.ConnectError("connection refused")))
    result = await manager.validate("lmstudio", api_base="http://127.0.0.1:1/v1")
    assert result.valid is False
    assert result.model_count == 0
    assert result.error is not None
    assert "connection" in result.error.lower()


# -- routes ------------------------------------------------------------------


def test_router_catalog_details_and_models() -> None:
    manager, _ = _manager(
        FakeHttpClient({"data": [{"id": "model-a"}, {"id": "model-b"}]})
    )
    app = FastAPI()
    app.include_router(build_providers_router(manager))
    with TestClient(app) as client:
        listing = client.get("/api/providers")
        assert listing.status_code == 200
        assert len(listing.json()["providers"]) == len(PROVIDER_TEMPLATES)

        details = client.get("/api/providers/lmstudio")
        assert details.status_code == 200
        assert details.json()["id"] == "lmstudio"

        assert client.get("/api/providers/nope").status_code == 404
        assert client.get("/api/providers/nope/models").status_code == 404

        models = client.get("/api/providers/openai/models")
        assert models.status_code == 200
        assert models.json() == {"models": ["model-a", "model-b"], "error": None}


def test_provider_models_accepts_x_provider_api_key_header() -> None:
    manager, http = _manager(FakeHttpClient({"data": [{"id": "model-a"}]}))
    app = FastAPI()
    app.include_router(build_providers_router(manager))
    with TestClient(app) as client:
        response = client.get(
            "/api/providers/openai/models",
            headers={"X-Provider-Api-Key": "sk-header-key"},
        )
        assert response.status_code == 200
        assert response.json() == {"models": ["model-a"], "error": None}
        assert len(http.calls) == 1
        _, headers = http.calls[0]
        assert headers["Authorization"] == "Bearer sk-header-key"


def test_provider_models_accepts_authorization_bearer_header() -> None:
    manager, http = _manager(FakeHttpClient({"data": [{"id": "model-a"}]}))
    app = FastAPI()
    app.include_router(build_providers_router(manager))
    with TestClient(app) as client:
        response = client.get(
            "/api/providers/openai/models",
            headers={"Authorization": "Bearer sk-bearer-key"},
        )
        assert response.status_code == 200
        assert response.json() == {"models": ["model-a"], "error": None}
        assert len(http.calls) == 1
        _, headers = http.calls[0]
        assert headers["Authorization"] == "Bearer sk-bearer-key"


def test_provider_models_passes_resolved_key_to_discover_models() -> None:
    manager, _ = _manager()
    manager.discover_models = AsyncMock(
        return_value={"models": ["mock-m"], "error": None}
    )  # type: ignore[method-assign]
    app = FastAPI()
    app.include_router(build_providers_router(manager))
    with TestClient(app) as client:
        # 1. X-Provider-Api-Key header takes highest precedence
        resp1 = client.get(
            "/api/providers/openai/models?api_key=query-key",
            headers={
                "X-Provider-Api-Key": "header-x-key",
                "Authorization": "Bearer header-bearer-key",
            },
        )
        assert resp1.status_code == 200
        manager.discover_models.assert_awaited_with(
            "openai", api_base=None, api_key="header-x-key"
        )

        # 2. Authorization: Bearer takes precedence over query param
        resp2 = client.get(
            "/api/providers/openai/models?api_key=query-key",
            headers={"Authorization": "Bearer header-bearer-key"},
        )
        assert resp2.status_code == 200
        manager.discover_models.assert_awaited_with(
            "openai", api_base=None, api_key="header-bearer-key"
        )

        # 3. Non-Bearer Authorization falls back to query param
        resp3 = client.get(
            "/api/providers/openai/models?api_key=query-key",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp3.status_code == 200
        manager.discover_models.assert_awaited_with(
            "openai", api_base=None, api_key="query-key"
        )

        # 4. Query param used when no headers provided
        resp4 = client.get("/api/providers/openai/models?api_key=query-key")
        assert resp4.status_code == 200
        manager.discover_models.assert_awaited_with(
            "openai", api_base=None, api_key="query-key"
        )


def test_bearer_token_helper() -> None:
    assert prov._bearer_token("Bearer sk-test-token") == "sk-test-token"
    assert prov._bearer_token("Bearer   sk-test-token  ") == "sk-test-token"
    assert prov._bearer_token("Bearer ") == ""
    assert prov._bearer_token("Basic dXNlcjpwYXNz") is None
    assert prov._bearer_token(None) is None
    assert prov._bearer_token("") is None


async def test_plugin_registers_provider_manager_service() -> None:
    ctx = Context()
    await ctx.plugin(prov.ProvidersPlugin(), config={})
    manager = ctx.inject(ProviderManager)
    assert len(manager.list_providers()) == len(PROVIDER_TEMPLATES)
    assert ctx.routes()
    await ctx.dispose()


# -- POST /api/providers/active ---------------------------------------------


def test_set_active_route_writes_through_settings(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
            "apiKey": "sk-test-1234",
            "model": "allenai/olmocr-2-7b",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider_id"] == "lmstudio"
    # Boot settings are seeded by the api_client fixture; assert write-through
    # by reaching the harness-owned manager the same way the unit test does.
    manager = api_client.app.state.context.inject(ProviderManager)  # type: ignore[attr-defined]
    assert manager._settings.llm_api_base == "http://localhost:1234/v1"
    assert manager._settings.llm_api_key == "sk-test-1234"
    assert manager._settings.llm_model == "allenai/olmocr-2-7b"


def test_set_active_route_with_omitted_api_key(api_client: TestClient) -> None:
    # First write a sentinel api_key.
    api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
            "apiKey": "sk-sentinel",
            "model": "allenai/olmocr-2-7b",
        },
    )
    # Now post without api_key; sentinel must be unchanged while base + model flip.
    response = api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:9999/v1",
            "model": "different-model",
        },
    )
    assert response.status_code == 200
    # Reach the harness-owned manager (same pattern as
    # ``test_set_active_writes_back_into_settings``) and confirm partial writes.
    manager = api_client.app.state.context.inject(ProviderManager)  # type: ignore[attr-defined]
    assert manager._settings.llm_api_key == "sk-sentinel"
    assert manager._settings.llm_api_base == "http://localhost:9999/v1"
    assert manager._settings.llm_model == "different-model"


# -- POST /api/providers/validate --------------------------------------------


def test_validate_route_returns_model_count(api_client, monkeypatch) -> None:
    """Stub httpx so the live probe never hits the network."""
    import httpx

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, headers=None):
            return _FakeResponse({"data": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]})

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    response = api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["model_count"] == 3


def test_validate_route_handles_offline_provider(api_client, monkeypatch) -> None:
    import httpx

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, headers=None):
            raise httpx.ConnectError("connection refused")

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    response = api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "openai",
            "apiBase": "http://127.0.0.1:1/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body.get("error")


def test_validate_route_unknown_provider(api_client) -> None:
    response = api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "bogus",
            "apiBase": "http://localhost:1234/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"] == "unknown provider"
