"""In-process asyncio job queue for background OCR processing.

Jobs are submitted by ``POST /api/process/async`` and drained by a
single background worker coroutine started at app startup. The result
(a PDF + text artifact) is recorded on the :class:`OCRJobRecord` and
retrievable via ``GET /api/process/status/{job_id}``. State is
in-memory; restart loses pending jobs (matches the rest of the
in-memory state — a Redis backend would replace StateBackend entirely,
which is the next-layer scale-out path).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

#: Default retention for terminal-state (COMPLETE / ERROR) OCR job records.
#: Set to 0 (or any value <= 0) to disable TTL-based eviction entirely.
DEFAULT_OCR_JOB_RETENTION_S = 24 * 60 * 60  # 24h
_RETENTION_ENV_VAR = "OMNISCRIBE_OCR_JOB_RETENTION_S"


def _resolve_retention_s() -> float:
    """Read ``OMNISCRIBE_OCR_JOB_RETENTION_S``; fall back to default on bad input.

    Mirrors the :func:`server._artifact_cleanup_interval_s` pattern: empty,
    non-numeric, and out-of-range values fall back to the default rather
    than crashing at import. This is the same env-var surface that the
    artifact TTL sweeper uses, so all retention knobs can be tuned in one
    place.
    """
    raw = os.getenv(_RETENTION_ENV_VAR)
    if raw is None or not raw.strip():
        return float(DEFAULT_OCR_JOB_RETENTION_S)
    try:
        return max(0.0, float(raw.strip()))
    except (TypeError, ValueError):
        return float(DEFAULT_OCR_JOB_RETENTION_S)


class OCRJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class OCRJobResult:
    """Outcome of a finished OCR job, captured by the worker."""

    text_artifact_id: str
    text_artifact_token: str
    output_pdf_path: str
    failed_pages: list[int] = field(default_factory=list)


@dataclass
class OCRJobRecord:
    """Per-job state visible to the API and the worker."""

    job_id: str
    filename: str
    status: OCRJobStatus = OCRJobStatus.PENDING
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    completed_at: float | None = None
    duration_s: float | None = None
    error: str | None = None
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    output_pdf_path: str | None = None
    failed_pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "job_id": self.job_id,
            "filename": self.filename,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": self.duration_s,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.status is OCRJobStatus.COMPLETE:
            assert self.text_artifact_id is not None
            assert self.text_artifact_token is not None
            d["text_artifact_id"] = self.text_artifact_id
            d["text_artifact_token"] = self.text_artifact_token
            # URL is intentionally token-free: clients attach the token
            # as `Authorization: Bearer <token>` to keep the artifact
            # out of proxy access logs, browser history, and server
            # audit trails. The token is still returned via the
            # `text_artifact_token` field so a client that wants the
            # legacy URL form can construct it itself.
            d["text_artifact_url"] = f"/api/text/{self.text_artifact_id}"
            # REVIEW: `output_pdf_path` remains internal and is not serialized,
            # so async clients currently have no status-linked PDF download.
            # Keep this record shape synchronized with the artifact routes.
        if self.failed_pages:
            d["failed_pages"] = list(self.failed_pages)
        return d


OCRJobRunner = Callable[[], Awaitable[OCRJobResult]]


class OCRJobQueue:
    """Single-worker asyncio queue for OCR jobs.

    Single-worker by design: jobs run sequentially on the same uvicorn
    worker that accepted the request. Restart loses pending jobs (which
    is the same trade-off every other in-memory state holder already
    has). Multi-worker scale-out would require a Redis-backed
    StateBackend — out of scope for this iteration.
    """

    def __init__(
        self,
        *,
        max_pending: int = 16,
        retention_s: float | None = None,
    ) -> None:
        self._records: dict[str, OCRJobRecord] = {}
        self._runners: dict[str, OCRJobRunner] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_pending)
        self._lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None
        # ``retention_s`` controls how long terminal-state (COMPLETE / ERROR)
        # records survive in :meth:`cleanup_expired`. ``None`` resolves from
        # the env var at construction time so a runtime env override (via
        # the sweeper restart hook) is honoured.
        self._retention_s = (
            float(retention_s) if retention_s is not None else _resolve_retention_s()
        )

    @property
    def running(self) -> bool:
        """Return True if the background worker task is active and not finished."""
        return self._worker is not None and not self._worker.done()

    async def start(self) -> None:
        """Spawn the background worker (idempotent)."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(
                self._worker_loop(), name="ocr-job-worker"
            )

    async def stop(self) -> None:
        """Cancel the worker. Pending jobs are lost on restart."""
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        self._worker = None

    async def submit(self, job_id: str, filename: str, runner: OCRJobRunner) -> str:
        """Register a job and enqueue it for the worker. Returns job_id."""
        record = OCRJobRecord(job_id=job_id, filename=filename)
        async with self._lock:
            self._records[job_id] = record
            self._runners[job_id] = runner
        await self._queue.put(job_id)
        return job_id

    async def get(self, job_id: str) -> OCRJobRecord | None:
        async with self._lock:
            return self._records.get(job_id)

    async def list(self) -> list[OCRJobRecord]:
        async with self._lock:
            return list(self._records.values())

    def cleanup_expired(self) -> int:
        """Evict terminal-state (COMPLETE / ERROR) records older than ``retention_s``.

        Synchronous to match the contract other stores expose to the artifact
        sweeper (:func:`server._artifact_cleanup_loop`, which calls
        ``cleanup_expired()`` without ``await``). Returns the number of records
        evicted; a ``retention_s`` of ``0`` (or any non-positive value)
        disables TTL-based eviction entirely and always returns ``0``.

        Concurrency: snapshots the dict membership under a plain iteration,
        then pops outside the loop. The asyncio lock is intentionally not
        acquired — the only races are benign:

        * A concurrent :meth:`submit` only adds entries (different ``job_id``);
          never conflicts with an eviction decision.
        * A concurrent :meth:`cancel` on a PENDING record removes the entry
          before our pop runs; :meth:`dict.pop` with a default is a no-op.
        * A concurrent :meth:`_worker_loop` mutates the *status* of an existing
          record, not the dict membership; the snapshot already decided
          whether that ``job_id`` was eligible.
        """
        if self._retention_s <= 0:
            return 0
        cutoff = time.monotonic() - self._retention_s
        terminal = (OCRJobStatus.COMPLETE, OCRJobStatus.ERROR)
        # Phase 1: materialise eligible ``job_id`` values. Python dicts raise
        # ``RuntimeError: dictionary changed size during iteration`` if we
        # mutate during the loop, so collect first and drop later.
        stale_ids: list[str] = []
        for job_id, record in self._records.items():
            if record.status not in terminal:
                continue
            completed_at = record.completed_at
            if completed_at is None or completed_at >= cutoff:
                continue
            stale_ids.append(job_id)
        # Phase 2: evict. ``pop`` with a default tolerates a concurrent
        # ``cancel`` having already removed the entry.
        for job_id in stale_ids:
            self._records.pop(job_id, None)
        return len(stale_ids)

    async def cancel(self, job_id: str) -> OCRJobRecord | None:
        """Mark a job as cancelled.

        For ``PENDING`` jobs the record is removed so the worker drops
        it the next time it pops from the queue. For ``PROCESSING``
        jobs the running pipeline cannot be interrupted safely here
        (the worker is owned by the asyncio task doing the work), so
        we mark the record as ``ERROR`` with a clear message and let
        the worker finish; the record already carries the cancellation
        signal so the client sees a stable terminal state.
        Returns the updated record, or ``None`` if the job is unknown.
        """
        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            if record.status in (OCRJobStatus.COMPLETE, OCRJobStatus.ERROR):
                return record
            if record.status is OCRJobStatus.PENDING:
                # Drop the queue entry by removing the runner; the
                # worker wakes, finds no runner, and skips the job.
                self._runners.pop(job_id, None)
                self._records.pop(job_id, None)
                return record
            record.status = OCRJobStatus.ERROR
            record.error = "cancelled by client"
            record.completed_at = time.monotonic()
            if record.started_at is not None:
                record.duration_s = record.completed_at - record.started_at
            return record

    async def _worker_loop(self) -> None:
        """Drain the queue forever; the queue is unbounded by the caller."""
        while True:
            job_id = await self._queue.get()
            try:
                async with self._lock:
                    record = self._records.get(job_id)
                    runner = self._runners.pop(job_id, None)
                if record is None or runner is None:
                    # Already cancelled or otherwise cleaned up.
                    continue
                record.status = OCRJobStatus.PROCESSING
                record.started_at = time.monotonic()
                try:
                    result = await runner()
                    record.text_artifact_id = result.text_artifact_id
                    record.text_artifact_token = result.text_artifact_token
                    record.output_pdf_path = result.output_pdf_path
                    record.failed_pages = list(result.failed_pages)
                    # A concurrent cancellation marks the record ERROR while
                    # the runner winds down. Never overwrite that terminal state.
                    if record.status is OCRJobStatus.PROCESSING:
                        record.status = OCRJobStatus.COMPLETE
                except Exception as exc:
                    # Preserve a concurrent cancellation's terminal message.
                    # The runner is allowed to wind down, but neither success
                    # nor failure may replace "cancelled by client".
                    if record.status is OCRJobStatus.PROCESSING:
                        record.error = str(exc) or type(exc).__name__
                        record.status = OCRJobStatus.ERROR
                finally:
                    record.completed_at = time.monotonic()
                    if record.started_at is not None:
                        record.duration_s = record.completed_at - record.started_at
            finally:
                self._queue.task_done()


__all__ = [
    "DEFAULT_OCR_JOB_RETENTION_S",
    "OCRJobQueue",
    "OCRJobRecord",
    "OCRJobResult",
    "OCRJobRunner",
    "OCRJobStatus",
]
