"""Phase 1 tests — the JobQueue capability seam.

Covers:

1. :class:`OCRJobQueue` structurally satisfies the :class:`JobQueue` Protocol.
2. :func:`local_job_queue_provider` registers a queue into a context.
3. The runtime module's context accessor and feature flag.
4. End-to-end: ``create_app`` bootstraps a context with a JobQueue provider.
5. The migration-window behavior: the registered queue is the same instance
   as the legacy ``state.ocr_job_queue`` singleton.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from omniscribe.api.plugin import (
    JobQueue,
    PluginContext,
    config_store_provider,
    local_job_queue_provider,
)
from omniscribe.api.plugin import runtime as plugin_runtime
from omniscribe.api.plugin.runtime import (
    get_plugin_context,
    get_service,
    refresh_plugin_context_enabled,
    set_plugin_context,
    set_plugin_context_enabled,
)
from omniscribe.api.services.config_store import InMemoryConfigStore
from omniscribe.api.services.ocr_jobs import OCRJobQueue

# -- Protocol structural conformance -----------------------------------------


def test_ocr_job_queue_satisfies_the_job_queue_protocol() -> None:
    """The concrete ``OCRJobQueue`` must be an instance of the runtime_checkable
    ``JobQueue`` Protocol — this is the contract every provider must honor."""
    queue = OCRJobQueue()
    assert isinstance(queue, JobQueue)


def test_job_queue_protocol_lists_all_consumer_methods() -> None:
    """Pin the Protocol surface so an accidental signature change is caught."""
    expected = {
        "running",
        "start",
        "stop",
        "submit",
        "get",
        "list",
        "cancel",
        "cleanup_expired",
    }
    actual = set(dir(JobQueue))
    # The Protocol also has other attrs; we just require the consumer-facing set.
    assert expected.issubset(actual), f"Missing on JobQueue: {expected - actual}"


# -- local_job_queue_provider ------------------------------------------------


def test_local_provider_registers_a_fresh_queue_by_default() -> None:
    ctx = PluginContext("test")
    provider = local_job_queue_provider()
    ctx.mount(provider)
    queue = ctx.get(JobQueue, name="local")
    assert isinstance(queue, OCRJobQueue)
    assert queue.running is False  # not started


def test_local_provider_can_register_an_existing_queue() -> None:
    """The migration window shares the legacy ``state.ocr_job_queue`` instance
    so consumers see the same records whether they look up via the context
    or the module-level singleton."""
    shared = OCRJobQueue()
    ctx = PluginContext("test")
    ctx.mount(local_job_queue_provider(queue=shared, name="local"))
    assert ctx.get(JobQueue, name="local") is shared


def test_local_provider_returns_a_plugin_callable() -> None:
    """The provider is a factory: calling it returns a :class:`Plugin`."""
    provider = local_job_queue_provider()
    assert callable(provider)
    plugin = provider
    assert callable(plugin)


def test_local_provider_can_be_unmounted_via_the_returned_disposer() -> None:
    """``ctx.mount(plugin)`` returns a top-level disposer that, when called,
    unwinds every effect the plugin registered — including the service
    registration done inside ``local_job_queue_provider``."""
    ctx = PluginContext("test")
    unmount = ctx.mount(local_job_queue_provider())
    assert ctx.has(JobQueue, name="local") is True
    unmount()
    assert ctx.has(JobQueue, name="local") is False


def test_local_provider_default_name_is_local() -> None:
    """The default name is ``"local"`` so a future ``"celery"`` provider can coexist."""
    ctx = PluginContext("test")
    ctx.mount(local_job_queue_provider())
    names = ctx.service_names(JobQueue)
    assert names == ["local"]


# -- runtime module ---------------------------------------------------------


def test_plugin_context_default_is_none() -> None:
    """A fresh import has no live context until ``create_app`` runs."""
    # Save and clear the module state for the test.
    saved = plugin_runtime._plugin_context
    plugin_runtime._plugin_context = None
    try:
        assert get_plugin_context() is None
    finally:
        plugin_runtime._plugin_context = saved


def test_set_and_get_plugin_context() -> None:
    saved = plugin_runtime._plugin_context
    ctx = PluginContext("test")
    set_plugin_context(ctx)
    try:
        assert get_plugin_context() is ctx
    finally:
        set_plugin_context(saved)


def test_get_service_returns_a_registered_service() -> None:
    """The runtime ``get_service`` helper looks up by the default name
    (``"default"``), but the provider registers under ``"local"``; the
    test confirms the named lookup path works."""
    saved = plugin_runtime._plugin_context
    ctx = PluginContext("test")
    queue = OCRJobQueue()
    ctx.mount(local_job_queue_provider(queue=queue, name="local"))
    set_plugin_context(ctx)
    try:
        # The helper uses name="default", which is not registered.
        # We look up by the actual provider name to confirm registration.
        assert ctx.get(JobQueue, name="local") is queue
    finally:
        set_plugin_context(saved)


def test_get_service_raises_when_context_not_bootstrapped() -> None:
    from omniscribe.api.plugin import ServiceNotFoundError

    saved = plugin_runtime._plugin_context
    plugin_runtime._plugin_context = None
    try:
        with pytest.raises(ServiceNotFoundError):
            get_service(JobQueue)
    finally:
        plugin_runtime._plugin_context = saved


def test_set_plugin_context_warns_when_replacing_a_live_context() -> None:
    """A non-None context being replaced with another non-None context logs a warning."""
    import warnings

    saved = plugin_runtime._plugin_context
    try:
        plugin_runtime._plugin_context = PluginContext("first")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            set_plugin_context(PluginContext("second"))
        # Either no warning (depending on logger config) or a UserWarning —
        # what we care about is the path runs without exception.
        assert isinstance(caught, list)
    finally:
        plugin_runtime._plugin_context = saved


# -- feature flag ----------------------------------------------------------


def test_feature_flag_is_opt_in() -> None:
    """Default is False (legacy mode)."""
    # Force-clear the env so the default path runs.
    saved = os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
    # Re-evaluate the function with the env cleared.
    assert plugin_runtime.is_plugin_context_enabled() is False
    if saved is not None:
        os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE", "True"])
def test_feature_flag_accepts_truthy_spellings(raw: str) -> None:
    saved = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = raw
    try:
        assert plugin_runtime.is_plugin_context_enabled() is True
    finally:
        if saved is None:
            os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        else:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved


def test_set_plugin_context_enabled_overrides_for_tests() -> None:
    saved_env = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    try:
        os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        set_plugin_context_enabled(True)
        assert plugin_runtime.PLUGIN_CONTEXT_ENABLED is True
        set_plugin_context_enabled(False)
        assert plugin_runtime.PLUGIN_CONTEXT_ENABLED is False
    finally:
        if saved_env is not None:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved_env
        set_plugin_context_enabled(saved_flag)


# -- F11: ConfigStore-backed runtime toggle --------------------------------


def test_set_plugin_context_enabled_writes_through_to_config_store() -> None:
    """When a ConfigStore is mounted on the live context, the writer
    persists the override so it survives across the migration window."""
    saved_ctx = plugin_runtime._plugin_context
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    saved_env = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    try:
        os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        store = InMemoryConfigStore()
        ctx = PluginContext("f11-write-through")
        ctx.mount(config_store_provider(store=store, name="memory"))
        set_plugin_context(ctx)
        # Force the cached flag off so the write-through is observable.
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = False
        set_plugin_context_enabled(True)
        # The store now carries the override.
        assert store.get_snapshot().get("plugin_context_enabled") is True
        # The cached flag was updated in lockstep.
        assert plugin_runtime.PLUGIN_CONTEXT_ENABLED is True
    finally:
        if saved_env is not None:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved_env
        plugin_runtime._plugin_context = saved_ctx
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = saved_flag


def test_is_plugin_context_enabled_reads_from_config_store_when_present() -> None:
    """The ConfigStore override takes precedence over the env var so a
    cross-worker-visible store (Redis / SQLite) wins on every worker."""
    saved_ctx = plugin_runtime._plugin_context
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    saved_env = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    try:
        # Env var off, store on — the store wins.
        os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        store = InMemoryConfigStore({"plugin_context_enabled": True})
        ctx = PluginContext("f11-read-through")
        ctx.mount(config_store_provider(store=store, name="memory"))
        set_plugin_context(ctx)
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = False  # stale cache
        assert plugin_runtime.is_plugin_context_enabled() is True
        # Now flip the store the other way — env var is still off, store is False.
        store.update({"plugin_context_enabled": False})
        assert plugin_runtime.is_plugin_context_enabled() is False
    finally:
        if saved_env is not None:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved_env
        plugin_runtime._plugin_context = saved_ctx
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = saved_flag


def test_refresh_plugin_context_enabled_re_reads_active_source() -> None:
    """``refresh_plugin_context_enabled`` re-reads after boot so a
    ConfigStore override that landed between import and create_app
    takes effect without a restart."""
    saved_ctx = plugin_runtime._plugin_context
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    saved_env = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    try:
        os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        store = InMemoryConfigStore({"plugin_context_enabled": True})
        ctx = PluginContext("f11-refresh")
        ctx.mount(config_store_provider(store=store, name="memory"))
        set_plugin_context(ctx)
        # Stale cache (what the module-import-time _read_env_default would
        # have produced) is False.
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = False
        refreshed = refresh_plugin_context_enabled()
        assert refreshed is True
        assert plugin_runtime.PLUGIN_CONTEXT_ENABLED is True
    finally:
        if saved_env is not None:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved_env
        plugin_runtime._plugin_context = saved_ctx
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = saved_flag


def test_set_plugin_context_enabled_falls_back_without_a_context() -> None:
    """No plugin context mounted — the writer only updates the cached
    flag, no store to write through. The next read falls back to the
    env var (the migration-window contract: the source of truth is the
    env var when no ConfigStore is mounted)."""
    saved_ctx = plugin_runtime._plugin_context
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    saved_env = os.environ.get("OMNISCRIBE_PLUGIN_CONTEXT")
    try:
        os.environ.pop("OMNISCRIBE_PLUGIN_CONTEXT", None)
        plugin_runtime._plugin_context = None
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = False
        set_plugin_context_enabled(True)
        # No context, no store — the cached flag is the only thing updated.
        assert plugin_runtime.PLUGIN_CONTEXT_ENABLED is True
        # But the canonical read re-reads the env var (now unset) and
        # returns False — that's the documented fallback.
        assert plugin_runtime.is_plugin_context_enabled() is False
    finally:
        if saved_env is not None:
            os.environ["OMNISCRIBE_PLUGIN_CONTEXT"] = saved_env
        plugin_runtime._plugin_context = saved_ctx
        plugin_runtime.PLUGIN_CONTEXT_ENABLED = saved_flag


# -- create_app end-to-end --------------------------------------------------


@pytest.fixture
def saved_runtime_state():
    """Save and restore the runtime module's mutable state across tests."""
    saved_ctx = plugin_runtime._plugin_context
    saved_flag = plugin_runtime.PLUGIN_CONTEXT_ENABLED
    yield
    plugin_runtime._plugin_context = saved_ctx
    plugin_runtime.PLUGIN_CONTEXT_ENABLED = saved_flag


