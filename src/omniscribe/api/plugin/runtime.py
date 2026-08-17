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


__all__ = [
    "PLUGIN_CONTEXT_ENABLED",
    "get_plugin_context",
    "get_service",
    "is_plugin_context_enabled",
    "set_plugin_context",
    "set_plugin_context_enabled",
]
