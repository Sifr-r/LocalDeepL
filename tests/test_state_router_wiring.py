"""Verify ``omniscribe.api.routers.state`` honours ``OMNISCRIBE_STATE_BACKEND``.

The audit found that ``state.py`` imported :func:`build_state_backend` but
unconditionally instantiated :class:`LocalStateBackend`, hardcoding the
in-memory backend. This file pins the fix in place: the module-level
``backend`` attribute must be produced by the factory, so that
``OMNISCRIBE_STATE_BACKEND=sqlite`` and ``OMNISCRIBE_STATE_BACKEND=redis``
are actually reachable from a normal ``import`` of the router state.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from omniscribe.api.routers import state as router_state
from omniscribe.api.services.state_backend import (
    LocalStateBackend,
    build_state_backend,
)
from omniscribe.config import load_settings


@pytest.fixture
def _restore_router_state(monkeypatch: pytest.MonkeyPatch):
    """Reload ``state.py`` after the test so the singleton is in a known
    default-backend state. Without this, a reordering of tests could leave
    a stale SQLite/Redis backend attached to ``router_state.backend`` for
    the rest of the session.
    """
    yield
    monkeypatch.delenv("OMNISCRIBE_STATE_BACKEND", raising=False)
    monkeypatch.delenv("OMNISCRIBE_ARTIFACT_DIR", raising=False)
    importlib.reload(router_state)


def test_default_backend_is_local_via_factory(
    _restore_router_state: None,
) -> None:
    """Default ``OMNISCRIBE_STATE_BACKEND`` (``"memory"``) routes through the
    factory to :class:`LocalStateBackend`. This is the default-import contract
    every other test in the suite depends on; it must keep passing.
    """
    assert isinstance(router_state.backend, LocalStateBackend)
    # Pin the contract: state.backend and the factory's product share the
    # same class. If the wiring regresses to ``LocalStateBackend.from_env()``
    # the import will still pass for the default case, but the class identity
    # comparison will silently drift if someone re-points the factory at a
    # subclass in the future.
    expected = build_state_backend(load_settings())
    assert type(router_state.backend) is type(expected)


def test_sqlite_backend_wired_through_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    _restore_router_state: None,
) -> None:
    """With ``OMNISCRIBE_STATE_BACKEND=sqlite``, a fresh import of
    ``state.py`` must produce a :class:`SQLiteStateBackend`.
    """
    pytest.importorskip("omniscribe.api.services.state_backend_sqlite")
    from omniscribe.api.services.state_backend_sqlite import SQLiteStateBackend

    monkeypatch.setenv("OMNISCRIBE_STATE_BACKEND", "sqlite")
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    importlib.reload(router_state)

    assert isinstance(router_state.backend, SQLiteStateBackend)
    # And it must satisfy the StateBackend Protocol (duck-typed).
    from omniscribe.api.services.state_backend import StateBackend

    assert isinstance(router_state.backend, StateBackend)
    # The module-level alias must track the new backend (this is what the
    # router call sites actually use).
    assert router_state.text_artifacts is router_state.backend.text_artifacts
    assert router_state.job_history is router_state.backend.job_history
    assert router_state.lexicon_store is router_state.backend.lexicon_store


def test_redis_backend_wired_through_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    _restore_router_state: None,
) -> None:
    """With ``OMNISCRIBE_STATE_BACKEND=redis``, a fresh import of
    ``state.py`` must produce a :class:`RedisStateBackend`. The redis
    client is lazy (uses ``Redis.from_url``), so an unreachable URL is
    acceptable for the wiring test — the constructor never opens a socket.
    """
    pytest.importorskip("redis")
    from omniscribe.api.services.state_backend_redis import RedisStateBackend

    monkeypatch.setenv("OMNISCRIBE_STATE_BACKEND", "redis")
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    # Intentionally unreachable host: Redis.from_url is lazy so the
    # constructor succeeds. The runtime fail-fast happens on the first
    # actual call, which is outside the wiring fix's scope.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    importlib.reload(router_state)

    assert isinstance(router_state.backend, RedisStateBackend)
    from omniscribe.api.services.state_backend import StateBackend

    assert isinstance(router_state.backend, StateBackend)
    assert router_state.lexicon_store is router_state.backend.lexicon_store


def test_factory_uses_settings_artifact_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    _restore_router_state: None,
) -> None:
    """The factory must read ``OMNISCRIBE_ARTIFACT_DIR`` from settings and
    thread it through to the backend's artifact stores. This proves the
    wiring goes through ``load_settings()`` rather than the historical
    ``from_env`` shortcut.
    """
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    importlib.reload(router_state)

    expected_artifact_dir = tmp_path / "omniscribe"
    assert router_state.backend.text_artifacts.artifact_dir == expected_artifact_dir
    assert router_state.backend.metadata_artifacts.artifact_dir == expected_artifact_dir
    assert router_state.backend.export_artifacts.artifact_dir == expected_artifact_dir
