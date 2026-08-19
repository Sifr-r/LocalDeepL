"""Phase 3c tests — JobHistoryProjection.

Covers:

1. Empty log → empty list.
2. Single submitted event → one record with status ``pending``.
3. submitted + started + completed events → one terminal
   record matching the legacy JobRecord shape exactly.
4. submitted + cancelled events → one error record.
5. submitted + started + completed-with-error → one error record.
6. Newest-first ordering.
7. ``max_jobs`` cap is respected.
8. ``failed_pages`` only present when non-empty.
9. The projection coexists with the audit recorder on the
   same context (the audit recorder fires; the projection
   reads; both see the same events).
"""

from __future__ import annotations

from omniscribe.api.plugin import (
    InMemoryLogStore,
    JobHistoryProjection,
    LogEvent,
    PluginContext,
    in_memory_session_log_provider,
)
from omniscribe.api.plugin.events_catalog import (
    JobCompletedEvent,
    JobStartedEvent,
    JobSubmittedEvent,
)


def _emit(ctx: PluginContext, payload) -> None:
    """Helper: append a JobSubmitted payload to the log via the context."""
    ctx.emit(payload.event_name, **payload.__dict__)


# -- Empty log --------------------------------------------------------------


def test_empty_log_yields_empty_list() -> None:
    log = InMemoryLogStore()
    proj = JobHistoryProjection(log)
    assert proj.list() == []


# -- Single submitted event -------------------------------------------------


def test_single_submitted_event_yields_pending_record() -> None:
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="ocr.job.submitted",
            payload={"job_id": "j1", "filename": "x.pdf"},
        )
    )
    proj = JobHistoryProjection(log)
    records = proj.list()
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "j1"
    assert rec["filename"] == "x.pdf"
    assert rec["status"] == "pending"
    # ``model`` and ``pipeline_mode`` are empty (no started event yet).
    assert rec["model"] == ""
    assert rec["pipeline_mode"] == ""
    # ``duration_s`` is None (job never finished).
    assert rec["duration_s"] is None
    # ``timestamp`` is an ISO-8601 string.
    assert isinstance(rec["timestamp"], str)
    assert "T" in rec["timestamp"]


# -- submitted + started + completed (success) -----------------------------


def test_submitted_started_completed_yields_complete_record() -> None:
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="ocr.job.submitted",
            payload={"job_id": "j1", "filename": "x.pdf"},
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={
                "job_id": "j1",
                "model": "qwen2.5-vl",
                "pipeline_mode": "hybrid",
                "pages": "1-5",
            },
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.completed",
            payload={
                "job_id": "j1",
                "filename": "x.pdf",
                "status": "complete",
                "duration_s": 12.34,
                "text_artifact_id": "ta-1",
            },
        )
    )
    proj = JobHistoryProjection(log)
    records = proj.list()
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "j1"
    assert rec["filename"] == "x.pdf"
    assert rec["status"] == "complete"
    assert rec["model"] == "qwen2.5-vl"
    assert rec["pipeline_mode"] == "hybrid"
    assert rec["pages"] == "1-5"
    assert rec["duration_s"] == 12.34
    assert rec["text_artifact_id"] == "ta-1"
    # ``error`` is absent (success path).
    assert "error" not in rec


# -- submitted + cancelled -------------------------------------------------


def test_cancelled_event_yields_error_record() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="ocr.job.submitted", payload={"job_id": "j1"}))
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={
                "job_id": "j1",
                "model": "m",
                "pipeline_mode": "hybrid",
            },
        )
    )
    log.append(LogEvent(kind="ocr.job.cancelled", payload={"job_id": "j1"}))
    proj = JobHistoryProjection(log)
    rec = proj.list()[0]
    assert rec["status"] == "error"
    assert rec["error"] == "cancelled by client"


# -- completed with error status --------------------------------------------


