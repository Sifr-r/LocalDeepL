"""Plugin context: a Cordis-inspired "everything is a plugin" foundation.

The :mod:`omniscribe.api.plugin` package provides the building blocks for
composable API extensions:

- :class:`PluginContext` — a typed repository of services and event listeners.
- :class:`ServiceDefinition` — a :class:`Protocol` marker for service interfaces.
- :class:`Plugin` — a callable that mounts capabilities into a context.
- :class:`EventMode` — one of four dispatch modes for typed events
  (``emit`` / ``waterfall`` / ``serial`` / ``parallel``).
- :class:`EffectScope` — group reversible effects under a single disposer.

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
from omniscribe.api.plugin.service import Plugin, ServiceDefinition

__all__ = [
    "ContextDisposedError",
    "EffectScope",
    "EventMode",
    "EventModeMismatchError",
    "EventName",
    "Plugin",
    "PluginContext",
    "PluginError",
    "ServiceAlreadyRegisteredError",
    "ServiceDefinition",
    "ServiceNotFoundError",
]
