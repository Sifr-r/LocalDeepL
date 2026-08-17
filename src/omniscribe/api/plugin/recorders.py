"""Built-in event recorders that ship with the plugin package.

A recorder is a :class:`Plugin` that subscribes to one or more events
and writes them somewhere (logs, session log store, etc.). The
``audit_log_recorder`` is the default recorder; it logs every event at
INFO level. Future recorders can persist events to a database or push
them to a metrics backend.

The recorders never decide policy — they observe. A future "policy
plugin" can be added that intercepts an event (via waterfall mode) to
block or modify behavior.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, is_dataclass

from omniscribe.api.plugin.context import PluginContext
from omniscribe.api.plugin.events_catalog import (
    ArtifactCreatedEvent,
    JobCancelledEvent,
    JobCompletedEvent,
    JobSubmittedEvent,
    ProviderSwitchedEvent,
    RequestReceivedEvent,
    TranslationRequestedEvent,
)

logger = logging.getLogger(__name__)


def _payload_to_dict(payload: object) -> dict[str, object]:
    """Convert a dataclass payload to a dict for logging.

    Non-dataclass payloads (e.g. raw dicts) are returned unchanged.
    """
    if is_dataclass(payload) and not isinstance(payload, type):
        return asdict(payload)
    if isinstance(payload, dict):
        return payload
    return {"value": payload}


def audit_log_recorder(
    *, level: int = logging.INFO
) -> Callable[[PluginContext], Callable[[], None]]:
    """Return a :class:`Plugin` that logs every audit event.

    Parameters
    ----------
    level:
        The :mod:`logging` level to use when emitting the audit line.
        Defaults to ``logging.INFO``; production deployments may prefer
        ``logging.DEBUG`` to keep audit chatter out of operational logs
        when a separate audit handler is wired up.

    The plugin subscribes to every event in
    :data:`omniscribe.api.plugin.events_catalog.ALL_EVENT_TYPES` using
    the ``emit`` dispatch mode. The plugin returns a single disposer
    that removes every listener on unmount.
    """

    def _plugin(ctx: PluginContext) -> Callable[[], None]:
        disposers: list[Callable[[], None]] = []

        def on_event(**payload: object) -> None:
            event_name = payload.get("event_name", "<unknown>")
            logger.log(level, "audit_event", extra={"event": _payload_to_dict(payload)})
            # Also emit a one-line human-readable summary on its own
            # so log-grep finds the marker without a structured-log
            # backend.
            logger.info("event=%s data=%s", event_name, _payload_to_dict(payload))

        for event_cls in (
            JobSubmittedEvent,
            JobCompletedEvent,
            JobCancelledEvent,
            TranslationRequestedEvent,
            ArtifactCreatedEvent,
            ProviderSwitchedEvent,
            RequestReceivedEvent,
        ):
            disposers.append(ctx.on(event_cls().event_name, on_event, mode="emit"))

        def dispose() -> None:
            for d in disposers:
                d()

        return dispose

    return _plugin


__all__ = ["audit_log_recorder"]