def test_completed_with_error_status_yields_error_record() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="ocr.job.submitted", payload={"job_id": "j1"}))
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={"job_id": "j1", "model": "m", "pipeline_mode": "hybrid"},
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.completed",
            payload={
                "job_id": "j1",
                "status": "error",
                "duration_s": 5.0,
                "error": "OCR pipeline raised",
                "failed_pages": [3, 7, 9],
            },
        )
    )
    proj = JobHistoryProjection(log)
    rec = proj.list()[0]
    assert rec["status"] == "error"
    assert rec["error"] == "OCR pipeline raised"
    assert rec["failed_pages"] == [3, 7, 9]


# -- failed_pages only present when non-empty ------------------------------


def test_failed_pages_omitted_when_empty() -> None:
    log = InMemoryLogStore()
    log.append(LogEvent(kind="ocr.job.submitted", payload={"job_id": "j1"}))
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={"job_id": "j1", "model": "m", "pipeline_mode": "hybrid"},
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.completed",
            payload={"job_id": "j1", "status": "complete", "duration_s": 1.0},
        )
    )
    proj = JobHistoryProjection(log)
    rec = proj.list()[0]
    assert "failed_pages" not in rec


# -- Newest-first ordering -------------------------------------------------


def test_newest_first_ordering() -> None:
    log = InMemoryLogStore()
    # Submit jobs in order: j1, j2, j3. The list() output
    # should be j3, j2, j1.
    for jid in ("j1", "j2", "j3"):
        log.append(
            LogEvent(
                kind="ocr.job.submitted",
                payload={"job_id": jid, "filename": f"{jid}.pdf"},
            )
        )
    proj = JobHistoryProjection(log)
    records = proj.list()
    assert [r["id"] for r in records] == ["j3", "j2", "j1"]


# -- max_jobs cap ----------------------------------------------------------


def test_max_jobs_cap_respected() -> None:
    log = InMemoryLogStore()
    for i in range(5):
        log.append(
            LogEvent(
                kind="ocr.job.submitted",
                payload={"job_id": f"j{i}", "filename": f"j{i}.pdf"},
            )
        )
    proj = JobHistoryProjection(log, max_jobs=2)
    records = proj.list()
    assert len(records) == 2
    # Newest two.
    assert {r["id"] for r in records} == {"j4", "j3"}


# -- Coexistence with the audit recorder ----------------------------------


def test_projection_and_audit_recorder_see_the_same_events() -> None:
    """Mount the audit recorder (Phase 2) and the session log
    (Phase 3) on the same context. Emit one JobSubmitted
    payload; the log gets the event (auto-append) and the
    recorder also sees it. The projection then folds the
    log into a JobRecord."""
    ctx = PluginContext("test")
    captured_audit: list[str] = []

    # A minimal recorder: log every emit.
    def _log_listener(**payload):
        captured_audit.append(payload.get("event_name", ""))

    ctx.on("ocr.job.submitted", _log_listener, mode="emit")
    ctx.on("ocr.job.started", _log_listener, mode="emit")
    ctx.on("ocr.job.completed", _log_listener, mode="emit")
    log = InMemoryLogStore()
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))

    # Emit one full lifecycle. The dataclass already carries
    # the event_name field; we pass ``__dict__`` directly to
    # ``ctx.emit``.
    ctx.emit(
        "ocr.job.submitted", **JobSubmittedEvent(job_id="j1", filename="x.pdf").__dict__
    )
    ctx.emit(
        "ocr.job.started",
        **JobStartedEvent(job_id="j1", model="m", pipeline_mode="hybrid").__dict__,
    )
    ctx.emit(
        "ocr.job.completed",
        **JobCompletedEvent(job_id="j1", status="complete", duration_s=2.0).__dict__,
    )

    # Audit recorder saw all three.
    assert captured_audit == [
        "ocr.job.submitted",
        "ocr.job.started",
        "ocr.job.completed",
    ]
    # Projection sees the same three.
    proj = JobHistoryProjection(log)
    rec = proj.list()[0]
    assert rec["id"] == "j1"
    assert rec["status"] == "complete"
    assert rec["duration_s"] == 2.0


# -- Match legacy JobHistory output shape ---------------------------------


