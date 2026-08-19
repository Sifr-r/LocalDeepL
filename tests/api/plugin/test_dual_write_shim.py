"""Phase 3c tests — dual-write shim and OCR-route emit helpers.

Covers the new emit helpers in :mod:`omniscribe.api.routers.ocr`:

1. :func:`_emit_job_submitted` writes a JobSubmittedEvent to the log
   (via the auto-append fan-out) and to any mounted recorders.
2. :func:`_emit_job_started` writes a JobStartedEvent with the
   per-request config (model, pipeline_mode, pages).
3. :func:`_record_job` writes BOTH the legacy ``JobHistory`` record
   (using ``job_id`` as the legacy id) AND a JobCompletedEvent to the
   log (using ``log_job_id`` as the canonical log id). The two ids
   may differ during the migration window — the sync path uses the
   UUID-hex for the log and the artifact_id for the legacy deque.
4. The dual-write shim's emit propagates ``text_artifact_id`` and
   ``error`` into the JobCompletedEvent payload so the projection can
   fold a complete record.
5. The :class:`JobHistoryProjection` correctly folds a full
   submitted → started → completed lifecycle into a JobRecord that
   matches the legacy JobHistory output (a re-verification at the
   router-helper level).
"""

from __future__ import annotations

import pytest

from omniscribe.api.plugin import (
    InMemoryLogStore,
    JobHistoryProjection,
    PluginContext,
    in_memory_session_log_provider,
)
from omniscribe.api.services.jobs import JobHistory

# -- _emit_job_submitted ----------------------------------------------------


def test_emit_job_submitted_appends_to_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_emit_job_submitted`` writes a JobSubmittedEvent to the log."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    ocr._emit_job_submitted("j-1", "doc.pdf")

    events = log.list()
    assert len(events) == 1
    assert events[0].kind == "ocr.job.submitted"
    assert events[0].payload == {
        "event_name": "ocr.job.submitted",
        "job_id": "j-1",
        "filename": "doc.pdf",
        "submitted_at": events[0].payload["submitted_at"],
        "request_channel_id": None,
    }


def test_emit_job_submitted_noop_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_emit_job_submitted`` is a no-op when the plugin context is unset."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr

    runtime.set_plugin_context(None)

    # Should not raise. (We can't easily assert "nothing happened"
    # without a log, but the function returns None and swallows its
    # own errors — calling it twice in a row should also be safe.)
    ocr._emit_job_submitted("j-1", "doc.pdf")
    ocr._emit_job_submitted("j-1", "doc.pdf")


# -- _emit_job_started ------------------------------------------------------


def test_emit_job_started_appends_to_log() -> None:
    """``_emit_job_started`` writes a JobStartedEvent with model/mode/pages."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    ocr._emit_job_started(
        "j-1", model="qwen2.5-vl", pipeline_mode="hybrid", pages="1-3"
    )

    events = log.list()
    assert len(events) == 1
    assert events[0].kind == "ocr.job.started"
    assert events[0].payload["job_id"] == "j-1"
    assert events[0].payload["model"] == "qwen2.5-vl"
    assert events[0].payload["pipeline_mode"] == "hybrid"
    assert events[0].payload["pages"] == "1-3"


def test_emit_job_started_with_no_pages() -> None:
    """``pages`` is optional; the event is still emitted with ``pages=None``."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    ocr._emit_job_started("j-1", model="m", pipeline_mode="hybrid", pages=None)
    events = log.list()
    assert events[0].payload["pages"] is None


# -- _record_job dual-write shim -------------------------------------------


