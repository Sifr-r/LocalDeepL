"""Config router helpers — lifted from routers/config.py into services/config_helpers.py.

These tests assert the ACTUAL contract of the helpers (preserved from the
inline definitions that pre-dated the Phase C extraction). The plan's
literal test file assumed a fictional ``(store, *, namespace, payload)``
async signature that never existed in this codebase.
"""

from __future__ import annotations

import pytest

from omniscribe.api.services.config_store import InMemoryConfigStore
from omniscribe.api.services.helpers import (
    ConfigBackendIncompatible,
    load_config_from_store,
    mask_api_key,
    persist_config,
)


def test_mask_api_key_returns_none_for_none() -> None:
    assert mask_api_key(None) is None


def test_mask_api_key_passes_through_lm_studio_sentinel() -> None:
    """The literal string 'lm-studio' is a sentinel (no API key needed) and
    must pass through unmasked so the UI doesn't show '*****' for it.
    """
    assert mask_api_key("lm-studio") == "lm-studio"


def test_mask_api_key_short_string() -> None:
    assert mask_api_key("short") == "********"
    assert mask_api_key("12345678") == "********"


def test_mask_api_key_first4_last4_format() -> None:
    """Standard mask format: first 4 chars + '...' + last 4 chars."""
    assert mask_api_key("supersecret-ocr-key") == "supe...-key"
    assert mask_api_key("sk-1234567890abcdef") == "sk-1...cdef"


def test_config_backend_incompatible_is_exception() -> None:
    """``ConfigBackendIncompatible`` extends ``Exception`` (not ``APIError``);
    it's caught and re-raised as ``BackendUnavailable`` at the route boundary.
    """
    exc = ConfigBackendIncompatible("state backend 'in_memory' cannot ...")
    assert isinstance(exc, Exception)
    assert "state backend" in str(exc)


def test_load_config_from_store_returns_dict() -> None:
    """``load_config_from_store`` returns the current config snapshot (always
    a dict). Uses the global config store at call time, so this is a smoke
    test on the function shape rather than store contents.
    """
    payload = load_config_from_store()
    assert isinstance(payload, dict)


def test_persist_config_raises_when_store_not_cross_worker_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default :class:`InMemoryConfigStore` is **not** cross-worker
    visible, so :func:`persist_config` must raise
    :class:`ConfigBackendIncompatible` rather than silently dropping the
    update (issue H1). The route boundary catches this and converts it to
    a 503 envelope.
    """
    from omniscribe.api.routers import state as router_state

    monkeypatch.setattr(
        router_state.backend,
        "config_store",
        InMemoryConfigStore(),
        raising=True,
    )
    with pytest.raises(ConfigBackendIncompatible) as excinfo:
        persist_config({"test_helpers_marker": "x"})
    assert "persistent state backend" in str(excinfo.value)


def test_persist_config_writes_through_when_store_cross_worker_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the active store IS cross-worker visible (Redis/SQLite, or the
    test-only flip on :class:`InMemoryConfigStore`), :func:`persist_config`
    writes through to the store. ``PYTEST_CURRENT_TEST`` is in ``os.environ``
    during the test, so the ``.env`` update branch is skipped.
    """
    from omniscribe.api.routers import state as router_state

    store = InMemoryConfigStore(initial={"existing": "value"})
    store._cross_worker_visible = True  # type: ignore[attr-defined]
    monkeypatch.setattr(
        router_state.backend,
        "config_store",
        store,
        raising=True,
    )
    persist_config({"new_key": "new_value", "existing": "overwritten"})

    snapshot = store.get_snapshot()
    assert snapshot["new_key"] == "new_value"
    assert snapshot["existing"] == "overwritten"