def test_projection_output_matches_legacy_job_history_shape() -> None:
    """The output of ``projection.list()`` and
    ``JobHistory.list()`` should be field-compatible so a
    consumer can swap one for the other without code
    changes.

    This is a hand-computed example that the legacy
    JobHistory stores; the projection must produce the same
    record shape from the same event stream.
    """
    from datetime import UTC, datetime

    from omniscribe.api.services.jobs import JobHistory

    # Build a hand-crafted JobHistory with one record.
    history = JobHistory()
    fixed_time = datetime(2026, 8, 17, 10, 0, 0, tzinfo=UTC)
    history.record(
        job_id="j1",
        filename="x.pdf",
        model="m",
        pipeline_mode="hybrid",
        pages="1-5",
        duration_s=12.34,
        status="complete",
        failed_pages=(),
    )
    legacy = history.list()

    # Build the same record via the projection.
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="ocr.job.submitted", payload={"job_id": "j1", "filename": "x.pdf"}
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={
                "job_id": "j1",
                "model": "m",
                "pipeline_mode": "hybrid",
                "pages": "1-5",
            },
        )
    )
    log.append(
        LogEvent(
            kind="ocr.job.completed",
            payload={
                "job_id": "j1",
                "status": "complete",
                "duration_s": 12.34,
            },
        )
    )
    proj = JobHistoryProjection(log, now_fn=lambda: fixed_time)
    projection = proj.list()

    # Compare field sets (ignoring the timestamp which is
    # an opaque wall-clock string).
    assert projection[0].keys() == legacy[0].keys(), (
        f"field set differs: projection={set(projection[0].keys())}, "
        f"legacy={set(legacy[0].keys())}"
    )
    for key in projection[0]:
        if key == "timestamp":
            continue
        assert projection[0][key] == legacy[0][key], (
            f"field {key!r} differs: projection={projection[0][key]!r}, "
            f"legacy={legacy[0][key]!r}"
        )


# -- Audit-secondary F15: fold + sort cache ---------------------------------


def test_list_caches_fold_until_log_changes(monkeypatch) -> None:
    """Repeated ``list()`` calls reuse the cached fold.

    Audit-secondary F15: the fold + position-stamp + sort is
    the expensive part (O(N log N)). The cache is keyed on
    ``len(self._log)`` so any ``log.append`` invalidates it.
    Three calls within the same log version must fold only
    once; one call after a new event must fold again.
    """
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="ocr.job.submitted",
            payload={"job_id": "j1", "filename": "x.pdf"},
        )
    )
    proj = JobHistoryProjection(log)

    fold_calls = 0
    original_fold_all = proj._fold_all

    def counting_fold_all():
        nonlocal fold_calls
        fold_calls += 1
        return original_fold_all()

    monkeypatch.setattr(proj, "_fold_all", counting_fold_all)

    # Three calls within the same log version: one fold.
    r1 = proj.list()
    r2 = proj.list()
    r3 = proj.list()
    assert fold_calls == 1
    assert r1 == r2 == r3

    # Append a new event: cache invalidated.
    log.append(
        LogEvent(
            kind="ocr.job.started",
            payload={"job_id": "j1", "model": "m"},
        )
    )
    r4 = proj.list()
    assert fold_calls == 2
    # The new event updates the same record.
    assert r4[0]["model"] == "m"

    # Another repeat call within the same (new) log version: cache hit.
    r5 = proj.list()
    assert fold_calls == 2
    assert r4 == r5


def test_list_cache_invalidation_fires_on_unrelated_event() -> None:
    """An unrelated event also invalidates the cache.

    The cache key is ``len(self._log)``, not the event kind.
    Any append (e.g. a new ``artifact.created`` event) bumps
    the log length and forces a re-fold. This is the
    conservative choice — a finer-grained invalidation would
    require an event-kind index in the log itself.
    """
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="ocr.job.submitted",
            payload={"job_id": "j1", "filename": "x.pdf"},
        )
    )
    proj = JobHistoryProjection(log)

    assert len(proj.list()) == 1
    # An unrelated event still invalidates.
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={"artifact_id": "a" * 32, "kind": "text"},
        )
    )
    # The projection itself does not see the artifact event, but
    # the cache key changed so the re-fold runs. Output is
    # unchanged.
    assert len(proj.list()) == 1
    assert proj.list()[0]["id"] == "j1"
