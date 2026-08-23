"""Service providers for the plugin context.

A **provider** is a callable (a :class:`~omniscribe.api.plugin.Plugin`) that
mounts one or more Service Definitions into a :class:`PluginContext`. Each
provider corresponds to one runtime implementation of a capability seam.

Phase 1 ships a single provider — the in-process OCR job queue. Phase 3
adds the in-memory session log provider. Future phases add providers
for the rest of the capability seams (state, auth, document export,
glossary import, provider manager, telemetry, etc.).

Disposal contract
-----------------

Every provider factory in this module returns a :class:`Plugin` closure.
When :func:`omniscribe.api.server.create_app` calls
``plugin_ctx.mount(plugin)``, the closure runs once: it calls
``ctx.register(Protocol, impl, name=...)`` and returns the resulting
disposer to :class:`PluginContext` as a reversible effect.

At shutdown, the FastAPI lifespan's ``_teardown_plugin_context`` (see
``server.py:220-225``) calls ``plugin_ctx.dispose()``, which runs every
disposer in **reverse mount order**.

Providers should be idempotent and side-effect-free outside the
``ctx.register`` call; any cleanup work happens in the disposer closure
returned by the :meth:`ctx.register` implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

# Note: import the inner modules directly to avoid a circular import with
# the top-level ``omniscribe.api.plugin`` package's __init__ (which re-exports
# the providers for convenience).
from omniscribe.api.plugin.context import PluginContext
from omniscribe.api.plugin.seams import (
    ConfigStore,
    JobQueue,
    ProgressService,
    SessionLog,
    TextArtifactStore,
)
from omniscribe.api.plugin.session_log import InMemoryLogStore
from omniscribe.api.services.artifacts import TextArtifactStore as _TextArtifactStore
from omniscribe.api.services.config_store import (
    ConfigStore as _ConfigStore,
)
from omniscribe.api.services.config_store import (
    InMemoryConfigStore,
)
from omniscribe.api.services.ocr_jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService as _ProgressService

logger = logging.getLogger(__name__)


def local_job_queue_provider(
    queue: OCRJobQueue | None = None,
    *,
    name: str = "local",
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that registers an in-process :class:`OCRJobQueue`.

    Parameters
    ----------
    queue:
        The queue instance to register. When ``None`` (default), a fresh
        :class:`OCRJobQueue` is constructed. Pass an existing instance to
        share state with the legacy ``state.ocr_job_queue`` singleton
        during the migration window.
    name:
        Provider name under which the queue is registered. Defaults to
        ``"local"`` so the future Celery provider can register under
        ``"celery"``.
    """
    impl = queue if queue is not None else OCRJobQueue()

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposer = ctx.register(JobQueue, impl, name=name)
        logger.info(
            "Registered JobQueue provider name=%r (%s)", name, type(impl).__name__
        )
        return disposer

    return _plugin


