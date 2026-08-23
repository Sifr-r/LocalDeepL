"""Integration tests for Provider REST API Router endpoints."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from omniscribe.api.services.envelope import register_envelope_handlers
from omniscribe.server import create_app
from omniscribe.utils.security import SSRFCheckResult


def _build_client() -> TestClient:
    """Create the app and register envelope handlers so swept error sites
    return the canonical envelope shape rather than bubbling up as 500s.
    """
    app = create_app()
    register_envelope_handlers(app)
    return TestClient(app)


def test_get_providers_route():
    client = _build_client()
    res = client.get("/api/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    providers = data["providers"]
    assert isinstance(providers, list)
    assert len(providers) > 0
    ids = [p["id"] for p in providers]
    assert "openai" in ids
    assert "lmstudio" in ids


def test_get_provider_templates_route():
    client = _build_client()
    res = client.get("/api/providers/templates")
    assert res.status_code == 200
    data = res.json()
    assert "templates" in data
    templates = data["templates"]
    assert isinstance(templates, list)
    assert len(templates) >= 11


def test_get_active_provider_route():
    client = _build_client()
    res = client.get("/api/providers/active")
    assert res.status_code == 200
    data = res.json()
    assert "id" in data
    assert "api_url" in data or "api_base" in data


def test_update_active_provider_route():
    client = _build_client()

    payload = {"provider_id": "groq", "model": "llama-3.2-90b-vision-preview"}
    res = client.post("/api/providers/active", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "groq"

    # Test invalid active provider
    res_404 = client.post(
        "/api/providers/active", json={"provider_id": "non-existent-provider-id"}
    )
    assert res_404.status_code == 404


def test_create_or_update_provider_route():
    client = _build_client()

    payload = {
        "id": "my-custom-provider",
        "display_name": "My Custom Provider",
        "format": "openai_compatible",
        "api_url": "http://localhost:8080/v1",
        "api_key": "secret-key",
        "models": ["model-a", "model-b"],
    }
    with patch(
        "omniscribe.api.routers.providers.is_ssrf_target",
        return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1"),
    ):
        res = client.post("/api/providers", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "my-custom-provider"
        assert data["api_url"] == "http://localhost:8080/v1"

    # SSRF rejection test
    with patch(
        "omniscribe.api.routers.providers.is_ssrf_target",
        return_value=SSRFCheckResult(
            allowed=False, resolved_ip=None, reason="mock-blocked"
        ),
    ):
        res_ssrf = client.post("/api/providers", json=payload)
        assert res_ssrf.status_code == 403
        assert "error" in res_ssrf.json()


def test_delete_provider_route():
    client = _build_client()

    payload = {
        "id": "temp-provider-to-delete",
        "display_name": "Temp Provider",
        "api_url": "http://localhost:8080/v1",
    }
    with patch(
        "omniscribe.api.routers.providers.is_ssrf_target",
        return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1"),
    ):
        client.post("/api/providers", json=payload)

        # Delete it
        res = client.delete("/api/providers/temp-provider-to-delete")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

    # Delete non-existent
    res_404 = client.delete("/api/providers/non-existent-id")
    assert res_404.status_code == 404


def test_get_provider_models_route():
    client = _build_client()

    with patch(
        "omniscribe.api.services.provider_manager.ProviderManager.list_provider_models",
        return_value=["model-1", "model-2"],
    ):
        with patch(
            "omniscribe.api.routers.providers.is_ssrf_target",
            return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1"),
        ):
            res = client.get("/api/providers/openai/models")
            assert res.status_code == 200
            data = res.json()
            assert "models" in data
            assert "model-1" in data["models"]

    # 404 for unknown provider
    res_404 = client.get("/api/providers/unknown-provider/models")
    assert res_404.status_code == 404


def test_get_provider_details_route():
    client = _build_client()

    res = client.get("/api/providers/openai")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "openai"

    res_404 = client.get("/api/providers/unknown-provider")
    assert res_404.status_code == 404