def test_record_job_dual_writes_to_legacy_and_log() -> None:
    """``_record_job`` writes the legacy JobRecord AND emits a log event.

    The legacy id (``job_id``) and the canonical log id
    (``log_job_id``) may differ — the sync path uses the artifact id
    for the legacy record and the UUID-hex for the log. The test pins
    both writes to prove the shim honours the contract.
    """
    from omniscribe.api.plugin import runtime

    # Fresh state: a private JobHistory attached to state.job_history
    # for the duration of the test (the real ``state`` module is
    # process-wide; we replace its ``job_history`` attribute and
    # restore it after).
    from omniscribe.api.routers import ocr, state

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    original_history = state.job_history
    state.job_history = JobHistory()
    try:
        ocr._record_job(
            job_id="legacy-id",
            filename="doc.pdf",
            model="qwen2.5-vl",
            pipeline_mode="hybrid",
            pages="1-5",
            duration_s=12.5,
            status="complete",
            failed_pages=(),
            log_job_id="canonical-id",
            text_artifact_id="ta-1",
        )
    finally:
        legacy_records = state.job_history.list()
        state.job_history = original_history

    # Legacy deque: one record, legacy id, no text_artifact_id field
    # (the legacy JobRecord schema does not include it).
    assert len(legacy_records) == 1
    assert legacy_records[0]["id"] == "legacy-id"
    assert legacy_records[0]["filename"] == "doc.pdf"
    assert legacy_records[0]["status"] == "complete"
    assert legacy_records[0]["model"] == "qwen2.5-vl"

    # Log: one JobCompletedEvent with the canonical id and
    # text_artifact_id carried in the payload so the projection can
    # see it.
    log_events = log.list()
    assert len(log_events) == 1
    assert log_events[0].kind == "ocr.job.completed"
    assert log_events[0].payload["job_id"] == "canonical-id"
    assert log_events[0].payload["filename"] == "doc.pdf"
    assert log_events[0].payload["status"] == "complete"
    assert log_events[0].payload["duration_s"] == 12.5
    assert log_events[0].payload["text_artifact_id"] == "ta-1"


def test_record_job_defaults_log_job_id_to_job_id() -> None:
    """When ``log_job_id`` is not passed, it defaults to ``job_id``."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr, state

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    original_history = state.job_history
    state.job_history = JobHistory()
    try:
        ocr._record_job(
            job_id="same-id",
            filename="doc.pdf",
            model="m",
            pipeline_mode="hybrid",
            pages=None,
            duration_s=1.0,
            status="complete",
        )
    finally:
        state.job_history = original_history

    log_events = log.list()
    assert log_events[0].payload["job_id"] == "same-id"


def test_record_job_emits_error_in_payload() -> None:
    """``_record_job`` propagates ``error=`` into the JobCompletedEvent payload."""
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr, state

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    original_history = state.job_history
    state.job_history = JobHistory()
    try:
        ocr._record_job(
            job_id="j-err",
            filename="doc.pdf",
            model="m",
            pipeline_mode="hybrid",
            pages=None,
            duration_s=0.5,
            status="error",
            error="OCR pipeline raised ValueError: bad page",
        )
    finally:
        state.job_history = original_history

    log_events = log.list()
    assert log_events[0].payload["status"] == "error"
    assert log_events[0].payload["error"] == "OCR pipeline raised ValueError: bad page"


# -- End-to-end: full lifecycle through the emit helpers --------------------


def test_full_lifecycle_through_emit_helpers_folds_into_projection() -> None:
    """submitted → started → completed (via the helper) folds into a JobRecord.

    Verifies the Phase 3c story end to end: the OCR route calls the
    three helpers in order, the auto-append fan-out writes them to
    the log, and the projection reconstructs a JobRecord with the
    same fields the legacy JobHistory would have stored.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr, state

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    canonical_id = "j-full"
    original_history = state.job_history
    state.job_history = JobHistory()
    try:
        ocr._emit_job_submitted(canonical_id, "doc.pdf")
        ocr._emit_job_started(
            canonical_id,
            model="qwen2.5-vl",
            pipeline_mode="hybrid",
            pages="1-3",
        )
        ocr._record_job(
            job_id="legacy-j-full",
            filename="doc.pdf",
            model="qwen2.5-vl",
            pipeline_mode="hybrid",
            pages="1-3",
            duration_s=10.0,
            status="complete",
            failed_pages=(),
            log_job_id=canonical_id,
            text_artifact_id="ta-full",
        )
        legacy = state.job_history.list()
    finally:
        state.job_history = original_history

    # The projection sees three events with the canonical id and
    # folds them into a single record.
    proj = JobHistoryProjection(log)
    rec = proj.list()[0]
    assert rec["id"] == canonical_id
    assert rec["filename"] == "doc.pdf"
    assert rec["status"] == "complete"
    assert rec["model"] == "qwen2.5-vl"
    assert rec["pipeline_mode"] == "hybrid"
    assert rec["pages"] == "1-3"
    assert rec["duration_s"] == 10.0
    assert rec["text_artifact_id"] == "ta-full"

    # The legacy record is still keyed by the legacy id — the two
    # stores agree on the rest of the fields but use different id
    # schemes during the migration window.
    assert len(legacy) == 1
    assert legacy[0]["id"] == "legacy-j-full"


