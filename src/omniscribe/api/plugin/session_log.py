"""Unified session log — the single source of truth for audit + state.

The :class:`SessionLog` is an append-only event stream that
replaces the parallel state stores (:class:`JobHistory`,
:class:`TextArtifactStore`, etc.) as the source of truth for
"what happened in this server". Existing stores become
**projections** over the log: they read events, fold them into
the shape the caller wants, and cache the result for cheap
re-reads. The projection is invalidated when new events are
appended that affect the cache.

This is the dsh "session log as source of truth" pattern
applied to OmniScribe. See ``docs/architecture.md`` in dsh for
the original framing.

Phase 3a delivers the foundation only:

- :class:`LogEvent` — the envelope (event_id, timestamp, kind,
  payload).
- :class:`SessionLog` — the Service Definition (Protocol).
- :class:`InMemoryLogStore` — a concrete provider for the
  migration window (drops everything on restart, like the rest
  of the in-memory state today).
- :class:`SessionLogQuery` — typed filter + page params.

Phase 3b wires :meth:`append` into the plugin context so every
:func:`PluginContext.emit` becomes a log append. Phase 3c/3d
migrate :class:`JobHistory` and :class:`TextArtifactStore` into
projections over the log.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


def _new_event_id() -> str:
    """Return a fresh opaque event id.

    Uses :mod:`secrets` (not :mod:`uuid`) so the id is
    unguessable — a log entry that leaks through a side channel
    should not be enumerable by a third party. 16 bytes → 32
    hex chars, plenty of entropy for the per-process lifetime
    of a log.
    """
    return secrets.token_hex(16)


def _new_correlation_id() -> str:
    """Return a fresh correlation id (groups log events that share a cause)."""
    return secrets.token_hex(8)


@dataclass(frozen=True)
class LogEvent:
    """One entry in the session log.

    The :attr:`kind` is a dotted string (``"job.submitted"``,
    ``"job.completed"``, ``"artifact.created"``, etc.); the
    :attr:`payload` is a dict whose shape is defined by the
    kind. Consumers branch on ``kind`` to interpret the
    payload.

    The envelope fields (:attr:`event_id`, :attr:`timestamp`,
    :attr:`correlation_id`) are added by :meth:`SessionLog.append`
    and must not be set by callers.
    """

    event_id: str = field(default_factory=_new_event_id)
    timestamp: float = field(default_factory=time.monotonic)
    correlation_id: str = field(default_factory=_new_correlation_id)
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def with_payload(self, **payload: Any) -> LogEvent:
        """Return a copy of this event with the given payload fields merged in.

        Convenience for the common pattern::

            ctx.session_log.append(
                LogEvent(kind="job.submitted", payload={}).with_payload(
                    job_id=job_id, filename=filename,
                )
            )
        """
        merged = dict(self.payload)
        merged.update(payload)
        return LogEvent(
            event_id=self.event_id,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            kind=self.kind,
            payload=merged,
        )


@dataclass(frozen=True)
class SessionLogQuery:
    """Typed filter + page parameters for :meth:`SessionLog.list`.

    All fields are optional. ``kind`` filters by exact match;
    ``kinds`` filters by set membership (OR); ``since`` is an
    inclusive lower bound on the event timestamp (monotonic
    seconds); ``limit`` caps the result count.
    """

    kind: str | None = None
    kinds: frozenset[str] | None = None
    correlation_id: str | None = None
    since: float | None = None
    until: float | None = None
    limit: int | None = None


@runtime_checkable
class SessionLog(Protocol):
    """Append-only event log: the source of truth for server state.

    Implementations are expected to preserve insertion order
    and to make :meth:`append` atomic with respect to
    concurrent :meth:`list` / :meth:`get` calls. The log is
    not required to be durable across restarts unless the
    concrete provider advertises that capability (e.g. a
    SQLite-backed store would; the in-memory provider does
    not).
    """

    def append(self, event: LogEvent) -> str:
        """Persist ``event`` and return its ``event_id``.

        The returned id equals ``event.event_id`` if the caller
        supplied one; otherwise the log mints a fresh id. Calling
        code can ignore the return value when it doesn't need
        the id back.
        """
        ...

    def get(self, event_id: str) -> LogEvent | None:
        """Return the event with the given id, or ``None`` if unknown."""
        ...

    def list(self, query: SessionLogQuery | None = None) -> list[LogEvent]:
        """Return events matching ``query``, in insertion order.

        An empty / ``None`` query returns every event. The
        returned list is a snapshot; concurrent :meth:`append`
        calls do not mutate it.
        """
        ...

    def __len__(self) -> int:
        """Number of events in the log."""
        ...


# ---------------------------------------------------------------------------
# Concrete provider
# ---------------------------------------------------------------------------


class InMemoryLogStore:
    """Process-lifetime :class:`SessionLog` implementation.

    State is held in a plain list protected by a :class:`threading.Lock`
    so concurrent :meth:`append` and :meth:`list` calls are atomic
    with respect to each other. A :class:`uuid.UUID` index maps
    :attr:`LogEvent.event_id` to the list position for O(1)
    :meth:`get` calls. The lock is held only across the list /
    dict mutation, never across a callback, so a slow reader
    cannot block a writer.

    This is the migration-window provider. A SQLite-backed
    :class:`SessionLog` (and optionally a JSONL append-only
    log) will join it as opt-in providers behind the same
    :class:`SessionLog` Protocol — a Phase 5 follow-up.
    """

    def __init__(self) -> None:
        import threading

        self._events: list[LogEvent] = []
        self._by_id: dict[str, int] = {}
        self._lock = threading.Lock()

    def append(self, event: LogEvent) -> str:
        with self._lock:
            self._by_id[event.event_id] = len(self._events)
            self._events.append(event)
        return event.event_id

    def get(self, event_id: str) -> LogEvent | None:
        with self._lock:
            idx = self._by_id.get(event_id)
            if idx is None:
                return None
            return self._events[idx]

    def list(self, query: SessionLogQuery | None = None) -> list[LogEvent]:
        with self._lock:
            snapshot = list(self._events)
        if query is None:
            return snapshot
        out: list[LogEvent] = []
        for ev in snapshot:
            if not self._matches(ev, query):
                continue
            out.append(ev)
            if query.limit is not None and len(out) >= query.limit:
                break
        return out

    @staticmethod
    def _matches(event: LogEvent, query: SessionLogQuery) -> bool:
        """Return True iff ``event`` satisfies every set field of ``query``."""
        return (
            (query.kind is None or event.kind == query.kind)
            and (query.kinds is None or event.kind in query.kinds)
            and (
                query.correlation_id is None
                or event.correlation_id == query.correlation_id
            )
            and (query.since is None or event.timestamp >= query.since)
            and (query.until is None or event.timestamp <= query.until)
        )

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


def in_memory_session_log_provider(
    log: InMemoryLogStore | None = None,
    *,
    name: str = "memory",
) -> callable:
    """Return a :class:`Plugin` that registers an in-memory :class:`SessionLog`.

    Parameters
    ----------
    log:
        Pre-built log instance to register. When ``None``
        (default), a fresh :class:`InMemoryLogStore` is
        constructed. Pass an existing instance to share state
        with code that already holds a reference (e.g. a
        migration shim that wraps the legacy
        :class:`JobHistory`).
    name:
        Provider name. Defaults to ``"memory"`` so a future
        ``"sqlite"`` provider can register alongside.
    """
    impl = log if log is not None else InMemoryLogStore()

    def _plugin(ctx) -> callable:
        disposer = ctx.register(SessionLog, impl, name=name)
        return disposer

    return _plugin


__all__ = [
    "InMemoryLogStore",
    "LogEvent",
    "SessionLog",
    "SessionLogQuery",
    "in_memory_session_log_provider",
]
