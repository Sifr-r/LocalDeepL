"""Response building for the OCR upload endpoint.

Extracted from ``api/routers/ocr.py`` because the response-construction
code was carrying four distinct concerns:

- Document metadata headers (quality / structure / sections) emitted
  as compact JSON to ``X-Document-Quality`` / ``X-Document-Structure``
  / ``X-Document-Sections`` for the front-end progress UI.
- Workflow summary header (the canonical "what did this request run
  with" snapshot).
- Token-bound artifact id headers (``X-Text-Artifact-Id``,
  ``X-Text-Artifact-Token``, ``X-Document-Metadata-*``).
- ``FileResponse`` with the cleanup background task.

This module owns the shape that the front-end reads; the route handler
only decides *when* to call :func:`build_ocr_file_response`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse

from local_deepl import OCRPipeline
from local_deepl.api.schemas import ProcessSettings
from local_deepl.api.services.artifacts import TextArtifactHandle
from local_deepl.api.services.workflow import build_workflow_summary

_METADATA_HEADER_FIELDS = ("quality", "structure", "sections")


def _document_metadata_header(pipeline: OCRPipeline, field_name: str) -> str | None:
    """Render the per-page metadata header for ``field_name``.

    Reads ``page.metadata[field_name]`` on each page; returns ``None``
    when no page carries that metadata (so the response.header line is
    just omitted — better than emitting an empty ``{"pages":[]}``).
    """
    document = getattr(pipeline, "last_document_result", None)
    if document is None:
        return None

    pages: list[dict[str, object]] = []
    for page in document.pages:
        # Each page carries an arbitrary `metadata: dict`; processors
        # populate their own keys. We pull out the requested field and
        # surface only pages that have it.
        meta = page.metadata if hasattr(page, "metadata") else None
        if meta is None:
            continue
        value = meta.get(field_name)
        if isinstance(value, dict):
            pages.append({"page_index": page.page_index, field_name: value})

    if not pages:
        return None
    return json.dumps({"pages": pages}, separators=(",", ":"), sort_keys=True)


def _validation_error_response(exc: ValidationError) -> JSONResponse:
    """Render a Pydantic validation failure as a stable 422 response."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Invalid request parameters.",
            "detail": exc.errors(include_context=False),
        },
    )


def _metadata_headers_from_pipeline(
    pipeline: OCRPipeline,
) -> dict[str, str]:
    """Return all populated document-metadata headers as a dict."""
    headers: dict[str, str] = {}
    for field in _METADATA_HEADER_FIELDS:
        header_value = _document_metadata_header(pipeline, field)
        if header_value is not None:
            headers[f"X-Document-{field.capitalize()}"] = header_value
    return headers


def build_ocr_file_response(
    *,
    pipeline: OCRPipeline,
    settings: ProcessSettings,
    output_path: str,
    input_path: str,
    artifact_handle: TextArtifactHandle,
    metadata_handle: TextArtifactHandle | None,
    cleanup_callback: Any,
    filename: str,
    failed_pages: list[int],
) -> FileResponse:
    """Assemble the full ``FileResponse`` for a successful OCR run.

    The background task runs after the response is shipped and is
    responsible for deleting temporary files (input, output, optional
    text-artifact file).
    """
    response = FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"ocr_{filename}",
        background=BackgroundTask(cleanup_callback, input_path, output_path),
    )
    response.headers["X-Text-Artifact-Id"] = artifact_handle.artifact_id
    if failed_pages:
        response.headers["X-Failed-Pages"] = ",".join(str(p) for p in failed_pages)
    response.headers["X-Text-Artifact-Token"] = artifact_handle.token
    response.headers["X-Document-Workflow"] = json.dumps(
        build_workflow_summary(settings), separators=(",", ":"), sort_keys=True
    )
    if metadata_handle is not None:
        response.headers["X-Document-Metadata-Artifact-Id"] = (
            metadata_handle.artifact_id
        )
        response.headers["X-Document-Metadata-Artifact-Token"] = metadata_handle.token
    for header_name, header_value in _metadata_headers_from_pipeline(pipeline).items():
        response.headers[header_name] = header_value
    return response


__all__ = [
    "_validation_error_response",
    "build_ocr_file_response",
]
