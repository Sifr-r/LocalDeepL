"""Plugin context: a Cordis-inspired "everything is a plugin" foundation.

The :mod:`omniscribe.api.plugin` package provides the building blocks for
composable API extensions:

- :class:`PluginContext` — a typed repository of services and event listeners.
- :class:`ServiceDefinition` — a :class:`Protocol` marker for service interfaces.
- :class:`Plugin` — a callable that mounts capabilities into a context.
- :class:`EventMode` — one of four dispatch modes for typed events
  (``emit`` / ``waterfall`` / ``serial`` / ``parallel``).
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
from omniscribe.api.plugin.errors import (
    ContextDisposedError,
    EventModeMismatchError,
    PluginError,
    ServiceAlreadyRegisteredError,
    ServiceNotFoundError,
)
from omniscribe.api.plugin.events import EventMode, EventName
from omniscribe.api.plugin.providers import (
    config_store_provider,
    in_memory_session_log_provider,
    local_job_queue_provider,
    progress_service_provider,
    text_artifact_store_provider,
)
from omniscribe.api.plugin.seams import (
    ConfigStore,
    JobQueue,
    ProgressChannel,
    ProgressService,
    SessionLog,
    TextArtifactStore,
)
from omniscribe.api.plugin.service import Plugin, ServiceDefinition
from omniscribe.api.plugin.session_log import (
    InMemoryLogStore,
    LogEvent,
    SessionLogQuery,
)

__all__ = [
    "ConfigStore",
    "ContextDisposedError",
    "EventMode",
    "EventModeMismatchError",
    "EventName",
    "InMemoryLogStore",
    "JobQueue",
    "LogEvent",
    "Plugin",
    "PluginContext",
    "PluginError",
    "ProgressChannel",
    "ProgressService",
    "ServiceAlreadyRegisteredError",
    "ServiceDefinition",
    "ServiceNotFoundError",
    "SessionLog",
    "SessionLogQuery",
    "TextArtifactStore",
    "config_store_provider",
    "in_memory_session_log_provider",
    "local_job_queue_provider",
    "progress_service_provider",
    "text_artifact_store_provider",
]
