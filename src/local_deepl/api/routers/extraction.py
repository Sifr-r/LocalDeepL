"""Document export API (DOCX, HTML, block-tree JSON, structured Markdown).

New endpoints added in the upgrade:

- ``POST /api/export/html`` -> HTML with semantic markup
- ``POST /api/export/blocktree`` -> block-tree JSON

The existing ``/api/export/document`` and ``/api/export/docx`` routes are
preserved for backward compatibility.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from local_deepl.api.routers import state
from local_deepl.api.routers.common import _stable_server_error
from local_deepl.api.routers.config import _config
from local_deepl.api.schemas.requests import (
    ExportBlockTreeRequest,
    ExportDocxRequest,
    ExportHtmlRequest,
    ExtractionRequest,
)
from local_deepl.api.services.ai import AIServiceError, extract_structured_data

logger = logging.getLogger(__name__)
router = APIRouter()


def _ai_error_response(exc: AIServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.public_message},
    )


def _load_tree_from_artifact(artifact_id: str, token: str) -> Any:
    try:
        path = state.text_artifacts.get(artifact_id, token)

        import os
        from pathlib import Path

        from local_deepl.api.services.tree_artifact import read_tree

        # Phase D (review M4) — read the JSON tree artifact. Falls
        # back to the legacy text-only artifact if the JSON sidecar
        # is missing (older in-flight requests from before Phase D).
        tree_path = f"{path}.tree.json"
        if os.path.exists(tree_path):
            return read_tree(Path(tree_path))

        # Fallback for legacy text artifacts (no tree sidecar)
        with open(path, encoding="utf-8") as f:
            raw_data = json.load(f)
        import typing

        pages_data: dict[int, typing.Sequence[tuple[typing.Sequence[float], str]]] = {
            int(p): [([0.0, 0.0, 0.0, 0.0], str(txt)) for txt in lines]
            for p, lines in raw_data.items()
        }
        from local_deepl.core.block_tree import from_pages_data

        return from_pages_data(pages_data)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="text artifact not found") from exc


@router.post("/api/export/docx")
async def export_docx(req: ExportDocxRequest) -> Response:
    """Generate a .docx from the supplied markdown text. Backward-compatible."""
    from local_deepl.core.docx_writer import convert_markdown_to_docx

    stream = convert_markdown_to_docx(req.text or "")
    return Response(
        content=stream.getvalue(),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": "attachment; filename=document.docx"},
    )


@router.post("/api/export/docx-tree")
async def export_docx_tree(req: ExportBlockTreeRequest) -> Response:
    """Generate a structured .docx from a stored DocumentTree artifact."""
    from local_deepl.core.docx_tree_writer import convert_tree_to_docx

    tree = _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)
    stream = convert_tree_to_docx(tree)
    return Response(
        content=stream.getvalue(),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": "attachment; filename=document.docx"},
    )


@router.post("/api/export/html")
async def export_html(req: ExportHtmlRequest) -> Response:
    """Generate a structured HTML document from a text artifact."""
    from local_deepl.core.html_writer import render_html

    tree = _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)
    html = render_html(tree)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=document.html"},
    )


@router.post("/api/export/blocktree")
async def export_blocktree(req: ExportBlockTreeRequest) -> JSONResponse:
    """Return the block-tree JSON for a stored text artifact."""
    from local_deepl.core.tree_export import export_json

    tree = _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)

    if req.metadata_artifact_id and req.metadata_artifact_token:
        try:
            meta_path = state.metadata_artifacts.get(
                req.metadata_artifact_id, req.metadata_artifact_token
            )
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            tree.metadata["processor_report"] = meta
        except Exception as exc:
            logger.warning("metadata artifact not attached: %s", exc)

    payload = json.loads(export_json(tree))
    return JSONResponse(content=payload)


@router.post("/api/extract")
async def extract_data(body: ExtractionRequest):
    """Extract structured JSON data from OCR text."""
    try:
        extracted = await extract_structured_data(body, config=_config)
    except AIServiceError as exc:
        return _ai_error_response(exc)
    except Exception:
        logger.exception("Extraction request failed")
        return _stable_server_error()
    return {"extracted_data": extracted}
