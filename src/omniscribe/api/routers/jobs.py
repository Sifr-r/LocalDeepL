import asyncio
import os
import secrets
from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from omniscribe.api.plugin import JobQueue
from omniscribe.api.plugin.runtime import (
    PLUGIN_CONTEXT_ENABLED,
    get_plugin_context,
)
from omniscribe.api.routers import state
from omniscribe.api.routers.common import get_access_token
from omniscribe.api.services.ocr_jobs import OCRJobStatus

router = APIRouter()


def _result_download_filename(filename: str | None, job_id: str) -> str:
    """Build a Content-Disposition filename from the record's source filename.

    Strips the trailing ``.pdf`` (and any other extension) so the
    resulting ``{name}.ocr.pdf`` is unambiguous. Falls back to the
    ``job_id`` when the record has no filename (manual submissions,
    tests).
    """
    if not filename:
        return f"{job_id}.ocr.pdf"
    stem = Path(filename).stem or job_id
    return f"{stem}.ocr.pdf"


def _get_job_queue():
    """Return the OCR job queue, honouring the OMNISCRIBE_PLUGIN_CONTEXT flag.

    When the flag is on AND a live plugin context is available, the
    :class:`JobQueue` provider registered in the context is used. In all
    other cases the legacy ``state.ocr_job_queue`` singleton is
    returned. The two paths share the same underlying instance during
    the migration window because :func:`omniscribe.api.server.create_app`
    registers ``state.ocr_job_queue`` into the context.
    """
    if PLUGIN_CONTEXT_ENABLED:
        ctx = get_plugin_context()
        if ctx is not None and ctx.has(JobQueue):
            return ctx.get(JobQueue)
    return state.ocr_job_queue


@router.get("/api/jobs")
async def get_jobs():
    """Return the recent job history (newest first)."""
    return state.job_history.list()


@router.delete("/api/jobs")
async def clear_jobs():
    """Clear recent job history and current text artifacts."""
    await asyncio.to_thread(state.text_artifacts.clear)
    state.job_history.clear()
    return {"status": "ok"}


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a queued or running background OCR job."""
    record = await _get_job_queue().cancel(job_id)
    if record is None:
        return JSONResponse(
            status_code=HTTPStatus.NOT_FOUND, content={"error": "Job not found"}
        )
    return {"status": "cancelled", "job_id": job_id}


@router.get("/api/jobs/{job_id}/result")
async def get_job_result(
    job_id: str,
    access_token: str | None = Depends(get_access_token),
):
    """Download the searchable PDF produced by a completed async OCR job.

    Authentication: the client must present the same opaque token that
    was returned alongside the job (``text_artifact_token`` from
    ``GET /api/process/status/{job_id}``). The token is checked via
    :func:`secrets.compare_digest` so a timing side-channel cannot
    leak the secret one byte at a time.

    Errors:

    - ``404`` if the job_id is unknown (e.g. never submitted, already
      evicted by the 24h retention sweeper, or processed on a
      different uvicorn worker in a multi-worker deployment).
    - ``409`` if the job exists but is still pending/processing, or
      finished with an error status (no PDF was produced).
    - ``403`` if the access token is missing or does not match the
      record's ``text_artifact_token`` constant-time.
    - ``410`` if the job completed successfully but the underlying
      output file has been removed from disk (e.g. cleanup ran after
      the record was last refreshed).
    """
    record = await state.ocr_job_queue.get(job_id)
    if record is None:
        return JSONResponse(
            status_code=HTTPStatus.NOT_FOUND, content={"error": "Job not found"}
        )
    if record.status is not OCRJobStatus.COMPLETE:
        return JSONResponse(
            status_code=HTTPStatus.CONFLICT,
            content={
                "error": "Job is not complete",
                "status": record.status.value,
            },
        )
    expected_token = record.text_artifact_token
    if (
        not expected_token
        or not access_token
        or not secrets.compare_digest(expected_token, access_token)
    ):
        return JSONResponse(
            status_code=HTTPStatus.FORBIDDEN,
            content={"error": "Result access denied"},
        )
    output_path = record.output_pdf_path
    if not output_path or not await asyncio.to_thread(os.path.exists, output_path):
        return JSONResponse(
            status_code=HTTPStatus.GONE,
            content={"error": "Result file no longer available"},
        )
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=_result_download_filename(record.filename, job_id),
    )
