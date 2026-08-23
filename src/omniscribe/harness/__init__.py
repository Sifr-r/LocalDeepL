"""Cordis-style plugin harness: Context, Service, Event, EffectScope, Loader."""

from __future__ import annotations

from omniscribe.harness.context import Context
from omniscribe.harness.effects import EffectRef, EffectScope, effect_scope
from omniscribe.harness.errors import (
    ContextDisposedError,
    HarnessError,
    PluginLoadError,
    ServiceNotFoundError,
)
from omniscribe.harness.events import AgentEvent, CapabilityEvent, Event, SessionEvent
from omniscribe.harness.plugin import Plugin
from omniscribe.harness.service import Service, service_protocol

__all__ = [
    "AgentEvent",
    "CapabilityEvent",
    "Context",
    "ContextDisposedError",
    "EffectRef",
    "EffectScope",
    "Event",
    "HarnessError",
    "Plugin",
    "PluginLoadError",
    "Service",
    "ServiceNotFoundError",
    "SessionEvent",
    "effect_scope",
    "service_protocol",
]
