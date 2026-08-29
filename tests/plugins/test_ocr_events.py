"""OCR events: re-export surface keeps the right domains and fields."""

from __future__ import annotations

from omniscribe.harness.events import AgentEvent, SessionEvent
from omniscribe.plugins.ocr import events


def test_lifecycle_events_are_session_events() -> None:
    queued = events.JobQueued(job_id="j1")
    # 2026-08-29 audit C-3 / H-3: ``artifact_token`` is the out-of-band
    # delivery channel for the async result token (status endpoint no
    # longer returns it). See ``JobCompleted`` in plugins/jobs.py.
    completed = events.JobCompleted(job_id="j1", artifact_id="a1", artifact_token="t1")
    failed = events.JobFailed(job_id="j1", error="boom")
    cancelled = events.JobCancelled(job_id="j1")
    for event in (queued, completed, failed, cancelled):
        assert isinstance(event, SessionEvent)
    assert completed.artifact_id == "a1"
    assert completed.artifact_token == "t1"
    assert failed.error == "boom"


def test_live_frames_are_agent_events() -> None:
    started = events.JobStarted(job_id="j1")
    frame = events.ProgressFrame(
        job_id="j1", channel_id="c1", frame={"percent": 42, "stage": "ocr"}
    )
    assert isinstance(started, AgentEvent)
    assert isinstance(frame, AgentEvent)
    assert frame.channel_id == "c1"
    assert frame.frame == {"percent": 42, "stage": "ocr"}