def test_legacy_and_projection_have_same_field_set() -> None:
    """Phase 3c invariant: the projection output and the legacy
    JobHistory output expose the same field set (excluding
    ``timestamp`` which is opaque). This is the contract that lets
    a consumer swap one for the other without code changes.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import ocr, state

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)

    canonical_id = "j-shape"
    original_history = state.job_history
    state.job_history = JobHistory()
    try:
        ocr._emit_job_submitted(canonical_id, "x.pdf")
        ocr._emit_job_started(
            canonical_id, model="m", pipeline_mode="hybrid", pages="1-1"
        )
        ocr._record_job(
            job_id=canonical_id,
            filename="x.pdf",
            model="m",
            pipeline_mode="hybrid",
            pages="1-1",
            duration_s=1.0,
            status="complete",
            text_artifact_id="ta-shape",
        )
        legacy = state.job_history.list()
    finally:
        state.job_history = original_history

    projection = JobHistoryProjection(log).list()

    assert set(projection[0].keys()) == set(legacy[0].keys())
    for key in projection[0]:
        if key == "timestamp":
            continue
        assert projection[0][key] == legacy[0][key]


# -- Audit-secondary F10: dual-write shim exception scope --------------------


def test_dual_write_shim_propagates_programming_bugs(tmp_path) -> None:
    """A programming bug in a projection listener propagates to the caller.

    Audit-secondary F10: the dual-write shim in
    ``TextArtifactStore._emit_artifact_created`` used to catch
    ``Exception`` and log; that masked projection bugs as silent
    emit failures. The narrowed scope (``ServiceNotFoundError`` /
    ``ContextDisposedError``) lets ``KeyError`` / ``AttributeError``
    / ``TypeError`` propagate so a regression in the projection
    code is caught at the call site instead of silently dropping
    every artifact creation event.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.services.artifacts import TextArtifactStore

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))

    def buggy_listener(**_payload) -> None:
        raise KeyError("intentional programming bug in projection listener")

    ctx.on("artifact.created", buggy_listener, mode="emit")
    runtime.set_plugin_context(ctx)
    try:
        store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
        with pytest.raises(KeyError, match="intentional programming bug"):
            store.put(
                artifact_id="a" * 32,
                token="t" * 32,
                path=str(tmp_path / "text_a.json"),
            )
    finally:
        runtime.set_plugin_context(None)


def test_dual_write_shim_swallows_expected_context_errors(tmp_path) -> None:
    """A disposed / missing context does NOT raise from the shim.

    Audit-secondary F10: the shim's exception scope is the two
    expected "context is gone" errors. The primary write (in-memory
    ``_entries`` dict + backing file) must never be affected by a
    context-related failure on the secondary write path.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.services.artifacts import TextArtifactStore

    # No context mounted at all — the shim short-circuits.
    runtime.set_plugin_context(None)
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    # Should not raise.
    handle = store.put(
        artifact_id="b" * 32,
        token="u" * 32,
        path=str(tmp_path / "text_b.json"),
    )
    assert handle.artifact_id == "b" * 32
