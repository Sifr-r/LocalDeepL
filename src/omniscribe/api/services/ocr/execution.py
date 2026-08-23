"""Pipeline-execution internals for the OCR process routes.

Extracted from ``omniscribe.api.routers.ocr`` so the router module
holds only route handlers.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import Sequence
from concurrent.futures import Future as ConcurrentFuture
from typing import cast

from omniscribe import OCRPipeline
from omniscribe.api.routers import state
from omniscribe.api.routers.config import _config
from omniscribe.api.routers.websocket import manager
from omniscribe.api.schemas import ProcessSettings
from omniscribe.api.services.artifacts import PageText, TextArtifactHandle
from omniscribe.api.services.document_metadata import (
    build_document_metadata_report,
    write_document_metadata_atomic,
)
from omniscribe.api.services.jobs import JobStatus
from omniscribe.api.services.ocr.chunked_runner import run_ocr_in_chunks
from omniscribe.api.services.ocr.pipeline_factory import (
    build_pipeline,
    verify_backend_model,
)
from omniscribe.core.imaging.page_preprocess import PagePreprocessingOptions
from omniscribe.core.ocr_quality.routing import QualityRoutingOptions
from omniscribe.core.workflows.repair import RepairOptions

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