def in_memory_session_log_provider(
    log: InMemoryLogStore | None = None,
    *,
    name: str = "memory",
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that registers an in-memory :class:`SessionLog`.

    Parameters
    ----------
    log:
        Pre-built log instance to register. When ``None``
        (default), a fresh :class:`InMemoryLogStore` is
        constructed. The migration shim in Phase 3c will pass
        a shared instance so :class:`JobHistory` and the log
        see the same events.
    name:
        Provider name. Defaults to ``"memory"`` so a future
        ``"sqlite"`` provider can register alongside.
    """
    impl = log if log is not None else InMemoryLogStore()

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposer = ctx.register(SessionLog, impl, name=name)
        logger.info(
            "Registered SessionLog provider name=%r (%s)", name, type(impl).__name__
        )
        return disposer

    return _plugin


def progress_service_provider(
    service: _ProgressService | None = None,
    *,
    name: str = "memory",
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that registers a :class:`ProgressService`.

    The default :class:`~omniscribe.api.services.progress.ProgressService`
    is stateless (every method is a pure function of its arguments)
    so the same instance can be shared by every consumer — the
    provider just wraps the existing ``state.progress_service``
    singleton and registers it under the seam Protocol.

    Parameters
    ----------
    service:
        Pre-built service. ``None`` (default) constructs a fresh
        :class:`ProgressService`. Tests pass a stub to assert
        consumer behaviour without standing up the real math.
    name:
        Provider name. Defaults to ``"memory"`` (audit-secondary
        F14 — the in-process implementation has no distributed
        variant today; if one is added, it registers under its
        own name and a profile can run both side by side). The
        same convention is used by
        :func:`in_memory_session_log_provider` (``"memory"``)
        and :func:`local_job_queue_provider` (``"local"``).
    """
    impl = service if service is not None else _ProgressService()

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposer = ctx.register(ProgressService, impl, name=name)
        logger.info(
            "Registered ProgressService provider name=%r (%s)",
            name,
            type(impl).__name__,
        )
        return disposer

    return _plugin


def config_store_provider(
    store: _ConfigStore | None = None,
    *,
    name: str = "memory",
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that registers a :class:`ConfigStore`.

    The :class:`ConfigStore` Protocol already lives in
    :mod:`omniscribe.api.services.config_store`; this provider
    just bridges the existing ``state.config_store`` singleton
    into the plugin context. The three concrete implementations
    (:class:`InMemoryConfigStore` / :class:`SQLiteConfigStore`
    / :class:`RedisConfigStore`) all satisfy the Protocol, so
    swapping the active store only requires passing a different
    instance to this provider — no consumer code changes.

    Parameters
    ----------
    store:
        Pre-built store. ``None`` (default) constructs a fresh
        :class:`InMemoryConfigStore`. Production callers pass
        the same instance the StateBackend owns so the
        ``/api/config`` handler and the seam see one source of
        truth.
    name:
        Provider name. Defaults to ``"memory"`` (audit-secondary
        F14 — backend-kind convention; matches the
        :func:`in_memory_session_log_provider` default so a
        single diagnostic can list providers by kind).
    """
    impl = store if store is not None else InMemoryConfigStore()

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposer = ctx.register(ConfigStore, impl, name=name)
        logger.info(
            "Registered ConfigStore provider name=%r (%s)", name, type(impl).__name__
        )
        return disposer

    return _plugin


def text_artifact_store_provider(
    store: _TextArtifactStore,
    *,
    name: str = "text",
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that registers a :class:`TextArtifactStore`.

    The legacy :mod:`~omniscribe.api.routers.state` module owns
    three :class:`TextArtifactStore` instances (``text_artifacts``
    / ``metadata_artifacts`` / ``export_artifacts``). Phase 5
    registers each one under a distinct name so a consumer can
    request the metadata store explicitly:

    - ``ctx.get(TextArtifactStore, name="text")`` — the canonical
      per-page OCR text artifacts
    - ``ctx.get(TextArtifactStore, name="metadata")`` — the
      document-processor metadata reports
    - ``ctx.get(TextArtifactStore, name="export")`` — the export
      pipeline outputs (HTML / DOCX / tree)

    The default name is ``"text"`` (audit-secondary F14 — the
    "text" store is the most common consumer, and the three
    domain names are not backend kinds). Production wiring still
    passes the right name explicitly.

    Parameters
    ----------
    store:
        Pre-built store. The provider does not construct a
        default — the constructor requires an ``artifact_dir``
        and Phase 5 has no opinion about the default location
        (the StateBackend picks one).
    name:
        Provider name. Production wiring uses ``"text"``,
        ``"metadata"``, or ``"export"``.
    """
    if not isinstance(store, _TextArtifactStore):
        raise TypeError(
            f"text_artifact_store_provider requires a TextArtifactStore "
            f"instance, got {type(store).__name__!r}"
        )

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposer = ctx.register(TextArtifactStore, store, name=name)
        logger.info(
            "Registered TextArtifactStore provider name=%r (%s)",
            name,
            type(store).__name__,
        )
        return disposer

    return _plugin


__all__ = [
    "config_store_provider",
    "in_memory_session_log_provider",
    "local_job_queue_provider",
    "progress_service_provider",
    "text_artifact_store_provider",
]
