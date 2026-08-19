"""OCR upload + synchronous AI routes (``POST /api/process``).

After the god-module decomposition, this router is focused on
**orchestration**: validate the request, build the pipeline, run it,
build the response, record the job. Each of those steps is a single
call into one of the services next to this module:

- :mod:`omniscribe.api.services.ocr_settings` — form-parameter resolution
- :mod:`omniscribe.api.services.ocr_pipeline_factory` — pipeline + callback assembly
- :mod:`omniscribe.api.services.ocr_response` — response headers + FileResponse

What stays here:

- The ``@router.post(...)`` handlers (FastAPI binds them to routes).
- Job-history recording glue (short, single-call into ``state``).
- The ``stage → percent`` helper (one-line delegation to ``state.progress_service``).
- The doc-metadata artifact builder (small; keeping it inline avoids a 1-function service).
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import tempfile
import time
import uuid
from collections.abc import Sequence
from concurrent.futures import Future as ConcurrentFuture
from http import HTTPStatus
from typing import Any, cast

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe import OCRPipeline
from omniscribe.api.schemas import ProcessSettings
from omniscribe.api.services.artifacts import PageText, TextArtifactHandle
from omniscribe.api.services.document_metadata import (
    build_document_metadata_report,
    write_document_metadata_atomic,
)
from omniscribe.api.services.jobs import JobStatus
from omniscribe.api.services.ocr_chunked_runner import run_ocr_in_chunks
from omniscribe.api.services.ocr_jobs import OCRJobResult
from omniscribe.api.services.ocr_pipeline_factory import (
    build_pipeline,
    verify_backend_model,
)
from omniscribe.api.services.ocr_response import (
    _validation_error_response,
    build_ocr_file_response,
)
from omniscribe.api.services.ocr_settings import (
    collect_form_kwargs,
    resolve_process_settings,
)
from omniscribe.api.services.security import (
    SAFE_API_BASE_ERROR,
    UploadValidationError,
    api_error_response,
    save_validated_upload,
)
from omniscribe.core.preprocessing import PagePreprocessingOptions
from omniscribe.core.routing import QualityRoutingOptions
from omniscribe.core.workflows.base import OCRCancelled
from omniscribe.core.workflows.repair import RepairOptions
from omniscribe.utils import is_ssrf_target

from . import state
from .common import _cleanup, _stable_server_error
from .config import _config
from .websocket import manager

router = APIRouter()
logger = logging.getLogger(__name__)


async def _fire_and_forget_awaitable() -> None:
    """Empty coroutine returned by the thread-bridge progress callbacks.

    The OCR engine's :func:`omniscribe.core.workflows.base.notify` does
    ``await cb(...)`` so each ``progress`` / ``on_warning`` callback must
    return an awaitable. The thread-safe bridges in :func:`_run_ocr_pipeline`
    fire ``manager.send_progress`` onto the main loop and return this
    coroutine so the engine's ``await`` resolves immediately. That keeps the
    worker thread fully decoupled from the main loop's responsiveness — see
    refactor §3.1 in ``docs/superpowers/specs/deep_refactor_report.md``.
    """
    return None


async def _create_document_metadata_artifact(
    pipeline: OCRPipeline,
) -> TextArtifactHandle | None:
    """Persist the document-processor metadata report (if any) as a token-bound artifact."""
    report = build_document_metadata_report(
        getattr(pipeline, "last_document_result", None)
    )
    if report is None:
        return None

    artifact_id = state.metadata_artifacts.issue_id()
    token = state.metadata_artifacts.issue_token()
    path = await asyncio.to_thread(
        write_document_metadata_atomic,
        report,
        directory=state.metadata_artifacts.artifact_dir,
        artifact_id=artifact_id,
    )
    return state.metadata_artifacts.put(artifact_id=artifact_id, token=token, path=path)


def stage_to_percent(stage: str, current: int, total: int) -> int:
    """Map a pipeline stage + sub-progress into a 0-100 overall percent.

    Primary path (Phase 7): the :class:`ProgressService` seam via
    the plugin context. The legacy ``state.progress_service``
    singleton is the fallback for any code path that doesn't go
    through the context — the two paths share the same instance
    during the migration window.
    """
    from omniscribe.api.plugin.runtime import get_progress_service

    progress = get_progress_service()
    if progress is not None:
        return int(progress.stage_to_percent(stage, current, total))
    return int(state.progress_service.stage_to_percent(stage, current, total))


def _record_job(
    job_id: str,
    filename: str,
    model: str,
    pipeline_mode: str,
    pages: str | None,
    duration_s: float,
    status: JobStatus,
    failed_pages: Sequence[int] = (),
    *,
    log_job_id: str | None = None,
    text_artifact_id: str | None = None,
    error: str | None = None,
) -> None:
    """Append a validated job record to the capped in-memory history.

    ``failed_pages`` is the 0-indexed list of pages whose OCR call
    raised an exception that the pipeline caught at its per-page
    isolation boundary. Empty in the common case — the job history
    omits the field from the serialized record when it's empty so
    existing clients see the same shape as before.

    ``log_job_id`` is the canonical job identifier used for the audit
    log emit (Phase 3c). It defaults to ``job_id`` for the simple
    case (async path) but the sync path passes the UUID-hex job id
    while still recording the artifact id as the legacy ``JobRecord.id``
    — two stores, two id schemes, kept independent during the
    migration window.

    ``text_artifact_id`` and ``error`` flow into the
    :class:`JobCompletedEvent` payload so the Phase 3c projection has
    enough context to fold a complete record (the projection reads
    these from the audit event, not the legacy record).
    """
    state.job_history.record(
        job_id=job_id,
        filename=filename,
        model=model,
        pipeline_mode=pipeline_mode,
        pages=pages,
        duration_s=duration_s,
        status=status,
        failed_pages=failed_pages,
        text_artifact_id=text_artifact_id,
    )
    # Phase 3c: emit the completion audit event through the plugin
    # context. The log auto-records it via the session log fan-out
    # (Phase 3b); the audit recorder also observes it. Errors during
    # the emit are swallowed so a broken recorder never blocks the
    # job-history append.
    canonical_id = log_job_id or job_id
    try:
        from omniscribe.api.plugin.events_catalog import JobCompletedEvent
        from omniscribe.api.plugin.runtime import get_plugin_context

        ctx = get_plugin_context()
        if ctx is not None:
            ctx.emit(
                "ocr.job.completed",
                **JobCompletedEvent(
                    job_id=canonical_id,
                    filename=filename,
                    status=str(status),
                    duration_s=duration_s,
                    text_artifact_id=text_artifact_id,
                    error=error,
                    failed_pages=list(failed_pages) if failed_pages else [],
                ).__dict__,
            )
    except Exception:
        logger.exception(
            "audit: failed to emit JobCompletedEvent for job_id=%s", canonical_id
        )


def _emit_job_submitted(job_id: str, filename: str) -> None:
    """Phase 3c — emit a ``JobSubmittedEvent`` for the log.

    Mirrors the emit hooks already in :mod:`routers.jobs`. Errors
    are swallowed; a broken recorder must never block job submission.
    """
    try:
        from omniscribe.api.plugin.events_catalog import JobSubmittedEvent
        from omniscribe.api.plugin.runtime import get_plugin_context

        ctx = get_plugin_context()
        if ctx is not None:
            ctx.emit(
                "ocr.job.submitted",
                **JobSubmittedEvent(job_id=job_id, filename=filename).__dict__,
            )
    except Exception:
        logger.exception(
            "audit: failed to emit JobSubmittedEvent for job_id=%s", job_id
        )


def _emit_job_started(
    job_id: str,
    *,
    model: str,
    pipeline_mode: str,
    pages: str | None,
) -> None:
    """Phase 3c — emit a ``JobStartedEvent`` for the log.

    Fired when the worker actually picks the job up (sync path: right
    before the pipeline runs; async path: at the top of the queue
    worker's runner). Carries the per-request config (model,
    pipeline_mode, page-range) so the
    :class:`JobHistoryProjection` has enough context to fold a
    complete record. Errors swallowed for the same reason as the
    other emit helpers.
    """
    try:
        from omniscribe.api.plugin.events_catalog import JobStartedEvent
        from omniscribe.api.plugin.runtime import get_plugin_context

        ctx = get_plugin_context()
        if ctx is not None:
            ctx.emit(
                "ocr.job.started",
                **JobStartedEvent(
                    job_id=job_id,
                    model=model,
                    pipeline_mode=pipeline_mode,
                    pages=pages,
                ).__dict__,
            )
    except Exception:
        logger.exception("audit: failed to emit JobStartedEvent for job_id=%s", job_id)


async def _run_ocr_pipeline(
    *,
    settings: ProcessSettings,
    input_path: str,
    output_path: str,
    progress_target: str | None,
) -> tuple[
    OCRPipeline,
    TextArtifactHandle,
    TextArtifactHandle | None,
    str,
    list[int],
]:
    """Run the OCR pipeline against a single (chunk) input file.

    Returns ``(pipeline, artifact_handle, metadata_handle, text_path,
    failed_pages)`` so callers can decide how to surface the result
    (sync route builds a file response, chunked runner merges artifacts
    and emits per-chunk WS frames). No upload validation, file response,
    or job history — those live in :func:`process_pdf`.

    The ``await pipeline.run(...)`` call is wrapped in
    :func:`asyncio.to_thread` so the uvicorn event loop is released while
    the (CPU-bound) pipeline executes on a worker thread. Progress and
    warning callbacks are bridged to the main loop via
    :func:`asyncio.run_coroutine_threadsafe` so WebSocket frames still go
    out in the order the engine emits them. See refactor §3.1 in
    ``docs/superpowers/specs/deep_refactor_report.md``.

    Phase 3 fix (report §2.1) — the WebSocket cancel channel is wired
    into the engine via ``manager.is_cancelled(progress_target)``. The
    engine consults it between page boundaries and raises
    :class:`OCRCancelled` if the client cancelled. The bridge is built
    here (not in the worker thread) so the closure captures the live
    ``progress_target`` without a thread-local handoff.
    """
    pipeline, backend = build_pipeline(
        settings,
        progress_target=progress_target,
        manager_send_block=manager.send_block,
        manager_send_page_complete=manager.send_page_complete,
        manager_send_block_retry=manager.send_block_retry,
        manager_send_block_revised=manager.send_block_revised,
        manager_send_quality_summary=manager.send_quality_summary,
    )
    await verify_backend_model(
        backend,
        settings.model,
        verify_model=_config.get("verify_model", True),
    )

    # Capture the main loop so the worker thread can schedule WebSocket
    # frame sends on it. ``run_coroutine_threadsafe`` is the documented
    # cross-thread bridge for coroutines; the returned future is fire-
    # and-forget from the worker's perspective (see the warning below).
    main_loop = asyncio.get_running_loop()

    # Phase 3 fix (report §2.1) — the cancel callback runs on the
    # worker thread (inside ``pipeline.run``); ``manager.is_cancelled``
    # is a plain dict lookup on the main loop's WebSocket state, so
    # it's safe to call from any thread. We bind the channel id here
    # to keep the worker-thread closure free of late-binding bugs.
    cancel_channel = progress_target

    def _cancel_check() -> bool:
        return manager.is_cancelled(cancel_channel)

    def _log_threadsafe_future_error(fut: ConcurrentFuture) -> None:
        """Surface errors from fire-and-forget progress sends on the main loop.

        ``run_coroutine_threadsafe`` returns a concurrent.futures.Future
        that runs on the main loop. The worker thread does not await it
        (that would re-couple worker throughput to main-loop responsive-
        ness), so any exception raised by ``manager.send_progress`` would
        otherwise be silently swallowed. We attach a done-callback that
        runs on the main loop and logs via the module logger.
        """
        if fut.cancelled():
            return
        exc = fut.exception()
        if exc is not None:
            logger.warning("Progress frame failed on main loop: %s", exc)

    def _progress_bridge(stage, current, total, message):
        """Thread-safe progress callback (runs in the worker thread)."""
        fut = asyncio.run_coroutine_threadsafe(
            manager.send_progress(
                progress_target,
                message,
                stage_to_percent(stage, current, total),
                stage=stage,
            ),
            main_loop,
        )
        fut.add_done_callback(_log_threadsafe_future_error)
        return _fire_and_forget_awaitable()

    def _warning_bridge(page_index, exc):
        """Thread-safe warning callback (runs in the worker thread)."""
        # Include the full exception message, not just the class name, so
        # users can diagnose without opening the server log. Capped at
        # 500 chars to keep the WebSocket frame small.
        exc_msg = str(exc).strip() or "(no message)"
        if len(exc_msg) > 500:
            exc_msg = exc_msg[:497] + "..."
        warning_message = (
            f"OCR failed for page {page_index + 1}: {type(exc).__name__}: {exc_msg}"
        )
        fut = asyncio.run_coroutine_threadsafe(
            manager.send_progress(
                progress_target,
                warning_message,
                0,
                stage="ocr",
                warning=True,
            ),
            main_loop,
        )
        fut.add_done_callback(_log_threadsafe_future_error)
        return _fire_and_forget_awaitable()

    def _run_pipeline_in_thread() -> dict[int, list[str]]:
        """Sync entry point: drive the async ``pipeline.run`` in a fresh event loop.

        Lives on the worker thread started by :func:`asyncio.to_thread`.
        A fresh event loop is created via :func:`asyncio.run` because the
        worker thread has no loop of its own. The bridged callbacks above
        schedule the actual ``manager.send_progress`` coroutines on the
        captured ``main_loop`` and return immediately, so this worker
        thread never blocks waiting for the main loop.
        """
        return asyncio.run(
            pipeline.run(
                input_path,
                output_path,
                dpi=settings.dpi,
                pages=settings.pages,
                concurrency=settings.concurrency,
                refine=settings.refine,
                max_image_dim=settings.max_image_dim,
                dense_threshold=settings.dense_threshold,
                dense_mode=settings.dense_mode,
                self_correction=settings.self_correction,
                binarize=settings.binarize,
                dual_engine=settings.dual_engine,
                spellcheck=settings.spellcheck,
                cross_page=settings.cross_page,
                preprocessing_options=PagePreprocessingOptions(
                    enabled=settings.preprocess_pages,
                    orientation_detection=settings.orientation_detection,
                    deskew=settings.deskew,
                    denoise=settings.denoise,
                    normalize_contrast=settings.normalize_contrast,
                    crop_cleanup=settings.crop_cleanup,
                ),
                quality_routing_options=QualityRoutingOptions(
                    enabled=settings.quality_routing
                ),
                progress=_progress_bridge,
                on_warning=_warning_bridge,
                # Phase 2 — forward the configured model id to the trust
                # layer so :func:`omniscribe.core.ocr_quality.calibration.calibrate`
                # can pick the right per-model calibration JSON.
                trust_model_id=settings.model,
                # P1 — quality repair loop (spec §3.2). Built from the
                # resolved settings so form overrides and the env-seeded
                # config-store defaults both flow through; chunked runs
                # re-enter this helper per chunk and inherit the same
                # options.
                repair_options=RepairOptions(
                    enabled=settings.quality_loop_enabled,
                    target=settings.quality_target,
                    max_retries=settings.quality_max_retries,
                ),
                # Phase 3 fix (report §2.1) — hand the cancel callback
                # to the engine so the per-page loop can short-circuit
                # a user-initiated cancel between page completions.
                cancel_check=_cancel_check,
            )
        )

    # ``asyncio.to_thread`` is *not* cancellable: the worker thread
    # keeps running until ``_run_pipeline_in_thread`` returns. The
    # ``cancel_check`` wired above lets the engine itself raise
    # :class:`OCRCancelled` on the next page boundary; the route
    # handler catches that and returns a 503 to the client.
    # The worker thread therefore stops within one page of the
    # cancel signal instead of running the full VLM spend.
    pages_text = await asyncio.to_thread(_run_pipeline_in_thread)

    failed_pages = list(pipeline.last_failed_pages)

    artifact_handle = await state.text_artifacts.create(cast(PageText, pages_text))
    text_path = artifact_handle.path

    doc_res = getattr(pipeline, "last_document_result", None)
    if doc_res and doc_res.tree:
        from omniscribe.api.services.tree_artifact import write_tree_atomic

        def _write_tree() -> None:
            write_tree_atomic(doc_res.tree, pathlib.Path(f"{text_path}.tree.json"))

        await asyncio.to_thread(_write_tree)

    metadata_handle = await _create_document_metadata_artifact(pipeline)
    return pipeline, artifact_handle, metadata_handle, text_path, failed_pages


async def _execute_ocr_pipeline(
    *,
    settings: ProcessSettings,
    input_path: str,
    output_path: str,
    progress_target: str | None,
):
    """Select single-shot or bounded-page OCR for an uploaded document."""
    if (
        settings.chunk_pages is not None
        and settings.pages is None
        and input_path.lower().endswith(".pdf")
    ):
        return await run_ocr_in_chunks(
            settings=settings,
            input_path=input_path,
            output_path=output_path,
            progress_target=progress_target,
            manager=manager,
            chunk_size=settings.chunk_pages,
        )
    return await _run_ocr_pipeline(
        settings=settings,
        input_path=input_path,
        output_path=output_path,
        progress_target=progress_target,
    )


@router.post("/process")
async def process_pdf(
    file: UploadFile = File(...),
    client_id: str | None = Form(None),  # accepted for backward compat
    progress_channel: str | None = Form(None),
    progress_token: str | None = Form(None),
    api_base: str | None = Form(None),
    api_key: str | None = Form(None),
    model: str | None = Form(None),
    pipeline_mode: str | None = Form(None),
    dpi: str | None = Form(None),
    concurrency: str | None = Form(None),
    dense_mode: str | None = Form(None),
    dense_threshold: str | None = Form(None),
    pages: str | None = Form(None),
    refine: str | None = Form(None),
    max_image_dim: str | None = Form(None),
    self_correction: str | None = Form(None),
    binarize: str | None = Form(None),
    dual_engine: str | None = Form(None),
    spellcheck: str | None = Form(None),
    cross_page: str | None = Form(None),
    preprocess_pages: str | None = Form(None),
    orientation_detection: str | None = Form(None),
    deskew: str | None = Form(None),
    denoise: str | None = Form(None),
    normalize_contrast: str | None = Form(None),
    crop_cleanup: str | None = Form(None),
    quality_routing: str | None = Form(None),
    document_processors: str | None = Form(None),
    handwriting_hint: str | None = Form(None),
    chunk_pages: str | None = Form(None),
    # Phase 2 — optional trust-layer configuration (JSON-encoded). When the
    # frontend's TrustPanel is open, the front-end posts a JSON object string
    # here; when closed, the field is omitted and the trust layer stays off.
    quality_options: str | None = Form(None),
    # P1 — quality repair loop knobs (spec §3.2). Omitted fields fall
    # back to the env-seeded runtime config; the API-level defaults
    # enable the loop (target 0.98, two repair passes).
    quality_loop_enabled: str | None = Form(None),
    quality_target: str | None = Form(None),
    quality_max_retries: str | None = Form(None),
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
            pages=pages,
            **collect_form_kwargs(
                api_base=api_base,
                api_key=api_key,
                model=model,
                pipeline_mode=pipeline_mode,
                dpi=dpi,
                concurrency=concurrency,
                dense_mode=dense_mode,
                dense_threshold=dense_threshold,
                refine=refine,
                max_image_dim=max_image_dim,
                self_correction=self_correction,
                binarize=binarize,
                dual_engine=dual_engine,
                spellcheck=spellcheck,
                cross_page=cross_page,
                preprocess_pages=preprocess_pages,
                orientation_detection=orientation_detection,
                deskew=deskew,
                denoise=denoise,
                normalize_contrast=normalize_contrast,
                crop_cleanup=crop_cleanup,
                quality_routing=quality_routing,
                document_processors=document_processors,
                handwriting_hint=handwriting_hint,
                # Phase 2 — trust-layer knob; the resolver passes this
                # through to ``ProcessSettings.quality_options``, where the
                # field validator parses it into ``OCrQualitySettings``.
                quality_options=quality_options,
                quality_loop_enabled=quality_loop_enabled,
                quality_target=quality_target,
                quality_max_retries=quality_max_retries,
            ),
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
        progress_channel
        if manager.is_authorized(progress_channel, progress_token)
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
            cleanup_callback=_cleanup,
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
        await asyncio.to_thread(_cleanup, input_path, output_path, text_path)
        return api_error_response(
            HTTPStatus.BAD_REQUEST, "Invalid input.", detail=str(ve)
        )

    except asyncio.CancelledError:
        logger.info("OCR request cancelled by client: job_id=%s", canonical_job_id)
        await asyncio.to_thread(_cleanup, input_path, output_path, text_path)
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
        await asyncio.to_thread(_cleanup, input_path, output_path, text_path)
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
        await asyncio.to_thread(_cleanup, input_path, output_path, text_path)
        return _stable_server_error()


@router.post("/process/async", status_code=202)
async def process_pdf_async(
    file: UploadFile = File(...),
    progress_channel: str | None = Form(None),
    progress_token: str | None = Form(None),
    api_base: str | None = Form(None),
    api_key: str | None = Form(None),
    model: str | None = Form(None),
    pipeline_mode: str | None = Form(None),
    dpi: str | None = Form(None),
    concurrency: str | None = Form(None),
    dense_mode: str | None = Form(None),
    dense_threshold: str | None = Form(None),
    pages: str | None = Form(None),
    refine: str | None = Form(None),
    max_image_dim: str | None = Form(None),
    self_correction: str | None = Form(None),
    binarize: str | None = Form(None),
    dual_engine: str | None = Form(None),
    spellcheck: str | None = Form(None),
    cross_page: str | None = Form(None),
    preprocess_pages: str | None = Form(None),
    orientation_detection: str | None = Form(None),
    deskew: str | None = Form(None),
    denoise: str | None = Form(None),
    normalize_contrast: str | None = Form(None),
    crop_cleanup: str | None = Form(None),
    quality_routing: str | None = Form(None),
    document_processors: str | None = Form(None),
    handwriting_hint: str | None = Form(None),
    chunk_pages: str | None = Form(None),
    # Phase 2 — optional trust-layer configuration (JSON-encoded). When the
    # frontend's TrustPanel is open, the front-end posts a JSON object string
    # here; when closed, the field is omitted and the trust layer stays off.
    quality_options: str | None = Form(None),
    # P1 — quality repair loop knobs (spec §3.2). Omitted fields fall
    # back to the env-seeded runtime config; the API-level defaults
    # enable the loop (target 0.98, two repair passes).
    quality_loop_enabled: str | None = Form(None),
    quality_target: str | None = Form(None),
    quality_max_retries: str | None = Form(None),
):
    """Validate an upload and enqueue it on the single-worker OCR queue."""
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=pages,
            **collect_form_kwargs(
                api_base=api_base,
                api_key=api_key,
                model=model,
                pipeline_mode=pipeline_mode,
                dpi=dpi,
                concurrency=concurrency,
                dense_mode=dense_mode,
                dense_threshold=dense_threshold,
                refine=refine,
                max_image_dim=max_image_dim,
                self_correction=self_correction,
                binarize=binarize,
                dual_engine=dual_engine,
                spellcheck=spellcheck,
                cross_page=cross_page,
                preprocess_pages=preprocess_pages,
                orientation_detection=orientation_detection,
                deskew=deskew,
                denoise=denoise,
                normalize_contrast=normalize_contrast,
                crop_cleanup=crop_cleanup,
                quality_routing=quality_routing,
                document_processors=document_processors,
                handwriting_hint=handwriting_hint,
                # Phase 2 — trust-layer knob; the resolver passes this
                # through to ``ProcessSettings.quality_options``, where the
                # field validator parses it into ``OCrQualitySettings``.
                quality_options=quality_options,
                quality_loop_enabled=quality_loop_enabled,
                quality_target=quality_target,
                quality_max_retries=quality_max_retries,
            ),
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
        progress_channel
        if manager.is_authorized(progress_channel, progress_token)
        else None
    )
    output_path = os.path.join(tempfile.gettempdir(), f"output_{uuid.uuid4()}.pdf")
    job_id = uuid.uuid4().hex

    from omniscribe.api.services.state_backend_redis import RedisStateBackend

    is_redis_mode = isinstance(state.backend, RedisStateBackend)
    if is_redis_mode:
        from omniscribe.api.tasks import process_ocr_task

        process_ocr_task.delay(
            job_id,
            input_path,
            settings.model_dump(),
            progress_target,
            progress_token,
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
            # client. ``_cleanup`` runs in the ``finally`` block
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
            await asyncio.to_thread(_cleanup, *cleanup_paths)

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
        from omniscribe.core.translation_config import AsyncTranslationUnavailable

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
