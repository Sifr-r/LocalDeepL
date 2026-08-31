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
from omniscribe.harness.loader import Loader, PluginRow
from omniscribe.harness.plugin import Plugin
from omniscribe.harness.service import Service

__all__ = [
    "AgentEvent",
    "CapabilityEvent",
    "Context",
    "ContextDisposedError",
    "EffectRef",
    "EffectScope",
    "Event",
    "HarnessError",
    "Loader",
    "Plugin",
    "PluginLoadError",
    "PluginRow",
    "Service",
    "ServiceNotFoundError",
    "SessionEvent",
    "effect_scope",
]
