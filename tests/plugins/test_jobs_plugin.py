"""Jobs plugin: single-worker queue lifecycle, cancel, events, shutdown."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from omniscribe.harness.context import Context
from omniscribe.harness.errors import ServiceNotFoundError
from omniscribe.harness.events import Event
from omniscribe.plugins import artifacts as art
from omniscribe.plugins import jobs
from omniscribe.plugins import state_backend as sb
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.jobs import (
    JobCancelled,
    JobCompleted,
    JobFailed,
    JobOutcome,
    JobQueue,
    JobQueued,
    JobRunner,
    JobStarted,
)
from omniscribe.plugins.state_backend import JobRecord


async def _boot(runner: JobRunner | None = None) -> Context:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    await ctx.plugin(art.ArtifactsPlugin(), config={})
    if runner is not None:
        ctx.service(JobRunner, runner)
    await ctx.plugin(jobs.JobsPlugin(), config={})
    return ctx


async def _wait_status(
    queue: JobQueue, job_id: str, status: str, *, timeout: float = 5.0
) -> JobRecord:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = await queue.status(job_id)
        if record is not None and record.status == status:
            return record
        await asyncio.sleep(0.01)
    record = await queue.status(job_id)
    raise AssertionError(f"job {job_id} never reached {status!r}; last={record}")


async def test_submit_returns_handle_and_full_lifecycle() -> None:
    gate = asyncio.Event()

    async def runner(request: Any) -> JobOutcome:
        await gate.wait()
        return JobOutcome(blob=b"result-pdf", content_type="application/pdf")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    handle = await queue.submit({"page": 1}, request_meta={"filename": "a.pdf"})
    assert handle.status_url == f"/api/process/status/{handle.job_id}"
    await _wait_status(queue, handle.job_id, "running")
    gate.set()
    record = await _wait_status(queue, handle.job_id, "complete")
    assert record.request_meta == {"filename": "a.pdf"}
    assert record.result_artifact_id and record.result_artifact_token
    store = ctx.inject(ArtifactStore)
    blob = await store.get(record.result_artifact_id, record.result_artifact_token)
    assert blob is not None and blob.blob == b"result-pdf"
    await ctx.dispose()


async def test_second_job_stays_queued_until_worker_is_free() -> None:
    gate = asyncio.Event()

    async def runner(request: Any) -> JobOutcome:
        await gate.wait()
        return JobOutcome(blob=b"x", content_type="t/t")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    first = await queue.submit({"n": 1})
    await _wait_status(queue, first.job_id, "running")
    second = await queue.submit({"n": 2})
    record = await queue.status(second.job_id)
    assert record is not None and record.status == "queued"
    gate.set()
    await _wait_status(queue, first.job_id, "complete")
    await _wait_status(queue, second.job_id, "complete")
    await ctx.dispose()


async def test_raising_runner_marks_job_error() -> None:
    async def runner(request: Any) -> JobOutcome:
        raise RuntimeError("vlm endpoint down")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    handle = await queue.submit({})
    record = await _wait_status(queue, handle.job_id, "error")
    assert record.error is not None and "vlm endpoint down" in record.error
    assert record.result_artifact_id is None
    await ctx.dispose()


async def test_cancel_queued_job_before_it_runs() -> None:
    gate = asyncio.Event()
    ran: list[Any] = []

    async def runner(request: Any) -> JobOutcome:
        await gate.wait()
        ran.append(request)
        return JobOutcome(blob=b"x", content_type="t/t")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    first = await queue.submit({"n": 1})
    await _wait_status(queue, first.job_id, "running")
    second = await queue.submit({"n": 2})
    assert await queue.cancel(second.job_id) is True
    record = await queue.status(second.job_id)
    assert record is not None and record.status == "cancelled"
    gate.set()
    await _wait_status(queue, first.job_id, "complete")
    await asyncio.sleep(0.05)  # let the worker drain the queue
    assert (await queue.status(second.job_id)).status == "cancelled"  # type: ignore[union-attr]
    assert ran == [{"n": 1}]  # the cancelled job never ran
    assert await queue.cancel(second.job_id) is False  # terminal
    assert await queue.cancel("unknown") is False
    await ctx.dispose()


async def test_list_and_clear_delegate_to_state() -> None:
    async def runner(request: Any) -> JobOutcome:
        return JobOutcome(blob=b"x", content_type="t/t")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    handle = await queue.submit({}, request_meta={"filename": "a.pdf"})
    await _wait_status(queue, handle.job_id, "complete")
    listed = await queue.list_jobs()
    assert [r.job_id for r in listed] == [handle.job_id]
    assert await queue.clear() == 1
    assert await queue.list_jobs() == []
    await ctx.dispose()


async def test_lifecycle_events_emitted() -> None:
    async def runner(request: Any) -> JobOutcome:
        return JobOutcome(blob=b"x", content_type="t/t")

    ctx = await _boot(runner)
    seen: dict[str, list[Event]] = {
        "queued": [],
        "started": [],
        "completed": [],
        "failed": [],
        "cancelled": [],
    }

    def _collect(bucket: str) -> Any:
        def _handler(event: Event) -> None:
            seen[bucket].append(event)

        return _handler

    ctx.on(JobQueued, _collect("queued"))
    ctx.on(JobStarted, _collect("started"))
    ctx.on(JobCompleted, _collect("completed"))
    ctx.on(JobFailed, _collect("failed"))
    ctx.on(JobCancelled, _collect("cancelled"))
    queue = ctx.inject(JobQueue)
    handle = await queue.submit({})
    record = await _wait_status(queue, handle.job_id, "complete")
    assert [e.job_id for e in seen["queued"]] == [handle.job_id]
    assert [e.job_id for e in seen["started"]] == [handle.job_id]
    completed = seen["completed"]
    assert len(completed) == 1
    assert isinstance(completed[0], JobCompleted)
    assert completed[0].artifact_id == record.result_artifact_id
    assert seen["failed"] == [] and seen["cancelled"] == []
    await ctx.dispose()


async def test_shutdown_marks_pending_jobs_cancelled() -> None:
    gate = asyncio.Event()

    async def runner(request: Any) -> JobOutcome:
        await gate.wait()
        return JobOutcome(blob=b"x", content_type="t/t")

    ctx = await _boot(runner)
    queue = ctx.inject(JobQueue)
    first = await queue.submit({"n": 1})
    await _wait_status(queue, first.job_id, "running")
    second = await queue.submit({"n": 2})
    await ctx.dispose()  # effect: queue.shutdown()
    assert (await queue.status(second.job_id)).status == "cancelled"  # type: ignore[union-attr]


async def test_shutdown_cancels_queued_jobs_beyond_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pedantic review 1.6: shutdown must cancel ALL queued jobs, not
    only the newest page (list_jobs orders created_at DESC)."""
    ctx = await _boot()
    try:
        queue = ctx.inject(JobQueue)
        backend = ctx.inject(sb.StateBackend)
        for i in range(5):
            await backend.upsert_job(JobRecord(job_id=f"j{i}", status="queued"))

        real_list = backend.list_jobs

        async def two_per_page(**kwargs: Any) -> list[JobRecord]:
            # Emulate a 2-row page regardless of the caller's limit so a
            # single bounded list_jobs call cannot see the whole queue.
            # Forwards offset so the paginated shutdown walks every page.
            kwargs["limit"] = 2
            return await real_list(**kwargs)

        monkeypatch.setattr(backend, "list_jobs", two_per_page)

        await queue.shutdown()

        records = await real_list(limit=100)
        assert {r.status for r in records} == {"cancelled"}
    finally:
        await ctx.dispose()


async def test_missing_artifact_store_fails_loud() -> None:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    with pytest.raises(ServiceNotFoundError):
        await ctx.plugin(jobs.JobsPlugin(), config={})
    await ctx.dispose()