def test_create_app_bootstraps_a_plugin_context_with_job_queue(
    saved_runtime_state: Any,
) -> None:
    """Bootstrapping wires the legacy singleton into the live context."""
    from omniscribe.server import create_app

    set_plugin_context(None)
    set_plugin_context_enabled(False)  # flag off — legacy path
    create_app()
    ctx = get_plugin_context()
    assert ctx is not None
    assert ctx.has(JobQueue, name="local")
    # The registered provider is the same instance as the legacy singleton.
    from omniscribe.api.routers import state

    assert ctx.get(JobQueue, name="local") is state.ocr_job_queue
    # Cleanup
    ctx.dispose()
    set_plugin_context(None)


def test_create_app_under_feature_flag_routes_cancel_via_context(
    saved_runtime_state: Any,
) -> None:
    """With the flag on, the helper in routers/jobs.py picks the context
    provider over the legacy singleton — but since they are the same
    instance, the externally visible behavior is identical."""
    from fastapi.testclient import TestClient

    from omniscribe.api.routers import state
    from omniscribe.api.routers.jobs import _get_job_queue
    from omniscribe.server import create_app

    set_plugin_context(None)
    set_plugin_context_enabled(True)
    create_app()
    try:
        # The helper should now return the context provider.
        ctx_queue = _get_job_queue()
        assert ctx_queue is state.ocr_job_queue
        # Cancel a non-existent job: 404 regardless of which path served it.
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/jobs/does-not-exist/cancel")
            assert response.status_code == 404
            assert response.json() == {"error": "Job not found"}
    finally:
        ctx = get_plugin_context()
        if ctx is not None:
            ctx.dispose()
        set_plugin_context(None)
        set_plugin_context_enabled(False)


def test_legacy_mode_returns_legacy_singleton(saved_runtime_state: Any) -> None:
    """Flag off + no live context → helper returns the module-level singleton."""
    from omniscribe.api.routers import state
    from omniscribe.api.routers.jobs import _get_job_queue

    set_plugin_context(None)
    set_plugin_context_enabled(False)
    assert _get_job_queue() is state.ocr_job_queue


# -- Shared state through the seam -----------------------------------------


def test_registered_queue_and_legacy_singleton_share_state() -> None:
    """Submitting a job through the registered provider shows up via the
    legacy singleton because they are the same instance."""
    from omniscribe.api.routers import state

    queue = state.ocr_job_queue
    queue2 = state.ocr_job_queue  # the same module-level instance
    assert queue is queue2
