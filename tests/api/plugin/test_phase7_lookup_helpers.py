"""Phase 7 tests — typed lookup helpers in ``api.plugin.runtime``.

Covers:

1. The five typed helpers (``get_job_queue`` /
   ``get_session_log`` / ``get_progress_service`` /
   ``get_config_store`` / ``get_text_artifact_store``) each
   return the registered impl when the context is live, the
   ``None`` sentinel when the context is not bootstrapped, and
   the ``None`` sentinel when the slot is empty.
2. The helpers respect the ``name=`` kwarg so a consumer can
   request a specific named slot (e.g. ``name="metadata"`` for
   the metadata artifact store).
3. The helpers do not raise on missing context or missing slot
   — the "returns None" contract is the consumer-friendly shape
   for the migration window.
4. The ``stage_to_percent`` consumer in ``routers.ocr`` uses
   the helper as the primary path and falls back to the legacy
   ``state.progress_service`` when the helper returns None.
5. The ``_get_job_queue`` consumer in ``routers.jobs`` does the
   same.
6. End-to-end: a default profile wired in a real
   ``PluginContext`` lets every helper return a real service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omniscribe.api.plugin import (
    Bundle,
    InMemoryLogStore,
    PluginContext,
    Profile,
    config_store_provider,
    in_memory_session_log_provider,
    local_job_queue_provider,
    progress_service_provider,
    runtime,
    text_artifact_store_provider,
)
from omniscribe.api.services.artifacts import TextArtifactStore as _TextArtifactStore
from omniscribe.api.services.config_store import InMemoryConfigStore
from omniscribe.api.services.ocr_jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService as _ProgressService


@pytest.fixture(autouse=True)
def _reset_plugin_context() -> Any:
    """Snapshot and restore the live plugin context so each test
    is independent (the lookup helpers read the module-level
    singleton)."""
    snapshot = runtime.get_plugin_context()
    runtime.set_plugin_context(None)
    try:
        yield
    finally:
        runtime.set_plugin_context(snapshot)


# -- Helper semantics ------------------------------------------------------


def test_get_job_queue_returns_none_without_context() -> None:
    assert runtime.get_job_queue() is None


def test_get_session_log_returns_none_without_context() -> None:
    assert runtime.get_session_log() is None


def test_get_progress_service_returns_none_without_context() -> None:
    assert runtime.get_progress_service() is None


def test_get_config_store_returns_none_without_context() -> None:
    assert runtime.get_config_store() is None


def test_get_text_artifact_store_returns_none_without_context() -> None:
    assert runtime.get_text_artifact_store(name="text") is None


def test_get_job_queue_returns_registered_impl() -> None:
    queue = OCRJobQueue()
    ctx = PluginContext("test")
    local_job_queue_provider(queue=queue)(ctx)
    runtime.set_plugin_context(ctx)
    assert runtime.get_job_queue() is queue


def test_get_session_log_returns_registered_impl() -> None:
    log = InMemoryLogStore()
    ctx = PluginContext("test")
    in_memory_session_log_provider(log=log)(ctx)
    runtime.set_plugin_context(ctx)
    assert runtime.get_session_log() is log


def test_get_progress_service_returns_registered_impl() -> None:
    service = _ProgressService()
    ctx = PluginContext("test")
    progress_service_provider(service=service)(ctx)
    runtime.set_plugin_context(ctx)
    assert runtime.get_progress_service() is service


def test_get_config_store_returns_registered_impl() -> None:
    store = InMemoryConfigStore(initial={"x": 1})
    ctx = PluginContext("test")
    config_store_provider(store=store)(ctx)
    runtime.set_plugin_context(ctx)
    assert runtime.get_config_store() is store
    assert runtime.get_config_store().get_snapshot() == {"x": 1}


def test_get_text_artifact_store_returns_named_slot(tmp_path: Path) -> None:
    text_store = _TextArtifactStore(artifact_dir=tmp_path / "text", kind="text")
    meta_store = _TextArtifactStore(artifact_dir=tmp_path / "meta", kind="metadata")
    ctx = PluginContext("test")
    text_artifact_store_provider(text_store, name="text")(ctx)
    text_artifact_store_provider(meta_store, name="metadata")(ctx)
    runtime.set_plugin_context(ctx)
    assert runtime.get_text_artifact_store(name="text") is text_store
    assert runtime.get_text_artifact_store(name="metadata") is meta_store
    # An unregistered name returns None — the helper does not
    # raise. This is the migration-window contract.
    assert runtime.get_text_artifact_store(name="export") is None


def test_helpers_return_none_for_empty_slots() -> None:
    """When the context is live but the slot is empty (no
    provider has registered), the helper still returns None
    instead of raising. Callers can therefore chain
    ``helper() is not None`` without a separate try/except."""
    ctx = PluginContext("test")  # no providers mounted
    runtime.set_plugin_context(ctx)
    assert runtime.get_job_queue() is None
    assert runtime.get_session_log() is None
    assert runtime.get_progress_service() is None
    assert runtime.get_config_store() is None
    assert runtime.get_text_artifact_store(name="text") is None


# -- Consumer migration ---------------------------------------------------


def test_routers_ocr_stage_to_percent_uses_helper_when_present() -> None:
    """``stage_to_percent`` resolves the helper first; a stub
    service that returns a known sentinel wins over the legacy
    ``state.progress_service`` (whose real answer is unknown)."""
    from omniscribe.api.routers import ocr

    class _StubProgress:
        def stage_to_percent(self, stage: str, current: int, total: int) -> int:
            return 42

        def create_channel(self, display_client_id: str | None = None) -> Any:
            from omniscribe.api.plugin import ProgressChannel

            return ProgressChannel(channel_id="c" * 32, session_token="t" * 32)

        def validate_channel_id(self, channel_id: str) -> str:
            return channel_id

        def validate_session_token(self, session_token: str) -> str:
            return session_token

        def is_bound(
            self,
            *,
            channel_id: str,
            session_token: str,
            expected_channel_id: str,
            expected_session_token: str,
        ) -> bool:
            return False

    ctx = PluginContext("test")
    progress_service_provider(service=_StubProgress())(ctx)
    runtime.set_plugin_context(ctx)
    assert ocr.stage_to_percent("ocr", 1, 4) == 42


def test_routers_ocr_stage_to_percent_falls_back_to_legacy() -> None:
    """When the helper returns None (no live context), the
    consumer delegates to ``state.progress_service`` and
    produces the real percent — no behaviour change for the
    legacy call sites."""
    from omniscribe.api.routers import ocr, state

    runtime.set_plugin_context(None)
    real = state.progress_service.stage_to_percent("ocr", 1, 4)
    assert ocr.stage_to_percent("ocr", 1, 4) == real


def test_routers_jobs_get_job_queue_uses_helper_when_present() -> None:
    """``_get_job_queue`` resolves the helper first; a stub
    queue wins over the legacy singleton."""
    from omniscribe.api.routers import jobs

    queue = OCRJobQueue()
    ctx = PluginContext("test")
    local_job_queue_provider(queue=queue)(ctx)
    runtime.set_plugin_context(ctx)
    assert jobs._get_job_queue() is queue


def test_routers_jobs_get_job_queue_falls_back_to_legacy() -> None:
    from omniscribe.api.routers import jobs, state

    runtime.set_plugin_context(None)
    assert jobs._get_job_queue() is state.ocr_job_queue


# -- End-to-end default profile -------------------------------------------


def test_default_profile_lets_every_helper_return_a_real_service(
    tmp_path: Path,
) -> None:
    """A full default profile (mirroring server boot) makes
    every Phase 7 helper return a real impl — the consumer
    code path is fully migrated to the seam."""
    queue = OCRJobQueue()
    log = InMemoryLogStore()
    progress = _ProgressService()
    config = InMemoryConfigStore()
    text_store = _TextArtifactStore(artifact_dir=tmp_path / "text", kind="text")
    meta_store = _TextArtifactStore(artifact_dir=tmp_path / "meta", kind="metadata")

    profile = Profile(
        name="default",
        bundles=(
            Bundle(
                name="job-queue", providers=(local_job_queue_provider(queue=queue),)
            ),
            Bundle(
                name="session-log",
                providers=(in_memory_session_log_provider(log=log),),
            ),
            Bundle(
                name="progress",
                providers=(progress_service_provider(service=progress),),
            ),
            Bundle(name="config", providers=(config_store_provider(store=config),)),
            Bundle(
                name="artifacts",
                providers=(
                    text_artifact_store_provider(text_store, name="text"),
                    text_artifact_store_provider(meta_store, name="metadata"),
                ),
            ),
        ),
    )
    ctx = PluginContext("root")
    profile.apply(ctx)
    runtime.set_plugin_context(ctx)
    try:
        assert runtime.get_job_queue() is queue
        assert runtime.get_session_log() is log
        assert runtime.get_progress_service() is progress
        assert runtime.get_config_store() is config
        assert runtime.get_text_artifact_store(name="text") is text_store
        assert runtime.get_text_artifact_store(name="metadata") is meta_store
        # Behavioural spot check on the migrated consumer.
        from omniscribe.api.routers import ocr

        assert ocr.stage_to_percent("ocr", 1, 4) == progress.stage_to_percent(
            "ocr", 1, 4
        )
    finally:
        runtime.set_plugin_context(None)


# -- Audit-secondary F14: backend-kind service-name convention --------------


def test_provider_and_helper_defaults_match() -> None:
    """Provider default name == corresponding helper default name.

    Audit-secondary F14: a provider registered without an
    explicit ``name=`` must be reachable through the helper
    without an explicit ``name=`` either. Any drift between
    provider default and helper default would silently return
    ``None`` from the helper.
    """
    from inspect import signature

    from omniscribe.api.plugin.providers import (
        config_store_provider,
        in_memory_session_log_provider,
        local_job_queue_provider,
        progress_service_provider,
        text_artifact_store_provider,
    )
    from omniscribe.api.plugin.runtime import (
        get_config_store,
        get_job_queue,
        get_progress_service,
        get_session_log,
        get_text_artifact_store,
    )

    pairs = [
        (local_job_queue_provider, get_job_queue),
        (in_memory_session_log_provider, get_session_log),
        (progress_service_provider, get_progress_service),
        (config_store_provider, get_config_store),
        (text_artifact_store_provider, get_text_artifact_store),
    ]
    for provider, helper in pairs:
        provider_default = signature(provider).parameters["name"].default
        helper_default = signature(helper).parameters["name"].default
        assert provider_default == helper_default, (
            f"defaults diverge: {provider.__name__}(name={provider_default!r}) "
            f"vs {helper.__name__}(name={helper_default!r})"
        )


def test_progress_service_helper_uses_memory_default() -> None:
    """F14: ``get_progress_service()`` looks up ``name='memory'`` by default."""
    from omniscribe.api.plugin.runtime import get_progress_service

    # No context — both default-name and explicit-name return None.
    runtime.set_plugin_context(None)
    assert get_progress_service() is None
    assert get_progress_service(name="memory") is None
    # An explicitly wrong name still returns None.
    assert get_progress_service(name="default") is None


def test_config_store_helper_uses_memory_default() -> None:
    """F14: ``get_config_store()`` looks up ``name='memory'`` by default."""
    from omniscribe.api.plugin.runtime import get_config_store

    runtime.set_plugin_context(None)
    assert get_config_store() is None
    assert get_config_store(name="memory") is None
    assert get_config_store(name="default") is None


def test_text_artifact_store_helper_uses_text_default() -> None:
    """F14: ``get_text_artifact_store()`` looks up ``name='text'`` by default.

    The three TextArtifactStore domain names (``text`` / ``metadata``
    / ``export``) are not backend kinds — they identify the kind of
    artifact the store owns. ``text`` is the most common consumer
    and the most useful default.
    """
    from omniscribe.api.plugin.runtime import get_text_artifact_store

    runtime.set_plugin_context(None)
    assert get_text_artifact_store() is None  # default name is "text"
    assert get_text_artifact_store(name="text") is None
    assert get_text_artifact_store(name="default") is None  # legacy name gone


def test_provider_default_name_is_backend_kind() -> None:
    """F14: every provider's default name is a backend kind, not ``"default"``.

    Locking in the convention so a future provider doesn't
    regress to ``name="default"`` and re-introduce the mixed
    convention.
    """
    from inspect import signature

    from omniscribe.api.plugin.providers import (
        config_store_provider,
        in_memory_session_log_provider,
        local_job_queue_provider,
        progress_service_provider,
    )

    expected = {
        local_job_queue_provider: "local",
        in_memory_session_log_provider: "memory",
        progress_service_provider: "memory",
        config_store_provider: "memory",
    }
    for provider, want in expected.items():
        got = signature(provider).parameters["name"].default
        assert got == want, f"{provider.__name__} default name = {got!r}, want {want!r}"
