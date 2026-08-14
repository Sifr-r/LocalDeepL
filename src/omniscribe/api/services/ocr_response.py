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

from omniscribe import OCRPipeline
from omniscribe.api.schemas import ProcessSettings
from omniscribe.api.services.artifacts import TextArtifactHandle
from omniscribe.api.services.security import api_error_response
from omniscribe.api.services.workflow import build_workflow_summary

_METADATA_HEADER_FIELDS = ("quality", "structure", "sections")

# Cap each leaf string before JSON serialization so a single oversized
# processor value cannot balloon the response header to multi-MB.
_METADATA_VALUE_MAX_CHARS = 4 * 1024

# Substring tokens (lowercased) that mark a metadata key as sensitive —
# any key whose lowercased name contains one of these has its value
# replaced with the literal ``"[redacted]"`` before serialization.
_SENSITIVE_KEY_TOKENS = (
    "path",
    "filename",
    "email",
    "secret",
    "token",
    "password",
    "key",
)

_TRUNCATED_SUFFIX = "\u2026[truncated]"

_TRUST_HISTOGRAM_BINS = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1")
_TRUST_BIN_EDGES = (0.2, 0.4, 0.6, 0.8, 1.0)


def _is_sensitive_key(key: object) -> bool:
    """Return ``True`` when ``key`` is a string containing a sensitive token."""
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _redact_metadata(value: object) -> object:
    """Recursively redact sensitive keys and truncate oversized strings.

    Walks ``dict`` and ``list`` containers in place-shape. For each
    ``dict`` key whose lowercased name contains any
    :data:`_SENSITIVE_KEY_TOKENS` substring, the value is replaced with
    the literal ``"[redacted]"``. Any ``str`` value longer than
    :data:`_METADATA_VALUE_MAX_CHARS` is truncated to that cap and
    suffixed with ``"\u2026[truncated]"``. Other primitive types pass
    through unchanged so numeric scores and booleans survive the round
    trip into JSON.

    The redacted form is what lands in the response header — the
    underlying ``page.metadata`` storage is untouched, so processors
    can keep their internal data intact.
    """
    if isinstance(value, dict):
        return {
            k: "[redacted]" if _is_sensitive_key(k) else _redact_metadata(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, str):
        if len(value) > _METADATA_VALUE_MAX_CHARS:
            return value[:_METADATA_VALUE_MAX_CHARS] + _TRUNCATED_SUFFIX
        return value
    return value


def _trust_bin(score: float) -> str:
    """Return the histogram bin label for a trust score in ``[0, 1]``.

    The upper bin (``0.8-1``) is inclusive of both ends so a perfect
    ``1.0`` lands in the rightmost bucket; the other bins use the
    standard half-open ``[a, b)`` semantics. Out-of-range scores are
    clamped — the trust layer guarantees ``[0, 1]`` but defensively
    prevents ``KeyError`` if a calibration edge case slips through.
    """
    clamped = max(0.0, min(1.0, score))
    for edge, label in zip(_TRUST_BIN_EDGES, _TRUST_HISTOGRAM_BINS, strict=False):
        if clamped < edge:
            return label
    return _TRUST_HISTOGRAM_BINS[-1]


def _document_trust_summary(pipeline: OCRPipeline) -> dict[str, object] | None:
    """Return a compact ``X-Document-Trust`` summary for ``pipeline``.

    The header is *only* emitted when at least one block carries a
    ``trust_score`` — when the trust layer is off (the Phase 1 default)
    every block has ``trust_score=None`` and the summary short-circuits
    to ``None`` so the front-end TrustPanel can stay hidden without any
    additional gating logic.

    Schema (matches the front-end TrustPanel):

    - ``block_count`` — total blocks across all pages
    - ``scored_count`` — blocks with a non-None ``trust_score``
    - ``flagged_count`` — blocks with at least one ``trust_flag``
    - ``average`` — mean trust_score across scored blocks (None if none scored)
    - ``histogram`` — count per bin in :data:`_TRUST_HISTOGRAM_BINS`
    - ``flag_counts`` — per-flag occurrence count (HALLUCINATION_RISK, etc.)
    """
    document = getattr(pipeline, "last_document_result", None)
    if document is None:
        return None

    block_count = 0
    scored_count = 0
    flagged_count = 0
    score_sum = 0.0
    histogram = dict.fromkeys(_TRUST_HISTOGRAM_BINS, 0)
    flag_counts: dict[str, int] = {}

    for page in document.pages:
        for block in page.blocks:
            block_count += 1
            score = getattr(block, "trust_score", None)
            if score is None:
                continue
            scored_count += 1
            score_sum += score
            histogram[_trust_bin(score)] += 1
            flags = getattr(block, "trust_flags", None) or ()
            if flags:
                flagged_count += 1
                for flag in flags:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1

    if scored_count == 0:
        return None

    average = round(score_sum / scored_count, 6)
    return {
        "block_count": block_count,
        "scored_count": scored_count,
        "flagged_count": flagged_count,
        "average": average,
        "histogram": histogram,
        "flag_counts": flag_counts,
    }


def _trust_header_from_pipeline(pipeline: OCRPipeline) -> str | None:
    """Render the trust summary as compact JSON for the response header.

    Returns ``None`` when the summary would be empty (no block was
    scored) so the ``X-Document-Trust`` header line is just omitted.
    """
    summary = _document_trust_summary(pipeline)
    if summary is None:
        return None
    return json.dumps(summary, separators=(",", ":"), sort_keys=True)


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
            # Redact sensitive keys + truncate oversized strings before
            # serialization so a processor cannot leak PII into the
            # response header (Phase 3 fix, finding 1.8).
            pages.append(
                {"page_index": page.page_index, field_name: _redact_metadata(value)}
            )

    if not pages:
        return None
    return json.dumps({"pages": pages}, separators=(",", ":"), sort_keys=True)


def _validation_error_response(exc: ValidationError) -> JSONResponse:
    """Render a Pydantic validation failure as a stable 422 response.

    Uses the standard ``api_error_response`` envelope so clients get a
    uniform shape across validation, value, and server errors.
    """
    return api_error_response(
        422,
        "Invalid request parameters.",
        detail=exc.errors(include_context=False),
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
    # Phase 2 — surface the trust-layer summary (block count, flagged count,
    # score histogram) on the response so the front-end TrustPanel can render
    # without re-parsing the OCR text artifact. The header is omitted when no
    # block carries a ``trust_score`` — matching the no-orchestrator default.
    trust_header = _trust_header_from_pipeline(pipeline)
    if trust_header is not None:
        response.headers["X-Document-Trust"] = trust_header
    return response


__all__ = [
    "_document_trust_summary",
    "_trust_header_from_pipeline",
    "_validation_error_response",
    "build_ocr_file_response",
]
