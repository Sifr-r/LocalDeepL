"""JobQueue plugin — single-worker async job queue over StateBackend.

Job lifecycle events are defined here (not in the OCR plugin) so the queue
never imports its producer: the OCR plugin registers a :class:`JobRunner`
service which the worker resolves lazily at claim time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, NamedTuple, Protocol, cast, runtime_checkable

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.events import AgentEvent, SessionEvent
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.state_backend import JobRecord, StateBackend

_LOGGER = logging.getLogger("omniscribe.plugins.jobs")

_TERMINAL_STATUSES = {"complete", "error", "cancelled"}


# -- events -------------------------------------------------------------------


@dataclass(frozen=True)
class JobQueued(SessionEvent):
    job_id: str


@dataclass(frozen=True)
class JobStarted(AgentEvent):
    job_id: str


@dataclass(frozen=True)
class JobCompleted(SessionEvent):
    """Fired once a job's result blob has been written to the artifact store.

    The ``artifact_token`` is the out-of-band delivery channel for the
    async path — the same role the sync path's ``X-Text-Artifact-Token``
    response header plays. The unauthenticated status polling endpoint
    (``GET /api/process/status/{job_id}``) deliberately does **not**
    return the token; the client consumes it from this event payload
    (SSE stream at ``/api/process/{job_id}/events``) instead. The
    artifact id alone is safe to expose everywhere.
    """

    job_id: str
    artifact_id: str
    artifact_token: str


@dataclass(frozen=True)
class JobFailed(SessionEvent):
    job_id: str
    error: str


@dataclass(frozen=True)
class JobCancelled(SessionEvent):
    job_id: str


# -- runner seam ----------------------------------------------------------------


@dataclass(frozen=True)
class JobOutcome:
    """What a runner returns: the result blob plus its content type."""

    blob: bytes
    content_type: str


@runtime_checkable
class JobRunner(Protocol):
    """Executes one queued request; registered by the OCR plugin."""

    async def __call__(self, request: Any) -> JobOutcome: ...


@runtime_checkable
class TranslationJobRunner(Protocol):
    """Executes one queued translation request; registered by the translate plugin."""

    async def __call__(self, request: Any) -> JobOutcome: ...


# -- queue ----------------------------------------------------------------------


class JobHandle(NamedTuple):
    """Opaque job id plus the status-polling URL for the frontend."""

    job_id: str
    status_url: str


@runtime_checkable
class JobQueue(Protocol):
    """Async OCR job queue seam."""

    async def submit(
        self, request: Any, *, request_meta: dict[str, Any] | None = None
    ) -> JobHandle: ...

    async def status(self, job_id: str) -> JobRecord | None: ...

    async def cancel(self, job_id: str) -> bool: ...

    def is_cancelled(self, job_id: str) -> bool: ...

    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]: ...

    async def clear(self) -> int: ...


class InMemoryJobQueue:
    """One ``asyncio.Queue`` drained by a single worker task.

    Cancellation is cooperative: queued jobs are marked ``cancelled`` before
    they run; running jobs expose :meth:`is_cancelled` for the runner to poll
    at block boundaries.
    """

    def __init__(
        self,
        ctx: Context,
        backend: StateBackend,
        artifacts: ArtifactStore,
        *,
        runner: JobRunner | None = None,
    ) -> None:
        self._ctx = ctx
        self._backend = backend
        self._artifacts = artifacts
        self._runner_override = runner
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._payloads: dict[str, Any] = {}
        self._cancelled: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    # -- public seam -------------------------------------------------------

    async def submit(
        self, request: Any, *, request_meta: dict[str, Any] | None = None
    ) -> JobHandle:
        job_id = uuid.uuid4().hex
        now = time.time()
        await self._backend.upsert_job(
            JobRecord(
                job_id=job_id,
                status="queued",
                request_meta=dict(request_meta or {}),
                created_at=now,
                updated_at=now,
            )
        )
        self._payloads[job_id] = request
        await self._queue.put(job_id)
        await self._ctx.emit(JobQueued(job_id=job_id))
        return JobHandle(job_id=job_id, status_url=f"/api/process/status/{job_id}")

    async def status(self, job_id: str) -> JobRecord | None:
        return await self._backend.get_job(job_id)

    async def cancel(self, job_id: str) -> bool:
        record = await self._backend.get_job(job_id)
        if record is None or record.status in _TERMINAL_STATUSES:
            return False
        self._cancelled.add(job_id)
        if record.status == "queued":
            await self._backend.upsert_job(
                replace(record, status="cancelled", updated_at=time.time())
            )
            await self._ctx.emit(JobCancelled(job_id=job_id))
        return True

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]:
        return await self._backend.list_jobs(limit=limit)

    async def clear(self) -> int:
        count = await self._backend.clear_jobs()
        self._payloads.clear()
        self._cancelled.clear()
        return count

    # -- worker lifecycle ------------------------------------------------------

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.get_running_loop().create_task(
                self._run(), name="omniscribe-job-worker"
            )

    async def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        # Pending work will never run now — mark it cancelled for callers.
        # Paginate until exhausted: list_jobs orders created_at DESC, so a
        # single bounded page would strand older queued rows forever
        # (pedantic review 1.6).
        offset = 0
        while True:
            page = await self._backend.list_jobs(limit=100, offset=offset)
            if not page:
                break
            offset += len(page)
            for record in page:
                if record.status == "queued":
                    await self._backend.upsert_job(
                        replace(record, status="cancelled", updated_at=time.time())
                    )
        self._payloads.clear()

    async def _run(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process_one(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("job worker failed for %s", job_id)
            finally:
                self._queue.task_done()

    def _resolve_runner(self, payload: Any) -> JobRunner:
        if self._runner_override is not None:
            return self._runner_override
        # Multi-producer dispatch: a payload class may self-describe the
        # service key its runner is registered under (the translate plugin
        # does); unmarked payloads keep the default OCR JobRunner seam.
        marker = getattr(type(payload), "runner_protocol", None)
        if marker is not None:
            return cast("JobRunner", self._ctx.inject(marker))
        return cast("JobRunner", self._ctx.inject(JobRunner))

    async def _process_one(self, job_id: str) -> None:
        payload = self._payloads.pop(job_id, None)
        if job_id in self._cancelled:
            await self._mark_cancelled(job_id, emit=True)
            return
        record = await self._backend.get_job(job_id)
        if record is None:
            return
        runner = self._resolve_runner(payload)
        await self._backend.upsert_job(
            replace(record, status="running", updated_at=time.time())
        )
        await self._ctx.emit(JobStarted(job_id=job_id))
        try:
            outcome = await runner(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            await self._set_error(job_id, message)
            await self._ctx.emit(JobFailed(job_id=job_id, error=message))
            return
        if job_id in self._cancelled:
            # The runner honored the cooperative cancel at a block boundary.
            await self._mark_cancelled(job_id, emit=True)
            return
        handle = await self._artifacts.put(
            outcome.blob,
            content_type=outcome.content_type,
            owner_job_id=job_id,
        )
        current = await self._backend.get_job(job_id)
        if current is not None:
            await self._backend.upsert_job(
                replace(
                    current,
                    status="complete",
                    result_artifact_id=handle.id,
                    result_artifact_token=handle.token,
                    updated_at=time.time(),
                )
            )
        await self._ctx.emit(
            JobCompleted(
                job_id=job_id,
                artifact_id=handle.id,
                artifact_token=handle.token,
            )
        )

    async def _mark_cancelled(self, job_id: str, *, emit: bool) -> None:
        self._cancelled.discard(job_id)
        record = await self._backend.get_job(job_id)
        transitioned = False
        if record is not None and record.status not in _TERMINAL_STATUSES:
            await self._backend.upsert_job(
                replace(record, status="cancelled", updated_at=time.time())
            )
            transitioned = True
        if emit and transitioned:
            await self._ctx.emit(JobCancelled(job_id=job_id))

    async def _set_error(self, job_id: str, message: str) -> None:
        record = await self._backend.get_job(job_id)
        if record is not None:
            await self._backend.upsert_job(
                replace(record, status="error", error=message, updated_at=time.time())
            )


# -- plugin ---------------------------------------------------------------------


class JobsSchema(BaseModel):
    worker_count: int = 1


class JobsPlugin(Plugin):
    """Mounts the single-worker queue; the runner arrives later via DI."""

    Schema = JobsSchema

    async def apply(self, ctx: Context) -> None:
        worker_count = int(self.config.get("worker_count", 1))
        if worker_count != 1:
            _LOGGER.warning(
                "worker_count=%d requested; this build ships a single worker",
                worker_count,
            )
        backend = ctx.inject(StateBackend)
        artifacts = ctx.inject(ArtifactStore)
        queue = InMemoryJobQueue(ctx, backend, artifacts)
        queue.start()
        ctx.service(JobQueue, queue)
        ctx.effect(queue.shutdown)


plugin = JobsPlugin()


__all__ = [
    "InMemoryJobQueue",
    "JobCancelled",
    "JobCompleted",
    "JobFailed",
    "JobHandle",
    "JobOutcome",
    "JobQueue",
    "JobQueued",
    "JobRunner",
    "JobStarted",
    "JobsPlugin",
    "JobsSchema",
    "TranslationJobRunner",
    "plugin",
]
