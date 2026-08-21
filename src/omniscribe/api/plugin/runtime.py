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

Service-name convention (audit-secondary F14)
---------------------------------------------

Every helper's default name matches the corresponding provider's
default name in :mod:`omniscribe.api.plugin.providers`, so a
provider registered without an explicit ``name=`` is reachable
through the helper without an explicit ``name=`` either. The
convention is **backend kind** for capability seams and
**domain name** for the artifact store triple:

| Helper / Provider                           | Default name  | Reason                          |
|---------------------------------------------|---------------|---------------------------------|
| :func:`get_job_queue`                       | ``"local"``   | in-process vs future Celery     |
| :func:`get_session_log`                     | ``"memory"``  | in-memory vs future SQLite/JSONL|
| :func:`get_progress_service`                | ``"memory"``  | in-process (no distributed)     |
| :func:`get_config_store`                    | ``"memory"``  | in-memory vs SQLite/Redis       |
| :func:`get_text_artifact_store`             | ``"text"``    | text / metadata / export        |

The three ``TextArtifactStore`` names are domain names, not
backend kinds — a profile can register the same backend under
all three names. A diagnostic that lists ``(definition, name)``
pairs should see this convention encoded in the helper defaults
so a "what providers are wired?" report is one line per entry.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, cast

from omniscribe.api.plugin import PluginContext

if TYPE_CHECKING:
    from omniscribe.api.services.config_store import ConfigStore

logger = logging.getLogger(__name__)


_ENV_VAR = "OMNISCRIBE_PLUGIN_CONTEXT"
_CONFIG_KEY = "plugin_context_enabled"


def _read_env_default() -> bool:
    """Parse :data:`_ENV_VAR` into a boolean.

    Accepts the same truthy spellings as a typical CLI flag (``1`` /
    ``true`` / ``yes`` / ``on``; case-insensitive). Returns ``False``
    when the var is unset or unrecognised.
    """
    raw = os.getenv(_ENV_VAR, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _lookup_active_config_store() -> ConfigStore | None:
    """Return the ConfigStore mounted on the live plugin context, if any.

    Returns ``None`` when no plugin context is bootstrapped or no
    ConfigStore is mounted; :func:`is_plugin_context_enabled` and
    :func:`refresh_plugin_context_enabled` fall back to the env-var in
    that case. The lookup name matches the
    :func:`config_store_provider` default so the in-memory store
    mounted at server boot is reachable without an explicit name.
    """
    from omniscribe.api.plugin import ConfigStore

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(ConfigStore, name="memory"):
        return None
    store = ctx.get(ConfigStore, name="memory")
    # ``PluginContext.get`` returns ``Any`` by design; the lookup is
    # gated by ``ctx.has`` above so the value structurally satisfies
    # the :class:`ConfigStore` Protocol. Cast for mypy.
    from omniscribe.api.services.config_store import ConfigStore as _ConfigStore

    return cast("_ConfigStore", store)


def is_plugin_context_enabled() -> bool:
    """True when the runtime plugin context is opted in.

    Reads :data:`_CONFIG_KEY` from the active :class:`ConfigStore` if
    one is mounted on the live plugin context; falls back to the
    :data:`_ENV_VAR` env var otherwise. The function is the canonical
    read; the module-level :data:`PLUGIN_CONTEXT_ENABLED` is a cache
    that :func:`refresh_plugin_context_enabled` and
    :func:`set_plugin_context_enabled` keep in sync.
    """
    store = _lookup_active_config_store()
    if store is not None:
        snapshot = store.get_snapshot()
        if _CONFIG_KEY in snapshot:
            return bool(snapshot[_CONFIG_KEY])
    return _read_env_default()


#: Module-level flag. Cached value of :func:`is_plugin_context_enabled`
#: last observed at module import, at :func:`refresh_plugin_context_enabled`
#: time, or after the most recent :func:`set_plugin_context_enabled`
#: write. Tests can read or override it directly; production consumers
#: should call :func:`is_plugin_context_enabled` so a ConfigStore
#: override that landed after import is honoured.
PLUGIN_CONTEXT_ENABLED: bool = _read_env_default()


def set_plugin_context_enabled(value: bool) -> None:
    """Override the runtime toggle.

    Writes through to the active :class:`ConfigStore` when one is
    mounted on the live plugin context, then updates the cached
    :data:`PLUGIN_CONTEXT_ENABLED` flag. When no store is mounted
    (e.g. before server boot, in tests) only the cached flag is
    updated; the next :func:`refresh_plugin_context_enabled` call
    will overwrite the flag with the env-var or store value.

    Production code should treat this as a configuration write: the
    change is durable (when a cross-worker-visible ConfigStore is
    active) and visible to every uvicorn worker on the next read.
    Test code may call it freely.
    """
    global PLUGIN_CONTEXT_ENABLED
    new_value = bool(value)
    PLUGIN_CONTEXT_ENABLED = new_value
    store = _lookup_active_config_store()
    if store is not None:
        store.update({_CONFIG_KEY: new_value})


def refresh_plugin_context_enabled() -> bool:
    """Re-read :data:`PLUGIN_CONTEXT_ENABLED` from the active source.

    Called once during server boot (after the plugin context is
    mounted) so a ConfigStore override that landed between server
    start and now takes effect without a restart. Returns the
    refreshed value.
    """
    global PLUGIN_CONTEXT_ENABLED
    PLUGIN_CONTEXT_ENABLED = is_plugin_context_enabled()
    return PLUGIN_CONTEXT_ENABLED


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


def get_progress_service(*, name: str = "memory") -> Any | None:
    """Return the registered :class:`ProgressService`, or ``None``.

    Default name matches :func:`progress_service_provider` (audit-secondary F14).
    """
    from omniscribe.api.plugin import ProgressService

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(ProgressService, name=name):
        return None
    return ctx.get(ProgressService, name=name)


def get_config_store(*, name: str = "memory") -> Any | None:
    """Return the registered :class:`ConfigStore`, or ``None``.

    Default name matches :func:`config_store_provider` (audit-secondary F14).
    """
    from omniscribe.api.plugin import ConfigStore

    ctx = get_plugin_context()
    if ctx is None or not ctx.has(ConfigStore, name=name):
        return None
    return ctx.get(ConfigStore, name=name)


def get_text_artifact_store(*, name: str = "text") -> Any | None:
    """Return the registered :class:`TextArtifactStore`, or ``None``.

    The three legacy stores register under their canonical domain
    names: ``"text"``, ``"metadata"``, ``"export"``. Pass the right
    name to reach the right store. The default ``"text"`` slot
    matches :func:`text_artifact_store_provider` (audit-secondary
    F14 — domain names, not backend kinds).
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
