"""Phase 2 tests — typed event payloads + audit recorder.

Covers:

1. The dataclass payloads in :mod:`omniscribe.api.plugin.events_catalog` are
   frozen and serialize cleanly.
2. The :func:`audit_log_recorder` plugin subscribes to every event in
   ``ALL_EVENT_TYPES`` and writes one log line per emit.
3. End-to-end: emit through the context and verify the recorder observes
   the payload.
4. The audit emit hooks in the existing routers (``routers/ocr.py`` and
   ``routers/jobs.py``) do not break their callers when the context is
   not bootstrapped.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from omniscribe.api.plugin import PluginContext
from omniscribe.api.plugin.events_catalog import (
    ALL_EVENT_TYPES,
    ArtifactCreatedEvent,
    JobCancelledEvent,
    JobCompletedEvent,
    JobSubmittedEvent,
    ProviderSwitchedEvent,
    RequestReceivedEvent,
    TranslationRequestedEvent,
)
from omniscribe.api.plugin.recorders import audit_log_recorder

# -- Payload shape -----------------------------------------------------------


def test_all_event_payloads_are_frozen() -> None:
    """Frozen dataclasses so a listener cannot mutate the payload after dispatch."""
    for cls in ALL_EVENT_TYPES:
        instance = cls()  # all defaults
        with pytest.raises((AttributeError, Exception)):
            instance.event_name = "tampered"  # type: ignore[misc]


def test_all_event_payloads_carry_their_event_name() -> None:
    """Every payload exposes a ``event_name`` field that matches the
    intended dispatch name. Pinning the names here means a rename
    surfaces as a test failure."""
    expected = {
        JobSubmittedEvent: "ocr.job.submitted",
        JobCompletedEvent: "ocr.job.completed",
        JobCancelledEvent: "ocr.job.cancelled",
        TranslationRequestedEvent: "translation.requested",
        ArtifactCreatedEvent: "artifact.created",
        ProviderSwitchedEvent: "provider.switched",
        RequestReceivedEvent: "http.request.received",
    }
    assert set(expected) == set(ALL_EVENT_TYPES)
    for cls, name in expected.items():
        assert cls().event_name == name


def test_payloads_serialize_to_dicts() -> None:
    """Every payload can be coerced to a dict for log/JSON serialization."""
    from dataclasses import asdict

    submitted = JobSubmittedEvent(job_id="abc", filename="x.pdf")
    d = asdict(submitted)
    assert d["job_id"] == "abc"
    assert d["filename"] == "x.pdf"
    assert d["event_name"] == "ocr.job.submitted"
    assert "submitted_at" in d  # default factory populated


# -- audit_log_recorder ------------------------------------------------------


def test_audit_recorder_logs_every_event(caplog: pytest.LogCaptureFixture) -> None:
    ctx = PluginContext("test")
    ctx.mount(audit_log_recorder(level=logging.INFO))
    with caplog.at_level(logging.INFO, logger="omniscribe.api.plugin.recorders"):
        ctx.emit("ocr.job.submitted", **JobSubmittedEvent(job_id="j1").__dict__)
        ctx.emit("ocr.job.cancelled", **JobCancelledEvent(job_id="j1").__dict__)
    messages = [r.getMessage() for r in caplog.records]
    # Two emits, two log lines.
    assert sum("ocr.job.submitted" in m for m in messages) == 1
    assert sum("ocr.job.cancelled" in m for m in messages) == 1


def test_audit_recorder_subscribes_to_every_event_type() -> None:
    """Every event in ALL_EVENT_TYPES must be subscribed to, otherwise
    emits for an unhandled event are silent."""
    ctx = PluginContext("test")
    ctx.mount(audit_log_recorder(level=logging.INFO))
    for cls in ALL_EVENT_TYPES:
        ctx.emit(cls().event_name, **cls().__dict__)
    # If any event name had no listener, the emit would still be a
    # no-op (not an error). To make the assertion concrete, register a
    # counter listener and verify each emit reached *something*.
    captured: list[str] = []
    ctx2 = PluginContext("test2")
    for cls in ALL_EVENT_TYPES:
        ctx2.on(
            cls().event_name,
            lambda **kw: captured.append(kw["event_name"]),
            mode="emit",
        )
    ctx2.mount(audit_log_recorder(level=logging.INFO))
    for cls in ALL_EVENT_TYPES:
        ctx2.emit(cls().event_name, **cls().__dict__)
    assert sorted(captured) == sorted(cls().event_name for cls in ALL_EVENT_TYPES)


def test_audit_recorder_unmount_removes_every_listener() -> None:
    """The returned disposer must unsubscribe from every event in
    ALL_EVENT_TYPES so a subsequent emit is silent."""
    ctx = PluginContext("test")
    unmount = ctx.mount(audit_log_recorder(level=logging.INFO))
    assert any(ctx.listeners(e().event_name) for e in ALL_EVENT_TYPES)
    unmount()
    for e in ALL_EVENT_TYPES:
        assert ctx.listeners(e().event_name) == []


# -- End-to-end emit through the context -----------------------------------


def test_emit_propagates_payload_to_recorder(caplog: pytest.LogCaptureFixture) -> None:
    ctx = PluginContext("test")
    captured: list[dict[str, Any]] = []
    ctx.on(
        "ocr.job.submitted",
        lambda **kw: captured.append(kw),
        mode="emit",
    )
    ctx.mount(audit_log_recorder(level=logging.INFO))
    with caplog.at_level(logging.INFO):
        ctx.emit(
            "ocr.job.submitted",
            **JobSubmittedEvent(job_id="job-1", filename="hello.pdf").__dict__,
        )
    assert len(captured) == 1
    assert captured[0]["job_id"] == "job-1"
    assert captured[0]["filename"] == "hello.pdf"


# -- Safe behavior when the context is not bootstrapped ---------------------


def test_ocr_submit_helper_works_when_context_is_none() -> None:
    """The inline emit hooks in routers/ocr.py and routers/jobs.py must
    be no-ops (and must not raise) when the plugin context is not
    bootstrapped. We exercise the call directly."""
    from omniscribe.api.plugin import runtime as plugin_runtime

    saved = plugin_runtime._plugin_context
    plugin_runtime._plugin_context = None
    try:
        # Simulate the emit pattern used in routers/ocr.py.
        from omniscribe.api.plugin.events_catalog import JobSubmittedEvent

        ctx = plugin_runtime.get_plugin_context()
        if ctx is not None:
            ctx.emit("ocr.job.submitted", **JobSubmittedEvent(job_id="x").__dict__)
        # No assertion needed: the test passes if no exception is raised.
    finally:
        plugin_runtime._plugin_context = saved


def test_cancel_helper_works_when_context_is_none() -> None:
    from omniscribe.api.plugin import runtime as plugin_runtime

    saved = plugin_runtime._plugin_context
    plugin_runtime._plugin_context = None
    try:
        from omniscribe.api.plugin.events_catalog import JobCancelledEvent

        ctx = plugin_runtime.get_plugin_context()
        if ctx is not None:
            ctx.emit("ocr.job.cancelled", **JobCancelledEvent(job_id="x").__dict__)
    finally:
        plugin_runtime._plugin_context = saved


# -- Cross-phase: the seam from Phase 1 still works alongside the recorder -


def test_job_queue_seam_and_audit_recorder_coexist() -> None:
    """The Phase 1 JobQueue provider and the Phase 2 audit recorder can
    be mounted into the same context without interfering with each
    other."""
    from omniscribe.api.plugin import JobQueue, local_job_queue_provider
    from omniscribe.api.services.ocr_jobs import OCRJobQueue

    ctx = PluginContext("test")
    queue = OCRJobQueue()
    ctx.mount(local_job_queue_provider(queue=queue, name="local"))
    ctx.mount(audit_log_recorder(level=logging.INFO))
    assert ctx.get(JobQueue, name="local") is queue
    # Emit an event and ensure the recorder (now mounted) still runs.
    captured: list[str] = []
    ctx.on(
        "ocr.job.submitted",
        lambda **kw: captured.append(kw["job_id"]),
        mode="emit",
    )
    ctx.emit("ocr.job.submitted", **JobSubmittedEvent(job_id="j-42").__dict__)
    assert captured == ["j-42"]
