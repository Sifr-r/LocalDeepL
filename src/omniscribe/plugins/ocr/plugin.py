"""OCR plugin — sync/async process routes, job surface, config store.

Wraps :mod:`omniscribe.plugins.ocr.pipeline_bridge` behind an
:class:`OCRService` seam:

- ``POST /api/process`` — synchronous OCR; returns the searchable PDF blob
  with ``X-Text-Artifact-Id`` / ``X-Text-Artifact-Token`` headers.
- ``POST /api/process/async`` — enqueues onto the injected ``JobQueue`` and
  returns ``202`` + ``{job_id, status, status_url}``.
- Job status / list / clear / cancel / result download, SSE event stream,
  and the ``/api/config`` runtime config store (frontend ``ConfigResponse``
  shape — GET/POST, non-secret round-trip with LLM write-through).

The plugin also registers the :class:`JobRunner` the queue worker resolves
at claim time, and subscribes to the job/progress events so the SSE route
can replay them per job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import tempfile
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from omniscribe.config import RuntimeSettings
from omniscribe.harness.context import Context
from omniscribe.harness.events import Event
from omniscribe.harness.plugin import Plugin
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
from omniscribe.plugins.ocr.pipeline_bridge import build_pipeline, run_pipeline
from omniscribe.plugins.ocr.schemas import (
    AsyncSubmitResponse,
    JobListItemResponse,
    JobStatusResponse,
    OCRRequest,
)
from omniscribe.plugins.progress import ProgressFrame, ProgressService
from omniscribe.plugins.state_backend import JobRecord

_LOGGER = logging.getLogger("omniscribe.plugins.ocr")

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

_SSE_KEEPALIVE_SECONDS = 15.0


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


@runtime_checkable
class OCRService(Protocol):
    """Sync/async OCR execution seam over the core pipeline."""

    async def run_sync(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> Response: ...

    async def submit(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> AsyncSubmitResponse: ...


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
        entry = _event_entry(event)
        self._event_buffers.setdefault(job_id, deque(maxlen=500)).append(entry)
        if type(event) in _TERMINAL_EVENTS:
            self._done_jobs.add(job_id)
        self._event_notify.setdefault(job_id, asyncio.Event()).set()

    def event_backlog(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._event_buffers.get(job_id, ()))

    def is_done(self, job_id: str) -> bool:
        return job_id in self._done_jobs

    async def wait_for_events(self, job_id: str) -> None:
        notify = self._event_notify.setdefault(job_id, asyncio.Event())
        await notify.wait()
        notify.clear()


def _event_entry(event: Event) -> dict[str, Any]:
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


# -- routes -------------------------------------------------------------------


def build_ocr_router(service: OCRServiceImpl) -> APIRouter:
    """Every OCR-plugin route from the spec's route table."""
    router = APIRouter(tags=["ocr"])

    async def _parse_upload(
        request: Request,
    ) -> tuple[OCRRequest, bytes, str]:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="missing 'file' field")
        blob: bytes = await upload.read()
        cap = service._max_upload_mb * 1024 * 1024
        if len(blob) > cap:
            raise HTTPException(
                status_code=413,
                detail=f"upload exceeds {service._max_upload_mb} MB limit",
            )
        # H-5 audit fix: validate the upload's content type against
        # the allowlist. FastAPI's ``request.form()`` accepts the
        # multipart ``content_type`` field, which is the per-file
        # MIME type set by the client. We compare it to a
        # document-handler allowlist (PDF, PNG, JPEG, WebP, AVIF) and
        # reject anything else with 415.
        content_type = getattr(upload, "content_type", "") or ""
        allowed_types = {
            "application/pdf",
            "application/octet-stream",  # Flutter file picker fallback
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/avif",
        }
        if content_type and content_type not in allowed_types:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"unsupported content type: {content_type!r}. "
                    "Allowed: PDF, PNG, JPEG, WebP, AVIF."
                ),
            )
        # H-5 audit fix (continued): magic-byte check so a malicious
        # client cannot bypass the content-type filter by sending
        # ``application/octet-stream`` with PDF bytes (or vice-versa).
        # We check the first 8 bytes against the four common
        # signatures and let ``application/octet-stream`` through —
        # those uploads rely on the downstream pipeline's own
        # magic-byte sniffing (Pymupdf / Pillow) to detect format.
        if content_type and content_type != "application/octet-stream":
            head = blob[:8]
            magic_ok = (
                head.startswith(b"%PDF-")
                or head.startswith(b"\x89PNG\r\n\x1a\n")
                or head[:3] == b"\xff\xd8\xff"
                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
                or head.startswith(b"\x00\x00\x00\x1c")  # AVIF ftyp
            )
            if not magic_ok:
                raise HTTPException(
                    status_code=415,
                    detail=(
                        f"file contents do not match declared content type "
                        f"{content_type!r}"
                    ),
                )
        fields: dict[str, Any] = {
            key: value
            for key, value in form.items()
            if key != "file" and isinstance(value, str)
        }
        for key, value in service._quality_defaults.items():
            fields.setdefault(key, value)
        try:
            # model_validate (not **kwargs): form values are all strings and
            # the before-validators coerce them at runtime.
            options = OCRRequest.model_validate(fields)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        filename = str(getattr(upload, "filename", "") or "") or "upload.pdf"
        return options, blob, filename

    @router.post("/api/process")
    async def process_sync(request: Request) -> Response:
        options, blob, filename = await _parse_upload(request)
        return await service.run_sync(options, blob, filename)

    @router.post("/api/process/async", status_code=202)
    async def process_async(request: Request) -> AsyncSubmitResponse:
        options, blob, filename = await _parse_upload(request)
        return await service.submit(options, blob, filename)

    @router.get("/api/process/status/{job_id}")
    async def process_status(job_id: str) -> JobStatusResponse:
        status = await service.job_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return status

    @router.get("/api/process/{job_id}/events")
    async def process_events(job_id: str) -> StreamingResponse:
        if await service.job_record(job_id) is None and not service.event_backlog(
            job_id
        ):
            raise HTTPException(status_code=404, detail="unknown job")

        async def stream():
            cursor = 0
            while True:
                backlog = service.event_backlog(job_id)
                while cursor < len(backlog):
                    entry = backlog[cursor]
                    cursor += 1
                    yield (
                        f"event: {entry['event']}\n"
                        f"data: {json.dumps(entry['data'])}\n\n"
                    )
                if service.is_done(job_id):
                    return
                try:
                    await asyncio.wait_for(
                        service.wait_for_events(job_id),
                        timeout=_SSE_KEEPALIVE_SECONDS,
                    )
                except TimeoutError:
                    yield ": keep-alive\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.get("/api/jobs")
    async def list_jobs() -> list[JobListItemResponse]:
        records = await service._queue.list_jobs()
        return [service.job_list_item(record) for record in records]

    @router.delete("/api/jobs")
    async def clear_jobs() -> dict[str, Any]:
        cleared = await service._queue.clear()
        return {"status": "ok", "cleared": cleared}

    @router.get("/api/jobs/{job_id}/result")
    async def job_result(
        job_id: str,
        token: str | None = None,
        authorization: str | None = Header(default=None),
    ) -> Response:
        bearer = token
        if not bearer and authorization and authorization.startswith("Bearer "):
            bearer = authorization.removeprefix("Bearer ").strip()
        return await service.fetch_result(job_id, bearer)

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, bool]:
        outcome = await service.cancel_job(job_id)
        if outcome is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return {"cancelled": outcome}

    @router.get("/api/config")
    @router.get("/api/config/ocr")
    async def get_config() -> dict[str, Any]:
        return service.get_config()

    @router.post("/api/config")
    @router.put("/api/config/ocr")
    async def update_config(
        updates: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return service.update_config(updates)

    return router


# -- plugin ---------------------------------------------------------------------


class OCRSchema(BaseModel):
    max_upload_mb: int | None = None
    quality_loop_enabled: bool = True
    quality_target: float = Field(default=0.85, ge=0.5, le=1.0)
    quality_max_retries: int = Field(default=2, ge=0, le=5)


class OCRPlugin(Plugin):
    """Registers the OCR service, the queue runner, and the route surface."""

    Schema = OCRSchema

    async def apply(self, ctx: Context) -> None:
        from omniscribe.plugins.runtime import RuntimeService

        runtime = ctx.inject(RuntimeService)
        queue = ctx.inject(JobQueue)
        artifacts = ctx.inject(ArtifactStore)
        progress = ctx.inject(ProgressService) if ctx.has(ProgressService) else None
        configured = self.config.get("max_upload_mb")
        max_upload_mb = (
            int(configured) if configured else runtime.settings.max_upload_mb
        )
        schema = OCRSchema(**self.config)
        service = OCRServiceImpl(
            runtime.settings,
            queue,
            artifacts,
            progress=progress,
            max_upload_mb=max_upload_mb,
            quality_defaults={
                "quality_loop_enabled": schema.quality_loop_enabled,
                "quality_target": schema.quality_target,
                "quality_max_retries": schema.quality_max_retries,
            },
        )
        ctx.service(OCRService, service)
        ctx.service(JobRunner, service.run_job)
        for event_type in (
            JobQueued,
            JobStarted,
            JobCompleted,
            JobFailed,
            JobCancelled,
            ProgressFrame,
        ):
            ctx.on(event_type, service.record_event)
        ctx.mount_router(build_ocr_router(service))


plugin = OCRPlugin()


__all__ = [
    "OCRPlugin",
    "OCRSchema",
    "OCRService",
    "OCRServiceImpl",
    "build_ocr_router",
    "plugin",
]
