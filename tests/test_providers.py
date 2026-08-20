"""Tests for LLM provider catalog and provider discovery routes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omniscribe.core.providers import PROVIDERS_CATALOG, get_provider
from omniscribe.server import create_app


@pytest.fixture
def fresh_provider_manager(tmp_path: Path) -> Iterator[None]:
    """Reset the ProviderManager singleton to use a fresh tmp config file.

    The real `~/.config/omniscribe/providers.yaml` may have been written by
    a prior app run with stale values (e.g. legacy Alibaba / Novita /
    Together URLs that have since moved, or an old `minimax-international`
    entry that has been removed). Tests that exercise the live API must
    load the in-process templates, not the user's disk state.
    """
    from omniscribe.api.services.provider_manager import (
        get_provider_manager,
        reset_provider_manager,
    )

    reset_provider_manager()
    get_provider_manager(config_path=tmp_path / "providers.yaml")
    try:
        yield
    finally:
        reset_provider_manager()


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
    # 2026-08-19: workspace-dedicated Alibaba domain replaced the legacy
    # `dashscope.aliyuncs.com` shared host; display name and URL shape
    # both updated.
    assert alibaba.name == "Alibaba Cloud Model Studio - China (Beijing)"
    assert "maas.aliyuncs.com" in alibaba.api_base
    assert "{WorkspaceId}" in alibaba.api_base
    assert alibaba.get_api_key_url is not None

    # Kimi split into China (`kimi`) and Global (`kimi-global`) variants
    # on 2026-08-19; the China entry keeps the moonshot.cn host.
    kimi = get_provider("kimi")
    assert kimi is not None
    assert kimi.api_base == "https://api.moonshot.cn/v1"
    kimi_global = get_provider("kimi-global")
    assert kimi_global is not None
    assert kimi_global.api_base == "https://api.moonshot.ai/v1"

    nonexistent = get_provider("unknown-provider-id")
    assert nonexistent is None


def test_list_providers_api_route(fresh_provider_manager: None) -> None:
    """Verify GET /api/providers returns full provider catalog."""
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    providers = data["providers"]
    # 2026-08-19: 27 providers ported from OmniRoute (7 Local + 20
    # API-key + 1 kimi-global split), plus the 25 pre-existing
    # templates (-1 `minimax-international` removed) → 51 catalog
    # entries on the metadata layer. The API route merges the catalog
    # with the runtime config; we only assert a generous lower bound
    # here to keep this test resilient to further catalog growth.
    assert len(providers) >= 40
    names = [p["name"] for p in providers]
    assert "Alibaba Cloud Model Studio - China (Beijing)" in names
    assert "Kimi (Moonshot AI) - China" in names
    assert "Kimi (Moonshot AI) - Global" in names
    assert "Z.ai - China (Zhipu BigModel)" in names
    assert "OpenAI" in names


def test_get_single_provider_api_route(fresh_provider_manager: None) -> None:
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
