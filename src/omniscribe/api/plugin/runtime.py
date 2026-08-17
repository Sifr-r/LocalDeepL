"""Live plugin context holder + feature flag.

The :func:`get_plugin_context` accessor returns the boot-time
:class:`PluginContext` that :func:`omniscribe.api.server.create_app`
constructed. Routers and services can call it to look up capability
seam providers by Protocol class.

The :data:`PLUGIN_CONTEXT_ENABLED` flag is opt-in for now. It is read
from the ``OMNISCRIBE_PLUGIN_CONTEXT`` env var and defaults to ``False``.
The legacy singleton-backed access path (``state.ocr_job_queue`` etc.)
remains the source of truth until every consumer has been migrated;
during the migration window a consumer that wants to verify the new
path can branch on :data:`PLUGIN_CONTEXT_ENABLED`.

Phase 7 — typed lookup helpers
------------------------------

This module also ships a small set of typed lookup helpers
(:func:`get_job_queue`, :func:`get_session_log`, etc.) that
consolidate the "look up by Protocol, fall back to None" pattern
every consumer in the migration window needs. The helpers return
``None`` when the context isn't bootstrapped or the slot is
empty, so the call site reads::

    progress = get_progress_service()
    if progress is not None:
        percent = progress.stage_to_percent(...)
    else:
        percent = state.progress_service.stage_to_percent(...)

A consumer that uses the helper is one search-and-replace away
from the legacy singleton — the seam becomes the primary code
path, the legacy alias stays for any code that hasn't migrated.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from omniscribe.api.plugin import PluginContext

logger = logging.getLogger(__name__)


_ENV_VAR = "OMNISCRIBE_PLUGIN_CONTEXT"


def is_plugin_context_enabled() -> bool:
    """True when the runtime plugin context is opted in.

    Reads the ``OMNISCRIBE_PLUGIN_CONTEXT`` env var. Accepts the same
    truthy spellings as a typical CLI flag (``1`` / ``true`` / ``yes``
    / ``on``; case-insensitive). Defaults to ``False`` so the legacy
    singleton-backed access path remains the default during the
    migration window.
    """
    raw = os.getenv(_ENV_VAR, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


#: Module-level flag. Read once at import; settable for tests via
#: :func:`set_plugin_context_enabled`.
PLUGIN_CONTEXT_ENABLED: bool = is_plugin_context_enabled()


def set_plugin_context_enabled(value: bool) -> None:
    """Override the env-var-driven flag. Intended for tests only."""
    global PLUGIN_CONTEXT_ENABLED
    PLUGIN_CONTEXT_ENABLED = bool(value)


#: Module-level handle on the live plugin context. ``None`` before
#: :func:`omniscribe.api.server.create_app` runs. The legacy access
#: path keeps working when this is ``None`` (the default).
_plugin_context: PluginContext | None = None


def set_plugin_context(ctx: PluginContext | None) -> None:
    """Set the live plugin context. Idempotent for re-bootstrapping.

    A warning is logged if a non-None context is replaced; the previous
    context is not auto-disposed (the caller is expected to have
    disposed it before swapping).
    """
    global _plugin_context
    if _plugin_context is not None and ctx is not None and _plugin_context is not ctx:
        logger.warning(
            "Replacing the live plugin context; the previous context was not auto-disposed."
        )
    _plugin_context = ctx


def get_plugin_context() -> PluginContext | None:
    """Return the live plugin context, or None if not yet bootstrapped."""
    return _plugin_context


def get_service(definition: type, *, name: str = "default") -> Any:
    """Convenience wrapper: look up a service from the live context.

    Raises :class:`~omniscribe.api.plugin.ServiceNotFoundError` if the
    context has not been bootstrapped or the service is not registered.
    Callers that want to fall back to the legacy singleton should do so
    themselves; this helper does NOT silently default.
    """
    ctx = get_plugin_context()
    if ctx is None:
        from omniscribe.api.plugin import ServiceNotFoundError

        raise ServiceNotFoundError(definition, name)
    return ctx.get(definition, name=name)


# ---------------------------------------------------------------------------
# Phase 7 — typed lookup helpers for the five Protocol-based services.
# ---------------------------------------------------------------------------
#
# Each helper returns the registered impl for the default (or named)
# slot, or ``None`` if the context isn't bootstrapped or the slot is
# empty. The shape is deliberately "returns None" rather than "raises"
# so the call site is a one-liner with an ``if x is not None:`` branch
# on the legacy path. A future tightening can change the contract to
# "raise" once every consumer has dropped its legacy fallback.
#
# All five helpers import the Protocol class lazily so the import
# order is safe even before :mod:`omniscribe.api.plugin.seams` has
# been fully resolved (e.g. from test modules that stub the
# bootstrap).


def get_job_queue(*, name: str = "local") -> Any | None:
    """Return the registered :class:`JobQueue`, or ``None``.

    The default name matches the in-process provider; a future
    ``"celery"`` provider would register under its own name and
    be reachable via ``get_job_queue(name="celery")``.
    """
    from omniscribe.api.plugin import JobQueue

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(JobQueue, name=name):
        return None
    return ctx.get(JobQueue, name=name)


def get_session_log(*, name: str = "memory") -> Any | None:
    """Return the registered :class:`SessionLog`, or ``None``.

    The default name matches the in-process provider; a future
    ``"sqlite"`` provider would register under its own name.
    """
    from omniscribe.api.plugin import SessionLog

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(SessionLog, name=name):
        return None
    return ctx.get(SessionLog, name=name)


def get_progress_service(*, name: str = "default") -> Any | None:
    """Return the registered :class:`ProgressService`, or ``None``."""
    from omniscribe.api.plugin import ProgressService

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(ProgressService, name=name):
        return None
    return ctx.get(ProgressService, name=name)


def get_config_store(*, name: str = "default") -> Any | None:
    """Return the registered :class:`ConfigStore`, or ``None``."""
    from omniscribe.api.plugin import ConfigStore

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(ConfigStore, name=name):
        return None
    return ctx.get(ConfigStore, name=name)


def get_text_artifact_store(*, name: str = "default") -> Any | None:
    """Return the registered :class:`TextArtifactStore`, or ``None``.

    The three legacy stores register under their canonical names:
    ``"text"``, ``"metadata"``, ``"export"``. Pass the right name
    to reach the right store. The default ``"default"`` slot is
    also accepted for tests and ad-hoc consumers.
    """
    from omniscribe.api.plugin import TextArtifactStore

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(TextArtifactStore, name=name):
        return None
    return ctx.get(TextArtifactStore, name=name)


__all__ = [
    "PLUGIN_CONTEXT_ENABLED",
    "get_config_store",
    "get_job_queue",
    "get_plugin_context",
    "get_progress_service",
    "get_service",
    "get_session_log",
    "get_text_artifact_store",
    "is_plugin_context_enabled",
    "set_plugin_context",
    "set_plugin_context_enabled",
]
