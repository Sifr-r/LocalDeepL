"""Phase 3a tests — session log foundation.

Covers:

1. ``LogEvent`` envelope shape (event_id, timestamp, kind, payload).
2. ``with_payload`` helper for ergonomic construction.
3. ``InMemoryLogStore.append`` returns the event_id and preserves order.
4. ``InMemoryLogStore.get`` returns the event by id, or None if unknown.
5. ``InMemoryLogStore.list`` returns events in insertion order.
6. ``SessionLogQuery`` filters by kind, kinds set, correlation_id, since, until, limit.
7. The runtime_checkable ``SessionLog`` Protocol accepts the InMemoryLogStore.
8. ``in_memory_session_log_provider`` registers under the default name.
9. The provider can be unmounted via the returned disposer.
10. The session log coexists with the JobQueue provider in the same context.
"""

from __future__ import annotations

import time

import pytest

from omniscribe.api.plugin import (
    InMemoryLogStore,
    JobQueue,
    LogEvent,
    PluginContext,
    SessionLog,
    SessionLogQuery,
    in_memory_session_log_provider,
    local_job_queue_provider,
)
from omniscribe.api.services.ocr_jobs import OCRJobQueue

# -- LogEvent envelope -------------------------------------------------------


def test_log_event_mints_event_id_and_timestamp() -> None:
    event = LogEvent(kind="job.submitted")
    # 32 hex chars from secrets.token_hex(16)
    assert len(event.event_id) == 32
    assert all(c in "0123456789abcdef" for c in event.event_id)
    # monotonic timestamp is a float
    assert isinstance(event.timestamp, float)
    assert event.timestamp > 0


def test_log_event_with_payload_merges_fields() -> None:
    base = LogEvent(kind="job.submitted", payload={"job_id": "j1"})
    merged = base.with_payload(filename="x.pdf", model="qwen")
    assert merged.kind == "job.submitted"
    assert merged.event_id == base.event_id  # identity preserved
    assert merged.timestamp == base.timestamp
    assert merged.payload == {"job_id": "j1", "filename": "x.pdf", "model": "qwen"}
    # The base is unchanged (frozen dataclass).
    assert base.payload == {"job_id": "j1"}


def test_log_event_is_frozen() -> None:
    event = LogEvent(kind="job.submitted", payload={"x": 1})
    with pytest.raises((AttributeError, Exception)):
        event.kind = "tampered"  # type: ignore[misc]


# -- InMemoryLogStore.append / get -------------------------------------------


def test_append_returns_event_id_and_preserves_order() -> None:
    log = InMemoryLogStore()
    a = log.append(LogEvent(kind="job.submitted", payload={"job_id": "a"}))
    b = log.append(LogEvent(kind="job.completed", payload={"job_id": "a"}))
    c = log.append(LogEvent(kind="job.submitted", payload={"job_id": "b"}))
    assert a != b != c
    assert len(log) == 3
    events = log.list()
    assert [e.kind for e in events] == [
        "job.submitted",
        "job.completed",
        "job.submitted",
    ]


def test_get_returns_event_by_id() -> None:
    log = InMemoryLogStore()
    event_id = log.append(LogEvent(kind="job.submitted", payload={"job_id": "x"}))
    event = log.get(event_id)
    assert event is not None
    assert event.event_id == event_id
    assert event.payload == {"job_id": "x"}


def test_get_returns_none_for_unknown_id() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="job.submitted"))
    assert log.get("does-not-exist") is None


# -- InMemoryLogStore.list --------------------------------------------------


def test_list_with_no_query_returns_all_events() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="a"))
    log.append(LogEvent(kind="b"))
    log.append(LogEvent(kind="c"))
    assert [e.kind for e in log.list()] == ["a", "b", "c"]


def test_list_filters_by_kind() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="job.submitted"))
    log.append(LogEvent(kind="artifact.created"))
    log.append(LogEvent(kind="job.completed"))
    events = log.list(SessionLogQuery(kind="job.submitted"))
    assert [e.kind for e in events] == ["job.submitted"]


