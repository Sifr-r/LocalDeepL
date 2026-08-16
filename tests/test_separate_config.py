from __future__ import annotations

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
* ``POST /api/config`` is refused with 503 when the StateBackend's
  config store is not cross-worker visible (issue H1).
* A value written via the StateBackend is visible to a "second worker"
  view that wraps the same store (cross-worker persistence contract).
"""

from typing import Any  # noqa: E402  (after module docstring)
from unittest.mock import AsyncMock, patch  # noqa: E402  (after module docstring)

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from omniscribe.api.routers import config  # noqa: E402
from omniscribe.api.routers import state as router_state  # noqa: E402
from omniscribe.api.services.ai import resolve_ai_settings  # noqa: E402
from omniscribe.api.services.config_store import (  # noqa: E402
    InMemoryConfigStore,
    SQLiteConfigStore,
)
from omniscribe.utils.security import SSRFCheckResult  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(config.router)
    return TestClient(app)


@pytest.fixture
def in_memory_store() -> InMemoryConfigStore:
    """Fresh in-memory config store marked cross-worker visible.

    Tests run in a single process, so the real
    :class:`~omniscribe.api.services.config_store.InMemoryConfigStore`
    is "cross-worker visible" for the test process. Marking the
    private flag here means POSTs succeed without standing up a
    Redis or SQLite backend. The original store on
    :data:`router_state.backend` is restored on teardown.
    """
    original = router_state.backend.config_store
    store = InMemoryConfigStore(initial=dict(config._config))  # type: ignore[attr-defined]
    store._cross_worker_visible = True  # type: ignore[attr-defined]
    router_state.backend.config_store = store
    try:
        yield store
    finally:
        router_state.backend.config_store = original
        # Reset the module dict so the next test sees a clean
        # baseline seeded from env (the production handlers refresh
        # ``_config`` from the store on every read, but tests that
        # touch ``_config`` directly benefit from a clean slate).
        config._config.clear()  # type: ignore[attr-defined]
        config._config.update(  # type: ignore[attr-defined]
            {
                "api_base": "https://api.openai.com/v1",
                "api_key": "lm-studio",
                "model": "openai/gpt-oss-20b",
            }
        )


@pytest.fixture(autouse=True)
def _install_store(in_memory_store: InMemoryConfigStore) -> None:
    """Auto-install the cross-worker in-memory store for every test."""
    return None


def _set_store(**values: Any) -> None:
    """Test helper: write ``values`` to the active config store.

    The production route handlers refresh :data:`config._config` from
    the store on every read, so a test that mutates ``_config``
    directly will be overwritten. The cross-worker contract is
    "store is the source of truth", so the helper writes to the
    store; the next read (in the test or in a route handler) will
    sync ``_config`` to match.
    """
    router_state.backend.config_store.update(values)


@pytest.fixture(autouse=True)
def _mock_is_ssrf_target():
    """Globally mock SSRF validation for config tests unless a test explicitly tests it."""
    with patch(
        "omniscribe.api.routers.config.is_ssrf_target",
        new=AsyncMock(
            return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
        ),
    ):
        yield


def test_get_ocr_config_masks_api_key(client: TestClient) -> None:
    _set_store(
        ocr_api_base="http://ocr-host/v1",
        ocr_api_key="supersecret-ocr-key",
        ocr_model="ocr-model",
        ocr_provider="openai",
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
    _set_store(
        translation_api_base="http://translation-host/v1",
        translation_api_key="translate-secret-key",
        translation_model="translation-model",
        translation_provider="deepseek",
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
    # The store has the real key, not the masked preview.
    snapshot = router_state.backend.config_store.get_snapshot()
    assert snapshot["ocr_api_key"] == "fresh-ocr-key-1234"


def test_post_ocr_config_ignores_masked_placeholder(client: TestClient) -> None:
    _set_store(ocr_api_key="real-ocr-key-1234")

    response = client.post(
        "/api/config/ocr",
        json={"ocr_api_key": "abcd...wxyz"},
    )

    assert response.status_code == 200
    # The masked placeholder must NOT overwrite the existing key.
    snapshot = router_state.backend.config_store.get_snapshot()
    assert snapshot["ocr_api_key"] == "real-ocr-key-1234"


def test_post_ocr_config_rejects_ssrf_base(client: TestClient) -> None:
    with patch(
        "omniscribe.api.routers.config.is_ssrf_target",
        new=AsyncMock(
            return_value=SSRFCheckResult(
                allowed=False, resolved_ip=None, reason="mock-blocked"
            )
        ),
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
    snapshot = router_state.backend.config_store.get_snapshot()
    assert snapshot["sliding_window_words"] == 120


def test_post_ocr_auth_token_round_trip(client: TestClient) -> None:
    response = client.post(
        "/api/config/ocr/auth",
        json={"auth_token": "a-strong-randomly-generated-ocr-auth-token-32+"},
    )
    assert response.status_code == 200
    snapshot = router_state.backend.config_store.get_snapshot()
    assert (
        snapshot["ocr_auth_token"] == "a-strong-randomly-generated-ocr-auth-token-32+"
    )


def test_post_ocr_auth_token_clear_via_null(client: TestClient) -> None:
    _set_store(ocr_auth_token="previously-set")

    response = client.post(
        "/api/config/ocr/auth",
        json={"auth_token": None},
    )
    assert response.status_code == 200
    snapshot = router_state.backend.config_store.get_snapshot()
    assert snapshot["ocr_auth_token"] is None


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
    _set_store(
        api_base="http://legacy-host/v1",
        api_key="legacy-key",
        model="legacy-model",
        ocr_api_base="http://ocr-host/v1",
        ocr_api_key="ocr-key",
        ocr_model="ocr-model",
    )

    settings = config.get_ocr_settings()

    assert settings.api_base == "http://ocr-host/v1"
    assert settings.api_key == "ocr-key"
    assert settings.model == "ocr-model"


def test_get_translation_settings_prefers_namespaced_over_legacy() -> None:
    _set_store(
        api_base="http://legacy-host/v1",
        api_key="legacy-key",
        model="legacy-model",
        translation_api_base="http://translation-host/v1",
        translation_api_key="translation-key",
        translation_model="translation-model",
    )

    settings = config.get_translation_settings()

    assert settings.api_base == "http://translation-host/v1"
    assert settings.api_key == "translation-key"
    assert settings.model == "translation-model"


def test_get_ocr_settings_falls_back_to_legacy_when_unset() -> None:
    _set_store(
        api_base="http://legacy-host/v1",
        api_key="legacy-key",
        model="legacy-model",
    )

    settings = config.get_ocr_settings()

    assert settings.api_base == "http://legacy-host/v1"
    assert settings.api_key == "legacy-key"
    assert settings.model == "legacy-model"


def test_legacy_post_config_does_not_clobber_namespaced_ocr(
    client: TestClient,
) -> None:
    _set_store(
        ocr_api_base="http://ocr-host/v1",
        ocr_api_key="ocr-key",
        ocr_model="ocr-model",
        api_base="http://legacy-host/v1",
        api_key="legacy-key",
        model="legacy-model",
    )

    response = client.post(
        "/api/config",
        json={"api_base": "http://updated-legacy-host/v1"},
    )

    assert response.status_code == 200
    snapshot = router_state.backend.config_store.get_snapshot()
    # Legacy key updated.
    assert snapshot["api_base"] == "http://updated-legacy-host/v1"
    # Namespaced OCR keys preserved untouched.
    assert snapshot["ocr_api_base"] == "http://ocr-host/v1"
    assert snapshot["ocr_api_key"] == "ocr-key"


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
        "omniscribe.api.services.ai.is_ssrf_target",
        new=AsyncMock(
            return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
        ),
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
        "omniscribe.api.services.ai.is_ssrf_target",
        new=AsyncMock(
            return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
        ),
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


# ---------------------------------------------------------------------------
# Issue H1: cross-worker config persistence
# ---------------------------------------------------------------------------


def test_post_config_in_memory_store_is_refused_with_503() -> None:
    """POST /api/config refuses with 503 when the store is in-memory.

    The :class:`~omniscribe.api.services.config_store.InMemoryConfigStore`
    is per-process: accepting the update would silently lie to
    operators about cross-worker state, so the handler returns 503
    with a remediation message instead.
    """
    # Install a real (not cross-worker-visible) in-memory store.
    original = router_state.backend.config_store
    store = InMemoryConfigStore()
    assert not store.is_cross_worker_visible()
    router_state.backend.config_store = store
    try:
        app = FastAPI()
        app.include_router(config.router)
        client = TestClient(app)

        response = client.post(
            "/api/config",
            json={"api_base": "http://updated-legacy-host/v1"},
        )

        assert response.status_code == 503
        body = response.json()
        assert "error" in body
        assert "persistent" in body["error"].lower()
        # The store must not have been mutated.
        assert "api_base" not in store.get_snapshot()
    finally:
        router_state.backend.config_store = original


def test_post_ocr_config_in_memory_store_is_refused_with_503() -> None:
    """Per-namespace POSTs are also refused when the store is in-memory."""
    original = router_state.backend.config_store
    store = InMemoryConfigStore()
    assert not store.is_cross_worker_visible()
    router_state.backend.config_store = store
    try:
        app = FastAPI()
        app.include_router(config.router)
        client = TestClient(app)

        response = client.post(
            "/api/config/ocr",
            json={"ocr_api_base": "http://ocr-host/v1"},
        )

        assert response.status_code == 503
    finally:
        router_state.backend.config_store = original


def test_post_translation_config_in_memory_store_is_refused_with_503() -> None:
    original = router_state.backend.config_store
    store = InMemoryConfigStore()
    assert not store.is_cross_worker_visible()
    router_state.backend.config_store = store
    try:
        app = FastAPI()
        app.include_router(config.router)
        client = TestClient(app)

        response = client.post(
            "/api/config/translation",
            json={"translation_api_base": "http://translation-host/v1"},
        )

        assert response.status_code == 503
    finally:
        router_state.backend.config_store = original


def test_post_ocr_auth_token_in_memory_store_is_refused_with_503() -> None:
    original = router_state.backend.config_store
    store = InMemoryConfigStore()
    assert not store.is_cross_worker_visible()
    router_state.backend.config_store = store
    try:
        app = FastAPI()
        app.include_router(config.router)
        client = TestClient(app)

        response = client.post(
            "/api/config/ocr/auth",
            json={"auth_token": "a-strong-randomly-generated-ocr-auth-token-32+"},
        )

        assert response.status_code == 503
    finally:
        router_state.backend.config_store = original


def test_sqlite_config_store_round_trip_is_visible_to_second_view(
    tmp_path,
) -> None:
    """A value written via one view is visible to another view of the
    same file. This is the cross-worker contract for
    :class:`~omniscribe.api.services.config_store.SQLiteConfigStore`:
    two uvicorn workers that open the same file see the same data.
    """
    db_path = tmp_path / "config.db"
    worker_a = SQLiteConfigStore(db_path)
    worker_b = SQLiteConfigStore(db_path)

    worker_a.update({"api_base": "http://worker-a-host/v1", "model": "a-model"})

    snapshot_b = worker_b.get_snapshot()
    assert snapshot_b["api_base"] == "http://worker-a-host/v1"
    assert snapshot_b["model"] == "a-model"
    assert worker_b.is_cross_worker_visible() is True


def test_sqlite_config_store_handles_json_corruption_gracefully(
    tmp_path,
) -> None:
    """A corrupted snapshot must not crash the next read.

    Operators occasionally edit the file by hand; the store should
    return an empty dict instead of raising so the operator gets a
    recoverable state.
    """
    import sqlite3

    db_path = tmp_path / "config.db"
    # Bootstrap the schema with one well-formed write.
    SQLiteConfigStore(db_path).update({"a": 1})

    # Corrupt the payload.
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE omniscribe_config SET payload = ? WHERE id = 1",
            ("not-json",),
        )

    snapshot = SQLiteConfigStore(db_path).get_snapshot()
    assert snapshot == {}


def test_post_legacy_config_persists_to_sqlite_store(tmp_path) -> None:
    """End-to-end: POST /api/config writes to the SQLiteConfigStore and
    a "second worker" view (fresh ConfigStore over the same file)
    reads the new value back.
    """
    db_path = tmp_path / "config.db"
    original = router_state.backend.config_store
    router_state.backend.config_store = SQLiteConfigStore(db_path)
    try:
        app = FastAPI()
        app.include_router(config.router)
        client = TestClient(app)

        response = client.post(
            "/api/config",
            json={"api_base": "http://sqlite-legacy-host/v1"},
        )
        assert response.status_code == 200

        # A "second worker" opens a fresh ConfigStore over the same
        # file. This is what a second uvicorn process would do at
        # startup; the value must already be present.
        second_view = SQLiteConfigStore(db_path)
        snapshot = second_view.get_snapshot()
        assert snapshot["api_base"] == "http://sqlite-legacy-host/v1"
    finally:
        router_state.backend.config_store = original
