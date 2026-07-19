"""OCR upload + synchronous AI routes (``POST /api/process``).

After the god-module decomposition, this router is focused on
**orchestration**: validate the request, build the pipeline, run it,
build the response, record the job. Each of those steps is a single
call into one of the services next to this module:

- :mod:`local_deepl.api.services.ocr_settings` — form-parameter resolution
- :mod:`local_deepl.api.services.ocr_pipeline_factory` — pipeline + callback assembly
- :mod:`local_deepl.api.services.ocr_response` — response headers + FileResponse

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
from typing import cast

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from local_deepl import OCRPipeline
from local_deepl.api.services.artifacts import PageText, TextArtifactHandle
from local_deepl.api.services.document_metadata import (
    build_document_metadata_report,
    write_document_metadata_atomic,
)
from local_deepl.api.services.jobs import JobStatus
from local_deepl.api.services.ocr_pipeline_factory import (
    build_pipeline,
    verify_backend_model,
)
from local_deepl.api.services.ocr_response import (
    _validation_error_response,
    build_ocr_file_response,
)
from local_deepl.api.services.ocr_settings import resolve_process_settings
from local_deepl.api.services.security import (
    SAFE_API_BASE_ERROR,
    UploadValidationError,
    save_validated_upload,
)
from local_deepl.core.preprocessing import PagePreprocessingOptions
from local_deepl.core.routing import QualityRoutingOptions
from local_deepl.utils import is_ssrf_target

from . import state
from .common import _cleanup, _stable_server_error
from .config import _config
from .websocket import manager

router = APIRouter()
logger = logging.getLogger(__name__)


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
    """Map a pipeline stage + sub-progress into a 0-100 overall percent."""
    return state.progress_service.stage_to_percent(stage, current, total)


def _record_job(
    job_id: str,
    filename: str,
    model: str,
    pipeline_mode: str,
    pages: str | None,
    duration_s: float,
    status: JobStatus,
    failed_pages: Sequence[int] = (),
) -> None:
    """Append a validated job record to the capped in-memory history.

    ``failed_pages`` is the 0-indexed list of pages whose OCR call
    raised an exception that the pipeline caught at its per-page
    isolation boundary. Empty in the common case — the job history
    omits the field from the serialized record when it's empty so
    existing clients see the same shape as before.
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
):
    """Process a PDF or image file through the OCR pipeline.

    Every optional parameter falls back to the in-memory config store
    when not supplied by the caller.
    """
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=pages,
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
        )
    except ValidationError as exc:
        return _validation_error_response(exc)

    if await is_ssrf_target(settings.api_base):
        return JSONResponse(status_code=403, content={"error": SAFE_API_BASE_ERROR})

    try:
        upload = await save_validated_upload(file)
    except UploadValidationError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    input_path = upload.path
    progress_target = (
        progress_channel
        if manager.is_authorized(progress_channel, progress_token)
        else None
    )
    output_path = os.path.join(tempfile.gettempdir(), f"output_{uuid.uuid4()}.pdf")
    text_path: str | None = None
    job_id = uuid.uuid4().hex
    t_start = time.monotonic()

    try:
        await manager.send_progress(progress_target, "Initializing...", 5, stage="init")

        pipeline, backend = build_pipeline(
            settings,
            progress_target=progress_target,
            manager_send_block=manager.send_block,
            manager_send_page_complete=manager.send_page_complete,
        )
        await verify_backend_model(
            backend,
            settings.model,
            verify_model=_config.get("verify_model", True),
        )

        async def on_progress(stage, current, total, message):
            await manager.send_progress(
                progress_target,
                message,
                stage_to_percent(stage, current, total),
                stage=stage,
            )

        async def on_warning(page_index, exc):
            warning_message = (
                f"OCR failed for page {page_index + 1}: {type(exc).__name__}"
            )
            await manager.send_progress(
                progress_target,
                warning_message,
                0,
                stage="ocr",
                warning=True,
            )

        pages_text = await pipeline.run(
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
            progress=on_progress,
            on_warning=on_warning,
        )

        failed_pages = list(pipeline.last_failed_pages)

        artifact_handle = await asyncio.to_thread(
            state.text_artifacts.create, cast(PageText, pages_text)
        )
        text_path = artifact_handle.path

        doc_res = getattr(pipeline, "last_document_result", None)
        if doc_res and doc_res.tree:
            from local_deepl.api.services.tree_artifact import write_tree_atomic

            def _write_tree() -> None:
                write_tree_atomic(doc_res.tree, pathlib.Path(f"{text_path}.tree.json"))

            await asyncio.to_thread(_write_tree)

        metadata_handle = await _create_document_metadata_artifact(pipeline)
        job_id = artifact_handle.artifact_id

        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="complete",
            failed_pages=failed_pages,
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
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
        )
        logger.warning("OCR processing rejected invalid input: %s", ve)
        await manager.send_progress(progress_target, "Invalid input.", 0, stage="error")
        _cleanup(input_path, output_path, text_path)
        return JSONResponse(status_code=400, content={"error": "Invalid input."})

    except Exception:
        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=file.filename or "unknown",
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="error",
        )
        logger.exception("OCR processing failed")
        await manager.send_progress(
            progress_target, "Processing failed.", 0, stage="error"
        )
        _cleanup(input_path, output_path, text_path)
        return _stable_server_error()
