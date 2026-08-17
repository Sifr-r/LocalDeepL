"""Plugin context: a Cordis-inspired "everything is a plugin" foundation.

The :mod:`omniscribe.api.plugin` package provides the building blocks for
composable API extensions:

- :class:`PluginContext` — a typed repository of services and event listeners.
- :class:`ServiceDefinition` — a :class:`Protocol` marker for service interfaces.
- :class:`Plugin` — a callable that mounts capabilities into a context.
- :class:`EventMode` — one of four dispatch modes for typed events
  (``emit`` / ``waterfall`` / ``serial`` / ``parallel``).
- :class:`EffectScope` — group reversible effects under a single disposer.
- :mod:`omniscribe.api.plugin.seams` — Service Definitions for swappable capabilities.
- :mod:`omniscribe.api.plugin.providers` — concrete Service Providers.

Existing OmniScribe code continues to work unchanged; the plugin context is
additive infrastructure. Subsequent refactor phases convert the legacy
singleton-backed services (``StateBackend``, ``OCRJobQueue``,
``ProviderManager``, etc.) into capability seams that register themselves
into the context instead of being imported by name.
"""

from __future__ import annotations

from omniscribe.api.plugin.context import PluginContext
from omniscribe.api.plugin.effects import EffectScope
from omniscribe.api.plugin.errors import (
    ContextDisposedError,
    EventModeMismatchError,
    PluginError,
    ServiceAlreadyRegisteredError,
    ServiceNotFoundError,
)
from omniscribe.api.plugin.events import EventMode, EventName
from omniscribe.api.plugin.profile import Bundle, Patch, Profile
from omniscribe.api.plugin.projections import (
    ArtifactStoreProjection,
    JobHistoryProjection,
)
from omniscribe.api.plugin.providers import (
    in_memory_session_log_provider,
    local_job_queue_provider,
)
from omniscribe.api.plugin.seams import JobQueue, SessionLog
from omniscribe.api.plugin.service import Plugin, ServiceDefinition
from omniscribe.api.plugin.session_log import (
    InMemoryLogStore,
    LogEvent,
    SessionLogQuery,
)

__all__ = [
    "ArtifactStoreProjection",
    "Bundle",
    "ContextDisposedError",
    "EffectScope",
    "EventMode",
    "EventModeMismatchError",
    "EventName",
    "InMemoryLogStore",
    "JobHistoryProjection",
    "JobQueue",
    "LogEvent",
    "Patch",
    "Plugin",
    "PluginContext",
    "PluginError",
    "Profile",
    "ServiceAlreadyRegisteredError",
    "ServiceDefinition",
    "ServiceNotFoundError",
    "SessionLog",
    "SessionLogQuery",
    "in_memory_session_log_provider",
    "local_job_queue_provider",
]
