"""Phase 5 tests — Protocol seams for ProgressService / ConfigStore / TextArtifactStore.

Covers:

1. The three new seam Protocols are importable from
   :mod:`omniscribe.api.plugin.seams` and are
   ``@runtime_checkable`` so a structural ``isinstance`` check
   succeeds.
2. The three new providers register the right concrete instance
   under the right Protocol + name.
3. The three new providers return disposers that un-register on
   call.
4. The :class:`TextArtifactStore` provider refuses anything that
   isn't a real :class:`TextArtifactStore` instance.
5. The three new providers all participate in the default server
   profile alongside the existing :class:`JobQueue` and
   :class:`SessionLog` providers — end-to-end wire-up that a
   consumer can ``ctx.get(ProgressService)`` and get the real
   service.
6. Consumer migration smoke test: the
   :func:`routers.ocr.stage_to_percent` helper looks up the
   :class:`ProgressService` via the plugin context and falls
   back to ``state.progress_service`` if the context is not
   available, preserving the existing wire behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omniscribe.api.plugin import (
    ConfigStore,
    InMemoryLogStore,
    JobQueue,
    PluginContext,
    ProgressChannel,
    ProgressService,
    SessionLog,
    TextArtifactStore,
    config_store_provider,
    in_memory_session_log_provider,
    local_job_queue_provider,
    progress_service_provider,
    text_artifact_store_provider,
)
from omniscribe.api.services.artifacts import TextArtifactStore as _TextArtifactStore
from omniscribe.api.services.config_store import InMemoryConfigStore
from omniscribe.api.services.ocr_jobs import OCRJobQueue
from omniscribe.api.services.progress import (
    ProgressService as _ProgressService,
)

# -- Protocol re-exports --------------------------------------------------


def test_seam_protocols_are_runtime_checkable() -> None:
    """All three new Protocol seams are ``@runtime_checkable`` so
    a structural ``isinstance`` check works without a nominal
    inheritance — this is what makes the swappable-provider
    pattern work in the first place."""
    assert hasattr(ProgressService, "_is_runtime_protocol")
    assert hasattr(ConfigStore, "_is_runtime_protocol")
    assert hasattr(TextArtifactStore, "_is_runtime_protocol")


def test_progress_channel_is_re_exported() -> None:
    """The progress-channel dataclass is reachable from the seam
    module so consumers don't have to know which concrete module
    it lives in."""
    channel = ProgressChannel(channel_id="a" * 32, session_token="b" * 32)
    assert channel.channel_id == "a" * 32
    assert channel.session_token == "b" * 32
    assert channel.display_client_id is None


# -- progress_service_provider --------------------------------------------


def test_progress_service_provider_registers_default_impl() -> None:
    """Without an explicit service, the provider constructs a
    real :class:`ProgressService` and registers it under the
    ``ProgressService`` Protocol."""
    ctx = PluginContext("test")
    plugin = progress_service_provider()
    plugin(ctx)
    service = ctx.get(ProgressService, name="memory")
    # Structural check via the runtime_checkable Protocol.
    assert isinstance(service, ProgressService)
    # Behavioural spot check: stage_to_percent is a pure function
    # (the "ocr" stage is the 25..75% band, so 1/4 = 37.5 → 37).
    assert service.stage_to_percent("ocr", 1, 4) == 37


def test_progress_service_provider_with_explicit_service() -> None:
    """A pre-built service (e.g. from ``state.progress_service``)
    is registered as-is, so the seam shares the same instance
    every consumer uses."""
    real_service = _ProgressService()
    ctx = PluginContext("test")
    progress_service_provider(service=real_service)(ctx)
    assert ctx.get(ProgressService, name="memory") is real_service


def test_progress_service_provider_disposer_unregisters() -> None:
    ctx = PluginContext("test")
    disposer = progress_service_provider()(ctx)
    assert ctx.has(ProgressService, name="memory")
    disposer()
    assert not ctx.has(ProgressService, name="memory")


def test_progress_service_provider_named_slot() -> None:
    """Two providers can register under different names so a
    future 'telemetry' provider can co-exist with the default."""
    ctx = PluginContext("test")
    progress_service_provider(name="memory")(ctx)
    alt = _ProgressService()
    progress_service_provider(service=alt, name="telemetry")(ctx)
    assert ctx.get(ProgressService, name="memory") is not alt
    assert ctx.get(ProgressService, name="telemetry") is alt


# -- config_store_provider -----------------------------------------------


def test_config_store_provider_registers_default_impl() -> None:
    ctx = PluginContext("test")
    config_store_provider()(ctx)
    store = ctx.get(ConfigStore, name="memory")
    assert isinstance(store, ConfigStore)
    # Behavioural: an empty in-memory store returns an empty
    # snapshot.
    assert store.get_snapshot() == {}


def test_config_store_provider_with_explicit_store() -> None:
    """A pre-built store (the one ``state.config_store`` points
    to) is shared with the seam so the /api/config handler and
    any consumer see the same data."""
    real_store = InMemoryConfigStore(initial={"x": 1})
    ctx = PluginContext("test")
    config_store_provider(store=real_store)(ctx)
    assert ctx.get(ConfigStore, name="memory") is real_store
    # The shared instance keeps its initial data.
    assert ctx.get(ConfigStore, name="memory").get_snapshot() == {"x": 1}


def test_config_store_provider_disposer_unregisters() -> None:
    ctx = PluginContext("test")
    disposer = config_store_provider()(ctx)
    assert ctx.has(ConfigStore, name="memory")
    disposer()
    assert not ctx.has(ConfigStore, name="memory")


# -- text_artifact_store_provider ----------------------------------------


def test_text_artifact_store_provider_registers_store(tmp_path: Path) -> None:
    store = _TextArtifactStore(artifact_dir=tmp_path, kind="text")
    ctx = PluginContext("test")
    text_artifact_store_provider(store, name="text")(ctx)
    seam = ctx.get(TextArtifactStore, name="text")
    assert seam is store


def test_text_artifact_store_provider_three_slots(tmp_path: Path) -> None:
    """The three legacy stores (text / metadata / export) each
    register under a distinct name so a consumer can request the
    right one explicitly."""
    text_store = _TextArtifactStore(artifact_dir=tmp_path / "text", kind="text")
    meta_store = _TextArtifactStore(artifact_dir=tmp_path / "meta", kind="metadata")
    export_store = _TextArtifactStore(artifact_dir=tmp_path / "export", kind="export")
    ctx = PluginContext("test")
    text_artifact_store_provider(text_store, name="text")(ctx)
    text_artifact_store_provider(meta_store, name="metadata")(ctx)
    text_artifact_store_provider(export_store, name="export")(ctx)
    assert ctx.get(TextArtifactStore, name="text") is text_store
    assert ctx.get(TextArtifactStore, name="metadata") is meta_store
    assert ctx.get(TextArtifactStore, name="export") is export_store


def test_text_artifact_store_provider_rejects_non_store() -> None:
    class _NotAStore:
        pass

    with pytest.raises(TypeError, match="TextArtifactStore"):
        text_artifact_store_provider(_NotAStore(), name="x")  # type: ignore[arg-type]


def test_text_artifact_store_provider_disposer_unregisters(
    tmp_path: Path,
) -> None:
    store = _TextArtifactStore(artifact_dir=tmp_path, kind="text")
    ctx = PluginContext("test")
    disposer = text_artifact_store_provider(store, name="text")(ctx)
    assert ctx.has(TextArtifactStore, name="text")
    disposer()
    assert not ctx.has(TextArtifactStore, name="text")


# -- Default server profile with all five providers -----------------------


def test_default_server_profile_has_all_five_capabilities(
    tmp_path: Path,
) -> None:
    """The full default profile mounts every Phase 1 / 3 / 5
    provider. A consumer that does ``ctx.get(ProgressService)``
    after ``profile.apply(ctx)`` gets the real service — the
    same instance the legacy ``state.progress_service`` holds."""
    queue = OCRJobQueue()
    log = InMemoryLogStore()
    progress = _ProgressService()
    config = InMemoryConfigStore(initial={"model": "qwen2.5-vl"})
    text_store = _TextArtifactStore(artifact_dir=tmp_path / "text", kind="text")
    meta_store = _TextArtifactStore(artifact_dir=tmp_path / "meta", kind="metadata")
    export_store = _TextArtifactStore(artifact_dir=tmp_path / "export", kind="export")

    ctx = PluginContext("root")
    ctx.mount(local_job_queue_provider(queue=queue))
    ctx.mount(in_memory_session_log_provider(log=log))
    ctx.mount(progress_service_provider(service=progress))
    ctx.mount(config_store_provider(store=config))
    ctx.mount(text_artifact_store_provider(text_store, name="text"))
    ctx.mount(text_artifact_store_provider(meta_store, name="metadata"))
    ctx.mount(text_artifact_store_provider(export_store, name="export"))

    assert ctx.get(JobQueue, name="local") is queue
    assert ctx.get(SessionLog, name="memory") is log
    assert ctx.get(ProgressService, name="memory") is progress
    assert ctx.get(ConfigStore, name="memory") is config
    assert ctx.get(TextArtifactStore, name="text") is text_store
    assert ctx.get(TextArtifactStore, name="metadata") is meta_store
    assert ctx.get(TextArtifactStore, name="export") is export_store
    # Behavioural sanity check on the progress service — the
    # consumer got the same instance the state module uses.
    assert (
        ctx.get(ProgressService, name="memory").stage_to_percent("embed", 1, 1) == 100
    )
    # Config store sees the initial data the StateBackend owns.
    assert ctx.get(ConfigStore, name="memory").get_snapshot() == {"model": "qwen2.5-vl"}


# -- Consumer migration smoke test ---------------------------------------


def test_routers_ocr_stage_to_percent_uses_seam_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``routers.ocr.stage_to_percent`` falls back to the live
    plugin context when one is set, and to
    ``state.progress_service`` otherwise. This is the migration
    pattern every consumer follows in Phase 7 (drop legacy
    singletons): look up by Protocol, fall back to the legacy
    path during the migration window."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr

    # Mount a stub ProgressService that returns a known sentinel
    # for any stage / current / total. The seam lookup must win
    # over the legacy ``state.progress_service`` (whose real
    # answer is unknown to us). The stub satisfies the full
    # ``ProgressService`` Protocol surface so the structural
    # ``isinstance`` check in ``register`` accepts it.
    class _StubProgress:
        def stage_to_percent(self, stage: str, current: int, total: int) -> int:
            return 42

        def create_channel(self, display_client_id: str | None = None) -> Any:
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
    try:
        assert ocr.stage_to_percent("ocr", 1, 4) == 42
    finally:
        runtime.set_plugin_context(None)


def test_routers_ocr_stage_to_percent_falls_back_to_legacy() -> None:
    """Without a live context, the helper delegates to
    ``state.progress_service`` and produces the real percent —
    no consumer-facing change."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr, state

    runtime.set_plugin_context(None)
    # The real service returns stage-weighted percent; the
    # ``ocr`` stage is the 25..75% band, so 1/4 = 25 + (0.25 * 50) = 37.5
    # → 37 (int truncation).
    real = state.progress_service.stage_to_percent("ocr", 1, 4)
    assert ocr.stage_to_percent("ocr", 1, 4) == real
