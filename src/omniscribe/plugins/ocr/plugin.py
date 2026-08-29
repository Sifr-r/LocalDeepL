"""OCR plugin — Protocol, route factory, plugin class.

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

Audit catalog (Sprint 6 long-file split): the 280-LOC
:file:`omniscribe.plugins.ocr.service` module now holds
``OCRServiceImpl`` + the SSE event-formatting helper + the
queue/event-name lookup tables. This file is just the
Protocol + plugin class + route factory.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.jobs import (
    JobCancelled,
    JobCompleted,
    JobFailed,
    JobQueue,
    JobQueued,
    JobRunner,
    JobStarted,
)
from omniscribe.plugins.ocr.schemas import (
    AsyncSubmitResponse,
    JobListItemResponse,
    JobStatusResponse,
    OCRRequest,
)
from omniscribe.plugins.progress import ProgressFrame, ProgressService

from .service import (
    SSE_KEEPALIVE_SECONDS,
    OCRServiceImpl,
)

_LOGGER = logging.getLogger("omniscribe.plugins.ocr")


@runtime_checkable
class OCRService(Protocol):
    """Sync/async OCR execution seam over the core pipeline."""

    async def run_sync(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> Response: ...

    async def submit(
        self, options: OCRRequest, blob: bytes, filename: str
    ) -> AsyncSubmitResponse: ...


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
                        timeout=SSE_KEEPALIVE_SECONDS,
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
    "build_ocr_router",
    "plugin",
]
