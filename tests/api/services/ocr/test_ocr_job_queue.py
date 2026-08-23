"""Tests for OCRJobQueue — single-worker asyncio background OCR queue (§2)."""

from __future__ import annotations

import asyncio

import pytest

from omniscribe.api.services.ocr.jobs import (
    OCRJobQueue,
    OCRJobRecord,
    OCRJobResult,
    OCRJobStatus,
)


async def test_submit_status_flips_through_pipeline():
    queue = OCRJobQueue()
    await queue.start()
    try:

        async def _ok_runner() -> OCRJobResult:
            return OCRJobResult(
                text_artifact_id="aid-1",
                text_artifact_token="tok-1",
                output_pdf_path="/tmp/x.pdf",
                failed_pages=[],
            )

        job_id = await queue.submit("job-1", "doc.pdf", _ok_runner)
        assert job_id == "job-1"

        # Wait for the worker to process the job.
        for _ in range(50):
            record = await queue.get(job_id)
            if record is not None and record.status is OCRJobStatus.COMPLETE:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("job did not complete in time")

        d = record.to_dict()
        assert d["status"] == "complete"
        assert d["job_id"] == "job-1"
        assert d["text_artifact_id"] == "aid-1"
        assert d["text_artifact_token"] == "tok-1"
        assert d["text_artifact_url"] == "/api/text/aid-1"
        # Token is intentionally NOT in the URL — clients attach it as
        # `Authorization: Bearer <token>` to keep the secret out of
        # proxy access logs. See api/services/ocr_jobs.py.
        assert "token=" not in d["text_artifact_url"]
    finally:
        await queue.stop()


async def test_runner_exception_records_error_status():
    queue = OCRJobQueue()
    await queue.start()
    try:

        async def _bad_runner() -> OCRJobResult:
            raise RuntimeError("boom")

        await queue.submit("job-2", "doc.pdf", _bad_runner)
        for _ in range(50):
            record = await queue.get("job-2")
            if record is not None and record.status is OCRJobStatus.ERROR:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("job did not error in time")

        assert record.error == "boom"
        d = record.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "boom"
    finally:
        await queue.stop()


async def test_get_unknown_returns_none_and_list_returns_submitted():
    queue = OCRJobQueue()
    assert await queue.get("nope") is None

    async def _ok_runner() -> OCRJobResult:
        return OCRJobResult(
            text_artifact_id="x",
            text_artifact_token="y",
            output_pdf_path="",
            failed_pages=[],
        )

    await queue.start()
    try:
        await queue.submit("a", "f.pdf", _ok_runner)
        await queue.submit("b", "f.pdf", _ok_runner)
        records = await queue.list()
        assert {r.job_id for r in records} >= {"a", "b"}
    finally:
        await queue.stop()


async def test_max_pending_one_blocks_second_submit():
    """Without the worker, the queue fills to maxsize and a 2nd put blocks."""
    queue = OCRJobQueue(max_pending=1)

    # Don't start the worker — that way the first put fills the queue and
    # the second put blocks on the bounded asyncio.Queue.
    async def _ok_runner() -> OCRJobResult:
        return OCRJobResult(
            text_artifact_id="x",
            text_artifact_token="y",
            output_pdf_path="",
            failed_pages=[],
        )

    await queue.submit("first", "f.pdf", _ok_runner)
    # Second submit must block because the queue size is 1 and no worker
    # is draining it.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.submit("second", "f.pdf", _ok_runner), 0.05)


async def test_start_is_idempotent():
    queue = OCRJobQueue()
    await queue.start()
    await queue.start()  # idempotent
    assert queue._worker is not None
    await queue.stop()
    assert queue._worker is None


async def test_stop_cancels_worker():
    queue = OCRJobQueue()
    await queue.start()
    await queue.stop()
    assert queue._worker is None


async def test_cancel_unknown_job_returns_none():
    queue = OCRJobQueue()
    assert await queue.cancel("missing") is None


async def test_cancel_pending_job_removes_record():
    """Without a worker draining the queue, a pending job is cancelled
    by popping it from the records map; the worker would later pop
    the queue entry and find no runner, so it skips the job."""
    queue = OCRJobQueue(max_pending=1)
    # Do NOT start the worker — the job stays in PENDING.

    async def _ok_runner() -> OCRJobResult:
        return OCRJobResult(
            text_artifact_id="x",
            text_artifact_token="y",
            output_pdf_path="",
            failed_pages=[],
        )

    await queue.submit("pending-1", "doc.pdf", _ok_runner)
    record = await queue.get("pending-1")
    assert record is not None
    assert record.status is OCRJobStatus.PENDING

    cancelled = await queue.cancel("pending-1")
    assert cancelled is not None
    # After cancellation the record is gone so the worker can't run it.
    assert await queue.get("pending-1") is None


async def test_cancel_complete_job_is_noop_idempotent():
    """Cancelling a completed job must not throw; the record is
    untouched and the worker is unaffected."""
    queue = OCRJobQueue()
    await queue.start()
    try:

        async def _ok_runner() -> OCRJobResult:
            return OCRJobResult(
                text_artifact_id="aid-1",
                text_artifact_token="tok-1",
                output_pdf_path="/tmp/x.pdf",
                failed_pages=[],
            )

        await queue.submit("done-1", "doc.pdf", _ok_runner)
        for _ in range(50):
            record = await queue.get("done-1")
            if record is not None and record.status is OCRJobStatus.COMPLETE:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("job did not complete in time")

        again = await queue.cancel("done-1")
        assert again is not None
        assert again.status is OCRJobStatus.COMPLETE
    finally:
        await queue.stop()


