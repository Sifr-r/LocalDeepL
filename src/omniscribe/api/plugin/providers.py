"""Service providers for the plugin context.

A **provider** is a callable (a :class:`~omniscribe.api.plugin.Plugin`) that
mounts one or more Service Definitions into a :class:`PluginContext`. Each
provider corresponds to one runtime implementation of a capability seam.

Phase 1 ships a single provider — the in-process OCR job queue. Phase 3
adds the in-memory session log provider. Future phases add providers
for the rest of the capability seams (state, auth, document export,
glossary import, provider manager, telemetry, etc.).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

# Note: import the inner modules directly to avoid a circular import with
# the top-level ``omniscribe.api.plugin`` package's __init__ (which re-exports
# the providers for convenience).
from omniscribe.api.plugin.context import PluginContext
from omniscribe.api.plugin.seams import JobQueue, SessionLog
from omniscribe.api.plugin.session_log import InMemoryLogStore
from omniscribe.api.services.ocr_jobs import OCRJobQueue

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


__all__ = ["in_memory_session_log_provider", "local_job_queue_provider"]