def test_list_filters_by_kinds_set() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="job.submitted"))
    log.append(LogEvent(kind="artifact.created"))
    log.append(LogEvent(kind="job.completed"))
    log.append(LogEvent(kind="translation.requested"))
    events = log.list(
        SessionLogQuery(kinds=frozenset({"job.submitted", "job.completed"}))
    )
    assert sorted(e.kind for e in events) == ["job.completed", "job.submitted"]


def test_list_filters_by_correlation_id() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="a", correlation_id="c1"))
    log.append(LogEvent(kind="b", correlation_id="c2"))
    log.append(LogEvent(kind="c", correlation_id="c1"))
    events = log.list(SessionLogQuery(correlation_id="c1"))
    assert [e.kind for e in events] == ["a", "c"]


def test_list_filters_by_since_and_until() -> None:
    log = InMemoryLogStore()
    # Inject events with explicit monotonic timestamps.
    base = time.monotonic()
    log.append(LogEvent(kind="a", timestamp=base + 0.0))
    log.append(LogEvent(kind="b", timestamp=base + 1.0))
    log.append(LogEvent(kind="c", timestamp=base + 2.0))
    log.append(LogEvent(kind="d", timestamp=base + 3.0))
    # since is inclusive
    events = log.list(SessionLogQuery(since=base + 1.0))
    assert [e.kind for e in events] == ["b", "c", "d"]
    # until is inclusive; combine since + until
    events = log.list(SessionLogQuery(since=base + 1.0, until=base + 2.0))
    assert [e.kind for e in events] == ["b", "c"]


def test_list_respects_limit() -> None:
    log = InMemoryLogStore()
    for i in range(10):
        log.append(LogEvent(kind=str(i)))
    assert len(log.list(SessionLogQuery(limit=3))) == 3
    assert len(log.list(SessionLogQuery(limit=100))) == 10


# -- Protocol conformance --------------------------------------------------


def test_in_memory_log_store_satisfies_session_log_protocol() -> None:
    log = InMemoryLogStore()
    assert isinstance(log, SessionLog)


# -- in_memory_session_log_provider -----------------------------------------


def test_provider_registers_a_fresh_log_by_default() -> None:
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider())
    log = ctx.get(SessionLog, name="memory")
    assert isinstance(log, InMemoryLogStore)
    assert len(log) == 0


def test_provider_can_register_an_existing_log() -> None:
    """The migration shim will pass a pre-built log to share state
    with code that already holds a reference."""
    ctx = PluginContext("test")
    shared = InMemoryLogStore()
    shared.append(LogEvent(kind="preexisting"))
    ctx.mount(in_memory_session_log_provider(log=shared, name="memory"))
    log = ctx.get(SessionLog, name="memory")
    assert log is shared
    assert len(log) == 1


def test_provider_default_name_is_memory() -> None:
    """A future ``"sqlite"`` provider should be able to coexist."""
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider())
    names = ctx.service_names(SessionLog)
    assert names == ["memory"]


def test_provider_can_be_unmounted_via_the_returned_disposer() -> None:
    ctx = PluginContext("test")
    unmount = ctx.mount(in_memory_session_log_provider())
    assert ctx.has(SessionLog, name="memory") is True
    unmount()
    assert ctx.has(SessionLog, name="memory") is False


# -- Coexistence with Phase 1 seam ------------------------------------------


def test_session_log_and_job_queue_seams_coexist() -> None:
    """The Phase 1 JobQueue provider and the Phase 3 SessionLog provider
    can be mounted into the same context without interfering."""
    ctx = PluginContext("test")
    queue = OCRJobQueue()
    log = InMemoryLogStore()
    ctx.mount(local_job_queue_provider(queue=queue, name="local"))
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    assert ctx.get(JobQueue, name="local") is queue
    assert ctx.get(SessionLog, name="memory") is log
    # Independent operation: an event in the log does not affect the queue.
    log.append(LogEvent(kind="job.submitted", payload={"job_id": "x"}))
    assert len(log) == 1
    assert queue.running is False
