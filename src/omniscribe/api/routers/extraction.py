"""Document export API (DOCX, HTML, block-tree JSON, structured Markdown).

New endpoints added in the upgrade:

- ``POST /api/export/html`` -> HTML with semantic markup
- ``POST /api/export/blocktree`` -> block-tree JSON

``POST /api/export/document`` and ``POST /api/export/docx`` live in
:mod:`omniscribe.api.routers.artifacts` (registered first, so a duplicate
here would only shadow into dead code and duplicate the OpenAPI operation
ID).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from omniscribe.api.routers import state
from omniscribe.api.routers.config import _config
from omniscribe.api.schemas.requests import (
    ExportBlockTreeRequest,
    ExportHtmlRequest,
    ExtractionRequest,
)
from omniscribe.api.services.ai import AIServiceError, extract_structured_data
from omniscribe.api.services.api_helpers import stable_server_error
from omniscribe.api.services.envelope import (
    BadRequest,
    NotFound,
    SSRFBlocked,
    envelope_error,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_tree_from_artifact(artifact_id: str, token: str) -> Any:
    try:
        path = await state.text_artifacts.get(artifact_id, token)

        import os
        from pathlib import Path

        from omniscribe.api.services.tree_artifact import read_tree

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
        from omniscribe.core.block_tree import from_pages_data

        return from_pages_data(pages_data)
    except Exception as exc:
        raise NotFound(detail="text artifact not found") from exc


@router.post("/api/export/docx-tree")
async def export_docx_tree(req: ExportBlockTreeRequest) -> Response:
    """Generate a structured .docx from a stored DocumentTree artifact."""
    from omniscribe.core.writers.docx_tree import convert_tree_to_docx

    tree = await _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)
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
    from omniscribe.core.writers.html import render_html

    tree = await _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)
    html = render_html(tree)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=document.html"},
    )


@router.post("/api/export/blocktree")
async def export_blocktree(req: ExportBlockTreeRequest) -> JSONResponse:
    """Return the block-tree JSON for a stored text artifact."""
    from omniscribe.core.writers.tree_json import export_json

    tree = await _load_tree_from_artifact(req.text_artifact_id, req.text_artifact_token)

    if req.metadata_artifact_id and req.metadata_artifact_token:
        try:
            meta_path = await state.metadata_artifacts.get(
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
    if not body.text.strip():
        raise BadRequest(detail="'text' is required")
    try:
        extracted = await extract_structured_data(body, config=_config)
    except AIServiceError as exc:
        if exc.status_code == 400:
            raise BadRequest(detail=exc.public_message) from exc
        if exc.status_code == 403:
            raise SSRFBlocked(url="", reason=exc.public_message) from exc
        # 500 (AIProviderError) and any other status code — keep the
        # opaque-message envelope shape so we don't leak internal detail.
        return envelope_error(
            status_code=exc.status_code,
            error="ai_error",
            detail=exc.public_message,
        )
    except Exception:
        logger.exception("Extraction request failed")
        return stable_server_error()
    return {"extracted_data": extracted}
