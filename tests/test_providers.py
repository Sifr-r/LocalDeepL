"""Tests for LLM provider catalog and provider discovery routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from local_deepl.core.providers import PROVIDERS_CATALOG, get_provider
from local_deepl.server import create_app


def test_providers_catalog_structure():
    """Verify that all catalog providers have valid fields, API base, and categories."""
    assert len(PROVIDERS_CATALOG) >= 15
    provider_ids = [p.id for p in PROVIDERS_CATALOG]
    assert "alibaba-china" in provider_ids
    assert "alibaba-singapore" in provider_ids
    assert "alibaba-us" in provider_ids
    assert "zai-china" in provider_ids
    assert "zai-international" in provider_ids
    assert "kimi" in provider_ids
    assert "minimax-china" in provider_ids
    assert "deepseek" in provider_ids
    assert "openai" in provider_ids
    assert "google-gemini" in provider_ids
    assert "lmstudio" in provider_ids
    assert "ollama" in provider_ids


def test_get_provider_lookup():
    """Verify helper lookup by provider_id."""
    alibaba = get_provider("alibaba-china")
    assert alibaba is not None
    assert alibaba.name == "Alibaba Cloud Model Studio - China"
    assert "dashscope.aliyuncs.com" in alibaba.api_base
    assert alibaba.get_api_key_url is not None

    nonexistent = get_provider("unknown-provider-id")
    assert nonexistent is None


def test_list_providers_api_route():
    """Verify GET /api/providers returns full provider catalog."""
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    providers = data["providers"]
    assert len(providers) >= 15
    names = [p["name"] for p in providers]
    assert "Alibaba Cloud Model Studio - China" in names
    assert "Kimi (Moonshot AI)" in names
    assert "Z.ai - China (Zhipu BigModel)" in names
    assert "OpenAI" in names


def test_get_single_provider_api_route():
    """Verify GET /api/providers/{provider_id} route."""
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/providers/kimi")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "kimi"
    assert data["api_base"] == "https://api.moonshot.cn/v1"
    assert data["get_api_key_url"] == "https://platform.moonshot.cn/console/api-keys"

    res_404 = client.get("/api/providers/invalid-id")
    assert res_404.status_code == 404
