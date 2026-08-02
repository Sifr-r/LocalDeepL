"""Tests for the per-namespace OCR / translation runtime config.

These tests pin the public contract:

* ``GET /api/config/ocr`` returns the OCR-namespace keys; the API key is
  masked.
* ``POST /api/config/ocr`` accepts and persists the ``ocr_*`` keys;
  per-request ``ocr_api_base`` is SSRF-checked; ``ocr_api_key`` masked
  placeholders are ignored.
* Same contract for ``/api/config/translation``.
* The namespaced keys take precedence over the legacy ``api_*`` keys
  when the OCR / translation handlers resolve settings.
* Legacy ``POST /api/config`` continues to mutate the legacy shared
  fallback and does not silently clobber namespaced divergence.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_deepl.api.routers import config
from local_deepl.api.services.ai import resolve_ai_settings


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(config.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_config():
    """Snapshot and restore the in-memory config around every test."""
    snapshot = dict(config._config)  # type: ignore[attr-defined]
    yield
    config._config.clear()  # type: ignore[attr-defined]
    config._config.update(snapshot)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _mock_is_ssrf_target():
    """Globally mock SSRF validation for config tests unless a test explicitly tests it."""
    with patch(
        "local_deepl.api.routers.config.is_ssrf_target",
        new=AsyncMock(return_value=False),
    ):
        yield


def test_get_ocr_config_masks_api_key(client: TestClient) -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "ocr_api_base": "http://ocr-host/v1",
            "ocr_api_key": "supersecret-ocr-key",
            "ocr_model": "ocr-model",
            "ocr_provider": "openai",
        }
    )

    response = client.get("/api/config/ocr")

    assert response.status_code == 200
    body = response.json()
    assert body["ocr_api_base"] == "http://ocr-host/v1"
    assert body["ocr_api_key"] != "supersecret-ocr-key"
    assert body["ocr_api_key"].startswith("supe")
    assert body["ocr_api_key"].endswith("-key")
    assert body["ocr_model"] == "ocr-model"
    assert body["ocr_provider"] == "openai"


def test_get_translation_config_masks_api_key(client: TestClient) -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "translation_api_base": "http://translation-host/v1",
            "translation_api_key": "translate-secret-key",
            "translation_model": "translation-model",
            "translation_provider": "deepseek",
        }
    )

    response = client.get("/api/config/translation")

    assert response.status_code == 200
    body = response.json()
    assert body["translation_api_base"] == "http://translation-host/v1"
    assert body["translation_api_key"] != "translate-secret-key"
    assert body["translation_api_key"].startswith("tran")
    assert body["translation_api_key"].endswith("-key")
    assert body["translation_model"] == "translation-model"
    assert body["translation_provider"] == "deepseek"


def test_post_ocr_config_persists_namespaced_keys(client: TestClient) -> None:
    response = client.post(
        "/api/config/ocr",
        json={
            "ocr_api_base": "http://new-ocr-host/v1",
            "ocr_api_key": "fresh-ocr-key-1234",
            "ocr_model": "fresh-ocr-model",
            "ocr_provider": "openai",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ocr_api_base"] == "http://new-ocr-host/v1"
    assert body["ocr_model"] == "fresh-ocr-model"
    # In-memory store has the real key, not the masked preview.
    assert config._config["ocr_api_key"] == "fresh-ocr-key-1234"  # type: ignore[attr-defined]


def test_post_ocr_config_ignores_masked_placeholder(client: TestClient) -> None:
    config._config["ocr_api_key"] = "real-ocr-key-1234"  # type: ignore[attr-defined]

    response = client.post(
        "/api/config/ocr",
        json={"ocr_api_key": "abcd...wxyz"},
    )

    assert response.status_code == 200
    # The masked placeholder must NOT overwrite the existing key.
    assert config._config["ocr_api_key"] == "real-ocr-key-1234"  # type: ignore[attr-defined]


def test_post_ocr_config_rejects_ssrf_base(client: TestClient) -> None:
    with patch(
        "local_deepl.api.routers.config.is_ssrf_target",
        new=AsyncMock(return_value=True),
    ):
        response = client.post(
            "/api/config/ocr",
            json={"ocr_api_base": "http://127.0.0.1:1234/v1"},
        )

    assert response.status_code == 403
    assert "error" in response.json()


def test_post_translation_config_persists_namespaced_keys(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/config/translation",
        json={
            "translation_api_base": "http://translation-host/v1",
            "translation_api_key": "translate-key-1234",
            "translation_model": "translation-model",
            "translation_provider": "deepseek",
            "sliding_window_words": 120,
            "dual_translate": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["translation_api_base"] == "http://translation-host/v1"
    assert body["translation_model"] == "translation-model"
    assert body["sliding_window_words"] == 120
    assert body["dual_translate"] is True
    assert config._config["sliding_window_words"] == 120  # type: ignore[attr-defined]


def test_post_ocr_auth_token_round_trip(client: TestClient) -> None:
    response = client.post(
        "/api/config/ocr/auth",
        json={"auth_token": "a-strong-randomly-generated-ocr-auth-token-32+"},
    )
    assert response.status_code == 200
    assert (
        config._config["ocr_auth_token"]
        == "a-strong-randomly-generated-ocr-auth-token-32+"  # type: ignore[attr-defined]
    )


def test_post_ocr_auth_token_clear_via_null(client: TestClient) -> None:
    config._config["ocr_auth_token"] = "previously-set"  # type: ignore[attr-defined]

    response = client.post(
        "/api/config/ocr/auth",
        json={"auth_token": None},
    )
    assert response.status_code == 200
    assert config._config["ocr_auth_token"] is None  # type: ignore[attr-defined]


def test_post_ocr_auth_token_rejects_masked_placeholder(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/config/ocr/auth",
        json={"auth_token": "abcd...wxyz"},
    )
    # M1: the placeholder mask is short enough that the
    # ``min_length=32`` Pydantic field validator rejects it before
    # the custom denylist runs, so we get 422 instead of 400. Either
    # response is a valid rejection; the contract is "do not accept it".
    assert response.status_code in (400, 422)


def test_get_ocr_settings_prefers_namespaced_over_legacy() -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "api_base": "http://legacy-host/v1",
            "api_key": "legacy-key",
            "model": "legacy-model",
            "ocr_api_base": "http://ocr-host/v1",
            "ocr_api_key": "ocr-key",
            "ocr_model": "ocr-model",
        }
    )

    settings = config.get_ocr_settings()

    assert settings.api_base == "http://ocr-host/v1"
    assert settings.api_key == "ocr-key"
    assert settings.model == "ocr-model"


def test_get_translation_settings_prefers_namespaced_over_legacy() -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "api_base": "http://legacy-host/v1",
            "api_key": "legacy-key",
            "model": "legacy-model",
            "translation_api_base": "http://translation-host/v1",
            "translation_api_key": "translation-key",
            "translation_model": "translation-model",
        }
    )

    settings = config.get_translation_settings()

    assert settings.api_base == "http://translation-host/v1"
    assert settings.api_key == "translation-key"
    assert settings.model == "translation-model"


def test_get_ocr_settings_falls_back_to_legacy_when_unset() -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "api_base": "http://legacy-host/v1",
            "api_key": "legacy-key",
            "model": "legacy-model",
        }
    )

    settings = config.get_ocr_settings()

    assert settings.api_base == "http://legacy-host/v1"
    assert settings.api_key == "legacy-key"
    assert settings.model == "legacy-model"


def test_legacy_post_config_does_not_clobber_namespaced_ocr(
    client: TestClient,
) -> None:
    config._config.update(  # type: ignore[attr-defined]
        {
            "ocr_api_base": "http://ocr-host/v1",
            "ocr_api_key": "ocr-key",
            "ocr_model": "ocr-model",
            "api_base": "http://legacy-host/v1",
            "api_key": "legacy-key",
            "model": "legacy-model",
        }
    )

    response = client.post(
        "/api/config",
        json={"api_base": "http://updated-legacy-host/v1"},
    )

    assert response.status_code == 200
    # Legacy key updated.
    assert config._config["api_base"] == "http://updated-legacy-host/v1"  # type: ignore[attr-defined]
    # Namespaced OCR keys preserved untouched.
    assert config._config["ocr_api_base"] == "http://ocr-host/v1"  # type: ignore[attr-defined]
    assert config._config["ocr_api_key"] == "ocr-key"  # type: ignore[attr-defined]


async def test_resolve_ai_settings_uses_namespaced_translation_key() -> None:
    config_map = {
        "api_base": "http://legacy-host/v1",
        "api_key": "legacy-key",
        "model": "legacy-model",
        "translation_api_base": "http://translation-host/v1",
        "translation_api_key": "translation-key",
        "translation_model": "translation-model",
    }

    with patch(
        "local_deepl.api.services.ai.is_ssrf_target",
        new=AsyncMock(return_value=False),
    ):
        settings = await resolve_ai_settings(
            api_base=None,
            api_key=None,
            model=None,
            config=config_map,
        )

    assert settings.api_base == "http://translation-host/v1"
    assert settings.api_key == "translation-key"
    assert settings.model == "translation-model"


async def test_resolve_ai_settings_request_overrides_win() -> None:
    config_map = {
        "translation_api_base": "http://translation-host/v1",
        "translation_api_key": "translation-key",
        "translation_model": "translation-model",
    }

    with patch(
        "local_deepl.api.services.ai.is_ssrf_target",
        new=AsyncMock(return_value=False),
    ):
        settings = await resolve_ai_settings(
            api_base="http://request-host/v1",
            api_key="request-key",
            model="request-model",
            config=config_map,
        )

    assert settings.api_base == "http://request-host/v1"
    assert settings.api_key == "request-key"
    assert settings.model == "request-model"


def test_ocr_config_update_rejects_unknown_keys(client: TestClient) -> None:
    response = client.post(
        "/api/config/ocr",
        json={"ocr_api_base": "http://x/v1", "unknown_key": "boom"},
    )
    assert response.status_code == 422


def test_translation_config_update_rejects_unknown_keys(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/config/translation",
        json={"translation_api_base": "http://x/v1", "unknown_key": "boom"},
    )
    assert response.status_code == 422
