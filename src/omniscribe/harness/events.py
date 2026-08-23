"""Typed event bases for the harness event bus.

Three domains mirror Cordis: ``SessionEvent`` (durable facts), ``AgentEvent``
(live progress frames), and ``CapabilityEvent`` (seam policy/adapter events).
Listeners filter by exact event type; there are no string names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """Base class for every event the bus dispatches."""


@dataclass(frozen=True)
class SessionEvent(Event):
    """Durable fact appended to the session log."""


@dataclass(frozen=True)
class AgentEvent(Event):
    """Live progress frame."""


@dataclass(frozen=True)
class CapabilityEvent(Event):
    """Seam policy / adapter event."""