async def test_cancel_processing_job_marks_error_with_cancellation_message():
    """A job that is mid-flight when cancelled is marked ERROR with a
    clear cancellation message so the client sees a terminal state
    without waiting for the pipeline to finish."""
    queue = OCRJobQueue()
    await queue.start()
    try:
        started = asyncio.Event()

        async def _slow_runner() -> OCRJobResult:
            started.set()
            await asyncio.sleep(0.5)
            return OCRJobResult(
                text_artifact_id="aid-2",
                text_artifact_token="tok-2",
                output_pdf_path="/tmp/x.pdf",
                failed_pages=[],
            )

        await queue.submit("slow-1", "doc.pdf", _slow_runner)
        # Wait until the worker actually picks the job up.
        await asyncio.wait_for(started.wait(), timeout=1.0)

        cancelled = await queue.cancel("slow-1")
        assert cancelled is not None
        assert cancelled.status is OCRJobStatus.ERROR
        assert cancelled.error == "cancelled by client"
        assert cancelled.completed_at is not None
        assert cancelled.duration_s is not None

        # The runner is allowed to wind down, but its eventual success must
        # not overwrite the cancellation terminal state.
        await asyncio.sleep(0.55)
        after_runner = await queue.get("slow-1")
        assert after_runner is not None
        assert after_runner.status is OCRJobStatus.ERROR
        assert after_runner.error == "cancelled by client"
    finally:
        await queue.stop()


async def test_cancelled_runner_failure_preserves_cancellation_message():
    """A late runner exception must not overwrite a processing cancellation."""
    queue = OCRJobQueue()
    await queue.start()
    try:
        started = asyncio.Event()
        release = asyncio.Event()

        async def _failing_runner() -> OCRJobResult:
            started.set()
            await release.wait()
            raise RuntimeError("late pipeline failure")

        await queue.submit("slow-failure", "doc.pdf", _failing_runner)
        await asyncio.wait_for(started.wait(), timeout=1.0)

        cancelled = await queue.cancel("slow-failure")
        assert cancelled is not None
        assert cancelled.error == "cancelled by client"

        release.set()
        await asyncio.sleep(0.05)
        after_runner = await queue.get("slow-failure")
        assert after_runner is not None
        assert after_runner.status is OCRJobStatus.ERROR
        assert after_runner.error == "cancelled by client"
    finally:
        await queue.stop()


# ---------------------------------------------------------------------------
# §3.3 (audit correction) — TTL eviction for OCRJobQueue._records.
# ---------------------------------------------------------------------------


def _seed_terminal_record(
    queue: OCRJobQueue,
    job_id: str,
    status: OCRJobStatus,
    *,
    completed_at: float,
) -> None:
    """Insert a record directly so the test does not need the async worker."""
    rec = OCRJobRecord(
        job_id=job_id,
        filename="doc.pdf",
        status=status,
        completed_at=completed_at,
    )
    queue._records[job_id] = rec


def test_cleanup_expired_evicts_old_terminal_records():
    """§3.3 regression: COMPLETE/ERROR records older than retention_s are dropped."""
    import time

    now = time.monotonic()
    queue = OCRJobQueue(retention_s=10.0)
    _seed_terminal_record(
        queue,
        "old-complete",
        OCRJobStatus.COMPLETE,
        completed_at=now - 30.0,  # way past retention
    )
    _seed_terminal_record(
        queue,
        "fresh-complete",
        OCRJobStatus.COMPLETE,
        completed_at=now - 1.0,  # within retention
    )
    _seed_terminal_record(
        queue,
        "old-error",
        OCRJobStatus.ERROR,
        completed_at=now - 30.0,
    )

    evicted = queue.cleanup_expired()

    assert evicted == 2
    assert "old-complete" not in queue._records
    assert "fresh-complete" in queue._records
    assert "old-error" not in queue._records


def test_cleanup_expired_preserves_pending_and_processing():
    """§3.3 regression: active records are never evicted, even if completed_at is past."""
    import time

    now = time.monotonic()
    queue = OCRJobQueue(retention_s=1.0)
    _seed_terminal_record(
        queue,
        "pending-stale",
        OCRJobStatus.PENDING,
        completed_at=now - 100.0,  # past retention but not terminal
    )
    _seed_terminal_record(
        queue,
        "processing-stale",
        OCRJobStatus.PROCESSING,
        completed_at=now - 100.0,
    )

    evicted = queue.cleanup_expired()

    assert evicted == 0
    assert "pending-stale" in queue._records
    assert "processing-stale" in queue._records


def test_cleanup_expired_disabled_with_non_positive_retention():
    """§3.3 regression: retention_s <= 0 is the documented 'off' sentinel."""
    import time

    now = time.monotonic()
    queue = OCRJobQueue(retention_s=0)
    _seed_terminal_record(
        queue,
        "ancient",
        OCRJobStatus.COMPLETE,
        completed_at=now - 100_000.0,
    )

    evicted = queue.cleanup_expired()

    assert evicted == 0
    assert "ancient" in queue._records
