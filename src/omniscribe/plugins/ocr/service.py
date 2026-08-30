"""OCR service implementation — bridges HTTP onto ``OCRPipeline``.

Audit catalog (Sprint 6 long-file split): separated from
``plugins/ocr/plugin.py`` so the plugin file is just the
Protocol + plugin class + route factory. The 280-LOC
``OCRServiceImpl`` + its private ``_OcrPayload`` + the SSE
event-formatting helper + the queue/event-name lookup tables
live here.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import tempfile
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from fastapi.responses import Response

from omniscribe.config import RuntimeSettings
from omniscribe.harness.events import Event
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.jobs import (
    JobCancelled,
    JobCompleted,
    JobFailed,
    JobOutcome,
    JobQueue,
    JobQueued,
    JobStarted,
)
from omniscribe.plugins.ocr.pipeline_bridge import build_pipeline, run_pipeline
from omniscribe.plugins.ocr.schemas import (
    AsyncSubmitResponse,
    JobListItemResponse,
    JobStatusResponse,
    OCRRequest,
)
from omniscribe.plugins.progress import ProgressFrame, ProgressService
from omniscribe.plugins.state_backend import JobRecord
from omniscribe.utils.security import check_ssrf_target_sync

_HttpJobStatus = Literal["pending", "processing", "complete", "error"]

_QUEUE_STATUS_TO_HTTP: dict[str, _HttpJobStatus] = {
    "queued": "pending",
    "running": "processing",
    "complete": "complete",
    "error": "error",
    "cancelled": "error",
}
_TERMINAL_QUEUE_STATUSES = {"complete", "error", "cancelled"}

_EVENT_NAMES: dict[type, str] = {
    JobQueued: "job_queued",
    JobStarted: "job_started",
    JobCompleted: "job_completed",
    JobFailed: "job_failed",
    JobCancelled: "job_cancelled",
    ProgressFrame: "progress",
}
_TERMINAL_EVENTS: tuple[type, ...] = (JobCompleted, JobFailed, JobCancelled)

SSE_KEEPALIVE_SECONDS = 15.0


@dataclass(frozen=True)
class _OcrPayload:
    """Everything the async worker needs for one queued upload."""

    submission_id: str
    file_bytes: bytes
    filename: str
    request: OCRRequest


def _seed_config(settings: RuntimeSettings) -> dict[str, Any]:
    """Initial ``/api/config`` store: LLM coordinates from settings, the
    rest at their historical workstation defaults."""
    return {
        "api_base": settings.llm_api_base,
        "api_key": settings.llm_api_key,
        "model": settings.llm_model,
        "concurrency": 3,
        "dpi": 192,
        "dense_mode": "auto",
        "dense_threshold": 150,
        "max_image_dim": 1024,
        "refine": True,
        "verify_model": True,
        "pipeline_mode": "hybrid",
        "self_correction": False,
        "binarize": False,
        "dual_engine": False,
        "spellcheck": "none",
        "cross_page": False,
        "preprocess_pages": False,
        "orientation_detection": False,
        "deskew": False,
        "denoise": False,
        "normalize_contrast": False,
        "crop_cleanup": False,
        "quality_routing": False,
        "document_processors": [],
    }


class OCRServiceImpl:
    """Concrete OCRService: bridges HTTP onto ``OCRPipeline``."""

    def __init__(
        self,
        settings: RuntimeSettings,
        queue: JobQueue,
        artifacts: ArtifactStore,
        *,
        progress: ProgressService | None,
        max_upload_mb: int,
        quality_defaults: Mapping[str, bool | float | int] | None = None,
        max_buffered_jobs: int = 500,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._artifacts = artifacts
        self._progress = progress
        self._max_upload_mb = max_upload_mb
        # cordis.yml-seeded defaults for the quality repair loop; applied to
        # uploads whose form omits the corresponding field.
        self._quality_defaults: Mapping[str, bool | float | int] = (
            quality_defaults or {}
        )
        self._max_buffered_jobs = max_buffered_jobs
        self._submission_to_job: dict[str, str] = {}
        self._config: dict[str, Any] = _seed_config(settings)
        self._event_buffers: dict[str, deque[dict[str, Any]]] = {}
        self._event_notify: dict[str, asyncio.Event] = {}
        self._done_jobs: set[str] = set()

    # -- execution ------------------------------------------------------------

    async def run_sync(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> Response:
        pdf_bytes, pages_data = await self._execute(options, blob, filename, job_id="")
        text_handle = await self._artifacts.put(
            json.dumps(
                {str(idx): "\n".join(lines) for idx, lines in pages_data.items()}
            ).encode("utf-8"),
            content_type="application/json",
            owner_job_id="",
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "X-Text-Artifact-Id": text_handle.id,
                "X-Text-Artifact-Token": text_handle.token,
            },
        )

    async def submit(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> AsyncSubmitResponse:
        submission_id = secrets.token_hex(16)
        payload = _OcrPayload(
            submission_id=submission_id,
            file_bytes=blob,
            filename=filename,
            request=options,
        )
        handle = await self._queue.submit(
            payload,
            request_meta={
                "submission_id": submission_id,
                "filename": filename,
                "model": options.model or self._settings.llm_model,
                "pipeline_mode": options.pipeline_mode,
                "pages": options.pages,
            },
        )
        self._submission_to_job[submission_id] = handle.job_id
        while len(self._submission_to_job) > self._max_buffered_jobs:
            self._submission_to_job.pop(next(iter(self._submission_to_job)), None)
        return AsyncSubmitResponse(
            job_id=handle.job_id, status="pending", status_url=handle.status_url
        )

    async def run_job(self, payload: Any) -> JobOutcome:
        """The JobRunner the queue worker injects at claim time."""
        if not isinstance(payload, _OcrPayload):
            raise ValueError("OCR job queue received a foreign payload")
        job_id = self._submission_to_job.get(payload.submission_id, "")
        pdf_bytes, _ = await self._execute(
            payload.request, payload.file_bytes, payload.filename, job_id=job_id
        )
        return JobOutcome(blob=pdf_bytes, content_type="application/pdf")

    async def _execute(
        self,
        options: OCRRequest,
        blob: bytes,
        filename: str,
        *,
        job_id: str,
    ) -> tuple[bytes, dict[int, list[str]]]:
        work_dir = Path(tempfile.mkdtemp(prefix="omniscribe-ocr-"))
        input_path = work_dir / f"input{Path(filename).suffix or '.pdf'}"
        output_path = work_dir / "output.pdf"
        try:
            input_path.write_bytes(blob)
            channel = options.progress_channel
            pipeline = build_pipeline(self._settings, options)
            pages_data = await run_pipeline(
                pipeline,
                settings=self._settings,
                request=options,
                input_path=str(input_path),
                output_path=str(output_path),
                on_progress=self._progress_adapter(job_id, channel),
                on_warning=self._warning_adapter(job_id, channel),
                cancel_check=self._cancel_check(job_id, channel),
            )
            return output_path.read_bytes(), pages_data
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _progress_adapter(self, job_id: str, channel: str | None):
        if self._progress is None or not channel:
            return None

        async def on_progress(percent: int, stage: str, message: str) -> None:
            assert self._progress is not None
            # Legacy progress frame shape: no ``type`` discriminator.
            await self._progress.emit_progress(
                job_id,
                channel,
                {"status": message, "percent": percent, "stage": stage},
            )

        return on_progress

    def _warning_adapter(self, job_id: str, channel: str | None):
        if self._progress is None or not channel:
            return None

        async def on_warning(text: str) -> None:
            assert self._progress is not None
            await self._progress.emit_progress(
                job_id,
                channel,
                {"status": text, "percent": 0, "stage": "warning", "warning": True},
            )

        return on_warning

    def _cancel_check(self, job_id: str, channel: str | None):
        if not job_id and not channel:
            return None
        queue, progress = self._queue, self._progress

        def check() -> bool:
            if job_id and queue.is_cancelled(job_id):
                return True
            return bool(
                channel and progress is not None and progress.is_cancelled(channel)
            )

        return check

    # -- job queries ------------------------------------------------------------

    async def job_record(self, job_id: str) -> JobRecord | None:
        return await self._queue.status(job_id)

    async def job_status(self, job_id: str) -> JobStatusResponse | None:
        record = await self._queue.status(job_id)
        if record is None:
            return None
        return self._status_response(record)

    def _status_response(self, record: JobRecord) -> JobStatusResponse:
        terminal = record.status in _TERMINAL_QUEUE_STATUSES
        error = record.error
        if record.status == "cancelled":
            error = error or "Job cancelled."
        # Security (2026-08-29 audit C-3 / H-3): the result token is NOT
        # returned here. The unauthenticated /api/process/status + /api/jobs
        # chain would otherwise bypass the constant-time gate at
        # fetch_result. The async client receives the token via the
        # ``job_completed`` SSE event payload (see _event_entry).
        return JobStatusResponse(
            job_id=record.job_id,
            filename=str(record.request_meta.get("filename", "")),
            status=_QUEUE_STATUS_TO_HTTP.get(record.status, "error"),
            created_at=record.created_at,
            started_at=None,
            completed_at=record.updated_at if terminal else None,
            duration_s=(record.updated_at - record.created_at) if terminal else None,
            error=error,
            text_artifact_id=record.result_artifact_id,
            failed_pages=[],
        )

    def job_list_item(self, record: JobRecord) -> JobListItemResponse:
        terminal = record.status in _TERMINAL_QUEUE_STATUSES
        meta = record.request_meta
        return JobListItemResponse(
            id=record.job_id,
            filename=str(meta.get("filename", "")),
            model=str(meta.get("model", "")),
            pipeline_mode=str(meta.get("pipeline_mode", "")),
            pages=meta.get("pages") if isinstance(meta.get("pages"), str) else None,
            duration_s=(record.updated_at - record.created_at) if terminal else 0.0,
            timestamp=datetime.fromtimestamp(record.created_at, tz=UTC).isoformat(),
            status=record.status,
            failed_pages=[],
        )

    async def fetch_result(self, job_id: str, token: str | None) -> Response:
        record = await self._queue.status(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if record.status != "complete":
            detail = (
                "job did not complete"
                if record.status in _TERMINAL_QUEUE_STATUSES
                else "job not complete yet"
            )
            raise HTTPException(status_code=409, detail=detail)
        expected = record.result_artifact_token or ""
        if not token or not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=403, detail="invalid result token")
        artifact = await self._artifacts.get(record.result_artifact_id or "", token)
        if artifact is None:
            raise HTTPException(status_code=404, detail="result artifact missing")
        return Response(
            content=artifact.blob,
            media_type=artifact.record.content_type or "application/pdf",
        )

    async def cancel_job(self, job_id: str) -> bool | None:
        """Returns None for unknown jobs, else the queue's cancel outcome."""
        if await self._queue.status(job_id) is None:
            return None
        return await self._queue.cancel(job_id)

    # -- config store -------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        cfg = dict(self._config)
        key = str(cfg.get("api_key", "") or "")
        if key and key != "lm-studio":
            cfg["api_key"] = "******"
        return cfg

    def update_config(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        if "api_base" in updates and updates["api_base"] is not None:
            new_base = str(updates["api_base"]).strip()
            if new_base:
                check = check_ssrf_target_sync(new_base)
                if not check.allowed:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid api_base URL (SSRF blocked: {check.reason})",
                    )
        for key, value in updates.items():
            if value is None or key not in self._config:
                continue
            if key == "api_key" and value == "******":
                continue
            self._config[key] = value
        # LLM coordinates write through to settings so the pipeline bridge
        # and the providers plugin observe the same active provider.
        self._settings.llm_api_base = str(self._config["api_base"])
        self._settings.llm_api_key = str(self._config["api_key"])
        self._settings.llm_model = str(self._config["model"])
        return self.get_config()

    # -- SSE replay -----------------------------------------------------------------

    async def record_event(self, event: Event) -> None:
        job_id = getattr(event, "job_id", "")
        if not job_id:
            return
        entry = event_entry(event)
        self._event_buffers.setdefault(job_id, deque(maxlen=500)).append(entry)
        if type(event) in _TERMINAL_EVENTS:
            self._done_jobs.add(job_id)
        self._event_notify.setdefault(job_id, asyncio.Event()).set()
        self._prune_events_if_needed()

    def _prune_events_if_needed(self) -> None:
        """Keep event buffers and done job sets bounded to _max_buffered_jobs."""
        while len(self._event_buffers) > self._max_buffered_jobs:
            oldest = next(iter(self._event_buffers))
            self._event_buffers.pop(oldest, None)
            self._event_notify.pop(oldest, None)
            self._done_jobs.discard(oldest)

        if len(self._done_jobs) > self._max_buffered_jobs:
            excess = set(self._done_jobs) - set(self._event_buffers)
            for jid in excess:
                self._done_jobs.discard(jid)
            while len(self._done_jobs) > self._max_buffered_jobs:
                self._done_jobs.pop()

    def prune(self, max_buffered_jobs: int | None = None) -> int:
        """Explicitly prune event buffers and done jobs to the specified limit.

        Returns the number of pruned job buffers.
        """
        limit = (
            self._max_buffered_jobs if max_buffered_jobs is None else max_buffered_jobs
        )
        initial_count = len(self._event_buffers)
        while len(self._event_buffers) > limit:
            oldest = next(iter(self._event_buffers))
            self._event_buffers.pop(oldest, None)
            self._event_notify.pop(oldest, None)
            self._done_jobs.discard(oldest)
        while len(self._submission_to_job) > limit:
            self._submission_to_job.pop(next(iter(self._submission_to_job)), None)
        if len(self._done_jobs) > limit:
            excess = set(self._done_jobs) - set(self._event_buffers)
            for jid in excess:
                self._done_jobs.discard(jid)
            while len(self._done_jobs) > limit:
                self._done_jobs.pop()
        return initial_count - len(self._event_buffers)

    def event_backlog(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._event_buffers.get(job_id, ()))

    def is_done(self, job_id: str) -> bool:
        return job_id in self._done_jobs

    async def wait_for_events(self, job_id: str) -> None:
        notify = self._event_notify.setdefault(job_id, asyncio.Event())
        await notify.wait()
        notify.clear()


def event_entry(event: Event) -> dict[str, Any]:
    """Format one job / progress event for the SSE stream.

    Public helper (no leading underscore) so the route factory in
    ``plugin.py`` can call it without depending on a private symbol.
    """
    data: dict[str, Any] = {"job_id": getattr(event, "job_id", "")}
    if isinstance(event, JobCompleted):
        # The async client uses ``artifact_token`` to authorize the
        # result download (this is the out-of-band channel that pairs
        # with the sync path's ``X-Text-Artifact-Token`` response header).
        data["artifact_id"] = event.artifact_id
        data["artifact_token"] = event.artifact_token
    elif isinstance(event, JobFailed):
        data["error"] = event.error
    elif isinstance(event, ProgressFrame):
        data.update(event.frame)
    return {
        "event": _EVENT_NAMES.get(type(event), type(event).__name__),
        "data": data,
    }


__all__ = [
    "SSE_KEEPALIVE_SECONDS",
    "OCRServiceImpl",
    "event_entry",
]
