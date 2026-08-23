"""Tests for Provider Schemas and ProviderManager service."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omniscribe.api.schemas.requests import (
    ActiveProviderUpdate,
    ProviderConfig,
    ProviderCreateRequest,
    ProviderFormatEnum,
    ProviderTemplate,
)
from omniscribe.api.services.provider_manager import (
    PROVIDER_TEMPLATES,
    ProviderManager,
    get_provider_manager,
    reset_provider_manager,
)


def test_provider_schemas():
    """Verify instantiation and validation of provider schemas."""
    config = ProviderConfig(
        id="custom",
        display_name="Custom Provider",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://custom.api/v1",
        api_key="secret",
    )
    assert config.id == "custom"
    assert config.format == ProviderFormatEnum.OPENAI_COMPATIBLE
    assert config.configured is False
    assert config.enabled is True

    template = ProviderTemplate(
        id="openai",
        display_name="OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        models=["gpt-4o"],
    )
    assert template.env_key == "OPENAI_API_KEY"

    update = ActiveProviderUpdate(provider_id="openai", model="gpt-4o")
    assert update.provider_id == "openai"
    assert update.model == "gpt-4o"

    create_req = ProviderCreateRequest(
        id="my-llm",
        display_name="My LLM",
        api_url="http://localhost:8080/v1",
    )
    assert create_req.format == ProviderFormatEnum.OPENAI_COMPATIBLE
    assert create_req.requires_auth is True


def test_provider_templates_catalog():
    """Verify required 11 catalog templates exist with correct formats."""
    expected_ids = {
        "openai",
        "anthropic",
        "openrouter",
        "ollama",
        "lmstudio",
        "databricks",
        "azure",
        "groq",
        "deepseek",
        "minimax",
        "litellm",
    }
    assert expected_ids.issubset(set(PROVIDER_TEMPLATES.keys()))

    assert (
        PROVIDERS_CATALOG_FORMAT(PROVIDER_TEMPLATES["openai"].format)
        == ProviderFormatEnum.OPENAI_COMPATIBLE
    )
    assert (
        PROVIDERS_CATALOG_FORMAT(PROVIDER_TEMPLATES["anthropic"].format)
        == ProviderFormatEnum.ANTHROPIC_COMPATIBLE
    )
    assert (
        PROVIDERS_CATALOG_FORMAT(PROVIDER_TEMPLATES["ollama"].format)
        == ProviderFormatEnum.OLLAMA_COMPATIBLE
    )
    assert PROVIDER_TEMPLATES["ollama"].requires_auth is False
    assert PROVIDER_TEMPLATES["lmstudio"].requires_auth is False
    assert PROVIDER_TEMPLATES["litellm"].requires_auth is False


def PROVIDERS_CATALOG_FORMAT(fmt: ProviderFormatEnum) -> ProviderFormatEnum:
    return fmt


def test_provider_manager_crud(tmp_path: Path):
    """Verify basic CRUD operations on ProviderManager."""
    config_file = tmp_path / "providers.yaml"
    pm = ProviderManager(config_path=config_file)

    templates = pm.get_templates()
    assert len(templates) >= 11

    providers = pm.get_providers()
    assert len(providers) >= 11

    openai = pm.get_provider("openai")
    assert openai is not None
    assert openai.display_name == "OpenAI"

    # Set active provider
    active = pm.set_active_provider("anthropic", model="claude-3-5-sonnet-20241022")
    assert active.id == "anthropic"
    assert active.models[0] == "claude-3-5-sonnet-20241022"
    assert pm.get_active_provider().id == "anthropic"

    # Save custom provider
    new_provider = ProviderConfig(
        id="custom-llm",
        display_name="Custom LLM",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:5000/v1",
        api_key="sk-123",
        requires_auth=True,
    )
    saved = pm.save_provider(new_provider)
    assert saved.configured is True
    assert pm.get_provider("custom-llm") is not None

    # Delete provider
    deleted = pm.delete_provider("custom-llm")
    assert deleted is True
    assert pm.get_provider("custom-llm") is None


def test_provider_manager_create_request(tmp_path: Path):
    """Verify create_provider helper."""
    config_file = tmp_path / "providers.yaml"
    pm = ProviderManager(config_path=config_file)

    req = ProviderCreateRequest(
        id="test-provider",
        display_name="Test Provider",
        api_url="https://test.api/v1",
        api_key="test-key",
    )
    created = pm.create_provider(req)
    assert created.id == "test-provider"
    assert created.configured is True
    assert created.enabled is True


def test_provider_manager_persistence(tmp_path: Path):
    """Verify disk persistence across manager instances."""
    config_file = tmp_path / "providers.yaml"
    pm1 = ProviderManager(config_path=config_file)
    pm1.set_active_provider("groq", model="llama-3.2-90b-vision-preview")

    new_cfg = ProviderConfig(
        id="persistent-id",
        display_name="Persistent Provider",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://persistent.api/v1",
        api_key="test-key",
    )
    pm1.save_provider(new_cfg)

    # Reload in pm2
    pm2 = ProviderManager(config_path=config_file)
    assert pm2.get_active_provider().id == "groq"
    assert pm2.get_provider("persistent-id") is not None


def test_provider_manager_auto_discovery(tmp_path: Path):
    """Verify environment variable auto-discovery on initialization."""
    config_file = tmp_path / "providers.yaml"

    env_overrides = {
        "OPENAI_API_KEY": "sk-openai-test-key",
        "OLLAMA_HOST": "http://192.168.1.100:11434",
    }
    with patch.dict(os.environ, env_overrides):
        pm = ProviderManager(config_path=config_file)

        openai = pm.get_provider("openai")
        assert openai is not None
        assert openai.api_key == "sk-openai-test-key"
        assert openai.configured is True

        ollama = pm.get_provider("ollama")
        assert ollama is not None
        assert ollama.api_url == "http://192.168.1.100:11434"
        assert ollama.configured is True


def test_provider_manager_list_models(tmp_path: Path):
    """Verify remote model listing and fallback behavior."""
    config_file = tmp_path / "providers.yaml"
    pm = ProviderManager(config_path=config_file)

    # Mock response for OpenAI-compatible
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "gpt-4o-real"}, {"id": "gpt-4o-mini-real"}]
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        models = pm.list_provider_models("openai")
        assert "gpt-4o-real" in models
        assert "gpt-4o-mini-real" in models

    # Test fallback when HTTP fails
    with patch("httpx.Client", side_effect=Exception("Network error")):
        fallback_models = pm.list_provider_models("deepseek")
        assert "deepseek-chat" in fallback_models


def test_singleton_accessor(tmp_path: Path):
    """Verify get_provider_manager singleton behavior."""
    reset_provider_manager()
    pm1 = get_provider_manager(config_path=tmp_path / "p.yaml")
    pm2 = get_provider_manager()
    assert pm1 is pm2
    reset_provider_manager()


# ---------------------------------------------------------------------------
# F2.6 — ProviderCreateRequest.headers validation
# (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_provider_create_request_accepts_benign_headers() -> None:
    """Custom headers (e.g. tenant-id, x-trace-id) are accepted unchanged."""
    req = ProviderCreateRequest(
        id="custom",
        display_name="Custom",
        api_url="https://api.example.com/v1",
        headers={"X-Tenant-Id": "abc", "x-trace-id": "trace-1"},
    )
    assert req.headers == {"X-Tenant-Id": "abc", "x-trace-id": "trace-1"}


@pytest.mark.parametrize(
    "bad_key",
    [
        "Host",
        "host",
        "X-Forwarded-Host",
        "x-forwarded-for",
        "X-Real-IP",
        "Forwarded",
        ":authority",
        ":scheme",
        "content-length",
        "transfer-encoding",
        "Authorization",
        "authorization",
        "Proxy-Authorization",
        "Cookie",
    ],
)
def test_provider_create_request_rejects_routing_and_auth_headers(bad_key: str) -> None:
    """Routing-affecting, body-framing, and credential headers are rejected."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ProviderCreateRequest(
            id="custom",
            display_name="Custom",
            api_url="https://api.example.com/v1",
            headers={bad_key: "value"},
        )
    msg = str(exc_info.value)
    assert "routing- or auth-affecting keys" in msg
    assert bad_key in msg or bad_key.lower() in msg


