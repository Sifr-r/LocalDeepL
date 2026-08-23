"""OCR upload + synchronous AI routes (``POST /api/process``).

After the god-module decomposition, this router is focused on
**orchestration**: validate the request, build the pipeline, run it,
build the response, record the job. Each of those steps is a single
call into one of the services next to this module:

- :mod:`omniscribe.api.services.ocr.settings` — form-parameter resolution
- :mod:`omniscribe.api.services.ocr.pipeline_factory` — pipeline + callback assembly
- :mod:`omniscribe.api.services.ocr.response` — response headers + FileResponse
- :mod:`omniscribe.api.services.ocr.execution` — pipeline-execution
  internals (job recording, audit emits, the thread-bridged runner)

What stays here: the ``@router.post(...)`` handlers (FastAPI binds
them to routes). The execution helpers are re-imported below so the
route handlers — and callers/tests that patch or import them through
this module — keep resolving them from ``omniscribe.api.routers.ocr``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe.api.routers import state
from omniscribe.api.routers.config import _config
from omniscribe.api.routers.websocket import manager
from omniscribe.api.services.helpers import (
    cleanup_files_dispatcher,
    stable_server_error,
)
from omniscribe.api.services.ocr.execution import (
    _create_document_metadata_artifact,  # noqa: F401 — re-export: lazy-imported by services/ocr/chunked_runner
    _emit_job_started,
    _emit_job_submitted,
    _execute_ocr_pipeline,
    _record_job,
    _run_ocr_pipeline,  # noqa: F401 — re-export: patched/imported via this module by tests and chunked_runner
    stage_to_percent,  # noqa: F401 — re-export: tests call ``routers.ocr.stage_to_percent``
)
from omniscribe.api.services.ocr.jobs import OCRJobResult
from omniscribe.api.services.ocr.response import (
    _validation_error_response,
    build_ocr_file_response,
)
from omniscribe.api.services.ocr.settings import (
    OCRProcessForm,
    collect_form_kwargs,
    resolve_process_settings,
)
from omniscribe.api.services.uploads import (
    SAFE_API_BASE_ERROR,
    UploadValidationError,
    api_error_response,
    save_validated_upload,
)
from omniscribe.core.workflows.base import OCRCancelled
from omniscribe.utils import is_ssrf_target

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process")
async def process_pdf(
    file: UploadFile = File(...),
    form: OCRProcessForm = Depends(OCRProcessForm),
):
    """Process a PDF or image file through the OCR pipeline.

    Every optional parameter falls back to the in-memory config store
    when not supplied by the caller.

    The OCR work is dispatched to a worker thread via
    :func:`asyncio.to_thread` so this route does not block the uvicorn
    event loop while the pipeline runs. For long-running jobs, prefer
    :func:`process_pdf_async` (``POST /api/process/async``) which returns
    a ``job_id`` immediately and lets the client poll
    :func:`process_status` for completion.
    """
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=form.pages,
            **collect_form_kwargs(form),
        )
    except ValidationError as exc:
        return _validation_error_response(exc)

    if not (await is_ssrf_target(settings.api_base)).allowed:
        return api_error_response(HTTPStatus.FORBIDDEN, SAFE_API_BASE_ERROR)

    try:
        upload = await save_validated_upload(file)
    except UploadValidationError as exc:
        return api_error_response(exc.status_code, str(exc))

    input_path = upload.path
    progress_target = (
        form.progress_channel
        if manager.is_authorized(form.progress_channel, form.progress_token)
        else None
    )
    output_path = os.path.join(tempfile.gettempdir(), f"output_{uuid.uuid4()}.pdf")
    text_path: str | None = None
    # Phase 3c — the canonical job id is the UUID hex we mint here.
    # It stays the same across submitted/started/completed log events
    # (so the ``JobHistoryProjection`` can fold a complete record) and
    # is the id we pass to ``_record_job(log_job_id=...)``. The legacy
    # ``JobHistory`` record below still uses the artifact id as its
    # ``id`` field for backward compatibility with the existing
    # ``/api/jobs`` shape (the frontend only displays the value as
    # text — no logic depends on the choice).
    canonical_job_id = uuid.uuid4().hex
    legacy_job_id_holder: dict[str, str] = {}  # populated after pipeline run
    _emit_job_submitted(canonical_job_id, file.filename or "unknown")
    t_start = time.monotonic()

    try:
        await manager.send_progress(progress_target, "Initializing...", 5, stage="init")
        _emit_job_started(
            canonical_job_id,
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
        )

        (
            pipeline,
            artifact_handle,
            metadata_handle,
            text_path,
            failed_pages,
        ) = await _execute_ocr_pipeline(
            settings=settings,
            input_path=input_path,
            output_path=output_path,
            progress_target=progress_target,
        )
        legacy_job_id_holder["id"] = artifact_handle.artifact_id

        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=legacy_job_id_holder["id"],
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="complete",
            failed_pages=failed_pages,
            log_job_id=canonical_job_id,
            text_artifact_id=artifact_handle.artifact_id,
        )

        if failed_pages:
            await manager.send_progress(
                progress_target,
                f"Completed with {len(failed_pages)} page failure(s).",
                100,
                stage="complete",
            )
        else:
            await manager.send_progress(
                progress_target,
                "Done! Preparing download...",
                100,
                stage="complete",
            )

        return build_ocr_file_response(
            pipeline=pipeline,
            settings=settings,
            output_path=output_path,
            input_path=input_path,
            artifact_handle=artifact_handle,
            metadata_handle=metadata_handle,
            cleanup_callback=cleanup_files_dispatcher,
            filename=file.filename or "unknown",
            failed_pages=failed_pages,
        )

    except ValueError as ve:
        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=legacy_job_id_holder.get("id", canonical_job_id),
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
            log_job_id=canonical_job_id,
            error=str(ve),
        )
        logger.warning("OCR processing rejected invalid input: %s", ve)
        await manager.send_progress(progress_target, "Invalid input.", 0, stage="error")
        await asyncio.to_thread(
            cleanup_files_dispatcher, input_path, output_path, text_path
        )
        return api_error_response(
            HTTPStatus.BAD_REQUEST, "Invalid input.", detail=str(ve)
        )

    except asyncio.CancelledError:
        logger.info("OCR request cancelled by client: job_id=%s", canonical_job_id)
        await asyncio.to_thread(
            cleanup_files_dispatcher, input_path, output_path, text_path
        )
        raise

    except OCRCancelled:
        # Phase 3 fix (report §2.1) — the engine raised
        # :class:`OCRCancelled` from inside the per-page OCR loop
        # because the WebSocket cancel channel fired. Translate it
        # into a 503 Service Unavailable with ``cancelled: true``
        # so the client can distinguish a user-initiated cancel
        # from a 500 server error. We intentionally do NOT record
        # a JobHistory entry on cancel: the in-memory ``JobStatus``
        # schema (Literal["complete", "error", "rejected"]) is
        # wider than the current API surface and adding a new
        # value would force every consumer to special-case it.
        # The cancel shows up in the application log instead.
        # Phase 3c — the projection still needs a marker so a future
        # ``/api/jobs`` view (driven by the log, not the deque) can
        # show the cancel. Emit ``ocr.job.cancelled`` so the
        # ``JobHistoryProjection`` can fold it; the legacy deque is
        # intentionally untouched.
        try:
            from omniscribe.api.plugin.events_catalog import JobCancelledEvent
            from omniscribe.api.plugin.runtime import get_plugin_context

            ctx = get_plugin_context()
            if ctx is not None:
                ctx.emit(
                    "ocr.job.cancelled",
                    **JobCancelledEvent(job_id=canonical_job_id).__dict__,
                )
        except Exception:
            logger.exception(
                "audit: failed to emit JobCancelledEvent for job_id=%s",
                canonical_job_id,
            )
        logger.info(
            "OCR run cancelled by client before completion: job_id=%s",
            canonical_job_id,
        )
        await asyncio.to_thread(
            cleanup_files_dispatcher, input_path, output_path, text_path
        )
        await manager.send_progress(progress_target, "Cancelled.", 0, stage="cancelled")
        return JSONResponse(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            content={
                "cancelled": True,
                "error": "OCR run was cancelled before completion.",
            },
        )

    except Exception as exc:
        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=legacy_job_id_holder.get("id", canonical_job_id),
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
            log_job_id=canonical_job_id,
            error=str(exc) or type(exc).__name__,
        )
        logger.exception("OCR processing failed")
        await manager.send_progress(
            progress_target, "Processing failed.", 0, stage="error"
        )
        await asyncio.to_thread(
            cleanup_files_dispatcher, input_path, output_path, text_path
        )
        return stable_server_error()


@router.post("/process/async", status_code=202)
async def process_pdf_async(
    file: UploadFile = File(...),
    form: OCRProcessForm = Depends(OCRProcessForm),
):
    """Validate an upload and enqueue it on the single-worker OCR queue."""
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=form.pages,
            **collect_form_kwargs(form),
        )
    except ValidationError as exc:
        return _validation_error_response(exc)

    if not (await is_ssrf_target(settings.api_base)).allowed:
        return api_error_response(HTTPStatus.FORBIDDEN, SAFE_API_BASE_ERROR)

    try:
        upload = await save_validated_upload(file)
    except UploadValidationError as exc:
        return api_error_response(exc.status_code, str(exc))

    input_path = upload.path
    filename = file.filename or "unknown"
    progress_target = (
        form.progress_channel
        if manager.is_authorized(form.progress_channel, form.progress_token)
        else None
    )
    output_path = os.path.join(tempfile.gettempdir(), f"output_{uuid.uuid4()}.pdf")
    job_id = uuid.uuid4().hex

    from omniscribe.api.services.state.redis import RedisStateBackend

    is_redis_mode = isinstance(state.backend, RedisStateBackend)
    if is_redis_mode:
        from omniscribe.api.tasks import process_ocr_task

        process_ocr_task.delay(
            job_id,
            input_path,
            settings.model_dump(),
            progress_target,
            form.progress_token,
        )
        _emit_job_submitted(job_id, filename)
        return {"job_id": job_id, "status": "pending"}

    async def runner() -> OCRJobResult:
        text_path: str | None = None
        succeeded = False
        started_at = time.monotonic()
        try:
            await manager.send_progress(
                progress_target, "Initializing...", 5, stage="init"
            )
            # Phase 3c — emit JobStartedEvent when the worker actually
            # picks the job up (not at submit time; the queue may have
            # backed up). The JobHistoryProjection needs this for
            # model + pipeline_mode + pages.
            _emit_job_started(
                job_id,
                model=settings.model,
                pipeline_mode=settings.pipeline_mode,
                pages=settings.pages,
            )
            (
                _pipeline,
                artifact_handle,
                _metadata_handle,
                text_path,
                failed_pages,
            ) = await _execute_ocr_pipeline(
                settings=settings,
                input_path=input_path,
                output_path=output_path,
                progress_target=progress_target,
            )
            _record_job(
                job_id=job_id,
                filename=filename,
                model=settings.model,
                pipeline_mode=settings.pipeline_mode,
                pages=settings.pages,
                duration_s=time.monotonic() - started_at,
                status="complete",
                failed_pages=failed_pages,
                text_artifact_id=artifact_handle.artifact_id,
            )
            await manager.send_progress(progress_target, "Done!", 100, stage="complete")
            succeeded = True
            return OCRJobResult(
                text_artifact_id=artifact_handle.artifact_id,
                text_artifact_token=artifact_handle.token,
                output_pdf_path=output_path,
                failed_pages=failed_pages,
            )
        except OCRCancelled:
            # Phase 3 fix (report §2.1) — same as the sync route:
            # the engine raised :class:`OCRCancelled` because the
            # WebSocket cancel channel fired. Log it, do NOT
            # record a job history entry (the JobStatus Literal
            # doesn't include "cancelled"), and re-raise so the
            # queue worker surfaces the failure to the polling
            # client. ``cleanup_files_dispatcher`` runs in the ``finally`` block
            # below and drops the input/output/text paths.
            # Phase 3c — emit the cancelled event for the projection.
            try:
                from omniscribe.api.plugin.events_catalog import JobCancelledEvent
                from omniscribe.api.plugin.runtime import get_plugin_context

                ctx = get_plugin_context()
                if ctx is not None:
                    ctx.emit(
                        "ocr.job.cancelled",
                        **JobCancelledEvent(job_id=job_id).__dict__,
                    )
            except Exception:
                logger.exception(
                    "audit: failed to emit JobCancelledEvent for job_id=%s", job_id
                )
            logger.info("Async OCR run cancelled by client: job_id=%s", job_id)
            await manager.send_progress(
                progress_target, "Cancelled.", 0, stage="cancelled"
            )
            raise
        except Exception as exc:
            _record_job(
                job_id=job_id,
                filename=filename,
                model=settings.model,
                pipeline_mode=settings.pipeline_mode,
                pages=settings.pages,
                duration_s=time.monotonic() - started_at,
                status="error",
                error=str(exc) or type(exc).__name__,
            )
            raise
        finally:
            cleanup_paths = (
                (input_path,) if succeeded else (input_path, output_path, text_path)
            )
            await asyncio.to_thread(cleanup_files_dispatcher, *cleanup_paths)

    await state.ocr_job_queue.submit(job_id, filename, runner)
    # Phase 2 + 3c: emit the audit event through the plugin context so
    # the mounted recorders (default: log) observe the submission. The
    # legacy code path is unchanged; the emit is a side effect.
    _emit_job_submitted(job_id, filename)
    return {"job_id": job_id, "status": "pending"}


@router.get("/process/status/{job_id}")
async def process_status(job_id: str):
    """Return the current state of a queued background OCR job."""
    record = await state.ocr_job_queue.get(job_id)
    if record is not None:
        return record.to_dict()

    for job in state.job_history.list():
        if job.get("id") == job_id or job.get("job_id") == job_id:
            return job

    try:
        from omniscribe.api.celery_app import celery_app
        from omniscribe.core.translate.config import AsyncTranslationUnavailable

        task = celery_app.AsyncResult(job_id)
        if task is not None and getattr(task, "state", None):
            res: dict[str, Any] = {
                "job_id": job_id,
                "status": (
                    task.state.lower()
                    if isinstance(task.state, str)
                    else str(task.state)
                ),
            }
            if (
                task.state == "SUCCESS"
                and hasattr(task, "result")
                and isinstance(task.result, dict)
            ):
                res.update(task.result)
            elif task.state == "FAILURE" and hasattr(task, "info"):
                res["error"] = str(task.info)
            elif hasattr(task, "info") and isinstance(task.info, dict):
                res.update(task.info)
            return res
    except (AsyncTranslationUnavailable, Exception):
        pass

    return api_error_response(HTTPStatus.NOT_FOUND, "Job not found")


# Canonical namespaced routes for the Svelte UI. The prefix-less forms remain
# available for existing integrations and route to the same handler objects.
router.add_api_route("/api/process", process_pdf, methods=["POST"])
router.add_api_route(
    "/api/process/async", process_pdf_async, methods=["POST"], status_code=202
)
router.add_api_route("/api/process/status/{job_id}", process_status, methods=["GET"])
