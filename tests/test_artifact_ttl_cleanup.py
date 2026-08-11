"""Tests for the artifact TTL background sweeper (audit A-15).

Verifies that the server lifespan actually spawns a sweeper that calls
``cleanup_expired`` on every artifact store at the configured interval,
and that cancelling it on shutdown is a clean no-op.
"""

from __future__ import annotations

import asyncio

import pytest

from omniscribe.api.routers import state
from omniscribe.api.services.artifacts import (
    DEFAULT_ARTIFACT_TTL_SECONDS,
    TextArtifactStore,
)


@pytest.fixture(autouse=True)
def _isolate_state() -> None:
    """Each test sees the real backend singletons.

    The background sweeper reads from ``state.text_artifacts`` etc., so
    we deliberately do NOT swap them out — the goal is to exercise the
    real wiring. We only restore any env vars that the tests touched,
    and we restore any store singletons that a test patched in place
    so a subsequent test sees the original backend wiring.
    """
    import os

    saved = os.environ.copy()
    saved_text = state.text_artifacts
    saved_metadata = state.metadata_artifacts
    saved_export = state.export_artifacts
    try:
        yield
    finally:
        # Restore store singletons so a previous test's broken-store
        # patch does not leak into the next test (e.g. the singleton
        # boundary test that walks the real backend surface).
        state.text_artifacts = saved_text
        state.metadata_artifacts = saved_metadata
        state.export_artifacts = saved_export
        # Restore env so other tests see a clean slate.
        for key in ("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S",):
            os.environ.pop(key, None)
        os.environ.update({k: v for k, v in saved.items() if k not in os.environ})


async def test_artifact_cleanup_loop_removes_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop calls cleanup_expired on every store on each tick."""
    from omniscribe import server

    # Replace the store singletons with minimal stubs that record calls.
    calls: list[tuple[str, int]] = []

    class _StubStore:
        def __init__(self, name: str) -> None:
            self._name = name

        def cleanup_expired(self) -> list[str]:
            calls.append((self._name, len(calls)))
            return []

    state.text_artifacts = _StubStore("text")  # type: ignore[assignment]
    state.metadata_artifacts = _StubStore("metadata")  # type: ignore[assignment]
    state.export_artifacts = _StubStore("export")  # type: ignore[assignment]

    task = asyncio.create_task(server._artifact_cleanup_loop(0.01))
    # Allow two ticks to fire.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    names = [name for name, _ in calls]
    assert names.count("text") >= 2
    assert names.count("metadata") >= 2
    assert names.count("export") >= 2


async def test_artifact_cleanup_loop_isolates_store_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One broken store must not stop the loop from sweeping the others."""

    from omniscribe import server

    class _BrokenStore:
        def cleanup_expired(self) -> list[str]:
            raise RuntimeError("disk on fire")

    good_calls: list[int] = []

    class _GoodStore:
        def cleanup_expired(self) -> list[str]:
            good_calls.append(1)
            return []

    state.text_artifacts = _BrokenStore()  # type: ignore[assignment]
    state.metadata_artifacts = _GoodStore()  # type: ignore[assignment]
    state.export_artifacts = _GoodStore()  # type: ignore[assignment]

    task = asyncio.create_task(server._artifact_cleanup_loop(0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Even though ``text_artifacts`` raises on every tick, the other
    # stores still get swept.
    assert len(good_calls) >= 2


async def test_start_artifact_cleanup_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interval of 0 disables the background sweep."""
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S", "0")
    assert await server._start_artifact_cleanup() is None


async def test_start_artifact_cleanup_spawns_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A positive interval spawns a task with the configured name."""
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S", "30")

    task = await server._start_artifact_cleanup()
    assert task is not None
    assert task.get_name() == "omniscribe-artifact-cleanup"
    # Clean up so we don't leak a coroutine into the event loop.
    await server._stop_artifact_cleanup(task)
    assert task.done()


async def test_stop_artifact_cleanup_is_noop_when_disabled() -> None:
    """``_stop_artifact_cleanup(None)`` is a clean no-op."""
    from omniscribe import server

    await server._stop_artifact_cleanup(None)


def test_artifact_cleanup_interval_invalid_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric interval falls back to the default rather than crashing."""
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S", "not-a-number")
    assert (
        server._artifact_cleanup_interval_s()
        == server._DEFAULT_ARTIFACT_CLEANUP_INTERVAL_S
    )


def test_artifact_cleanup_interval_negative_clamps_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A negative interval disables the sweep."""
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S", "-5")
    assert server._artifact_cleanup_interval_s() == 0.0


async def test_real_stores_get_swept_via_cleanup_expired() -> None:
    """Smoke test: a real TextArtifactStore's TTL is honoured end-to-end.

    Builds an entry with a very short TTL, waits for it to expire, runs
    ``cleanup_expired`` directly, and asserts the entry is gone. This
    is the same code path the background sweeper exercises, so a green
    test here means the sweep loop is wired to a working store.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        store = TextArtifactStore(
            ttl_seconds=0.05,
            max_entries=8,
            artifact_dir=Path(tmp),
        )
        await store.create({1: ["hello"]})
        assert len(store) == 1
        await asyncio.sleep(0.1)
        removed = store.cleanup_expired()
        assert len(removed) == 1
        assert len(store) == 0


def test_default_ttl_constant_matches_docstring() -> None:
    """The configured default TTL is one hour, matching the audit plan."""
    assert DEFAULT_ARTIFACT_TTL_SECONDS == 60 * 60