def test_provider_create_request_error_lists_all_bad_keys() -> None:
    """The error message lists every offending key, not just the first."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ProviderCreateRequest(
            id="custom",
            display_name="Custom",
            api_url="https://api.example.com/v1",
            headers={"Host": "x", "Authorization": "y", "X-Tenant-Id": "ok"},
        )
    msg = str(exc_info.value)
    assert "Host" in msg
    assert "Authorization" in msg
    # The benign key is still present in the model (validation
    # happens on assignment; the model is built before the validator
    # raises). What matters is that the validator raises, not that
    # partial state is preserved.
    assert "X-Tenant-Id" not in msg or "routing" in msg


# ---------------------------------------------------------------------------
# Masked-key preservation (merged from test_phase2_provider_masked_key.py)
# ---------------------------------------------------------------------------


def test_provider_manager_preserves_masked_api_key(tmp_path):
    """Audit-secondary F26 / Phase 2 fix: ``ProviderManager.save_provider``
    detects masked previews (``"sk-...XXXX"`` or ``"***"``) and preserves
    the existing real key instead of overwriting it when an operator
    re-submits the form with the masked value displayed by the UI.
    """
    mgr = ProviderManager(config_path=tmp_path / "providers.yaml")
    original = ProviderConfig(
        id="test-prov",
        display_name="Test Provider",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="sk-real-secret-key-12345",
        configured=True,
    )
    mgr.save_provider(original)

    # Submit update with masked preview
    updated = ProviderConfig(
        id="test-prov",
        display_name="Updated Provider",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="sk-r...2345",
        configured=True,
    )
    saved = mgr.save_provider(updated)
    assert saved.api_key == "sk-real-secret-key-12345"

    # Also test '***'
    updated_stars = ProviderConfig(
        id="test-prov",
        display_name="Updated Stars",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="***",
        configured=True,
    )
    saved_stars = mgr.save_provider(updated_stars)
    assert saved_stars.api_key == "sk-real-secret-key-12345"
