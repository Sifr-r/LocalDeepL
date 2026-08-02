"""Multi-source glossary import and library management endpoints."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query

from local_deepl.api.celery_app import celery_app  # noqa: F401  (re-exported for tasks)
from local_deepl.api.routers import state
from local_deepl.api.schemas.requests import (
    GlossaryFormat,
    GlossaryImportJobResponse,
    GlossaryImportRequest,
    GlossaryImportSource,
    GlossaryListItem,
    GlossaryPreviewResponse,
    GlossaryReorderRequest,
    GlossaryToggleRequest,
)
from local_deepl.core.glossary_library import (
    GlossaryLibrary,
    GlossaryNotFoundError,
    StoredGlossary,
)
from local_deepl.core.glossary_sources import (
    FormatNotAvailableError,
    GlossaryImportLimitError,
    parse,
)
from local_deepl.core.translation_config import AsyncTranslationUnavailable
from local_deepl.utils.security import is_ssrf_target

router = APIRouter()
logger = logging.getLogger(__name__)

SYNC_THRESHOLD = 5_000


def _library() -> GlossaryLibrary:
    return state.glossary_library


def _serialize_item(item: StoredGlossary) -> GlossaryListItem:
    return GlossaryListItem(
        id=item.id,
        name=item.name,
        format=_coerce_format(item.format),
        source_uri=item.source_uri,
        encoding=item.encoding,
        entry_count=len(item.entries),
        enabled=item.enabled,
        priority=item.priority,
        group=item.group,
    )


def _serialize_items(items: list[StoredGlossary]) -> list[GlossaryListItem]:
    return [_serialize_item(item) for item in items]


def _coerce_format(value: str) -> GlossaryFormat:
    try:
        return GlossaryFormat(value)
    except ValueError:
        return GlossaryFormat.JSON_PAIRS


def _decode_bytes_payload(value: str) -> bytes:
    if not value:
        raise HTTPException(status_code=422, detail="inline_bytes_b64 is required.")
    import binascii

    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=422, detail="inline_bytes_b64 is not valid base64."
        ) from exc


def _has_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _sync_ssrf(url: str) -> bool:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return bool(pool.submit(asyncio.run, is_ssrf_target(url)).result())


def _validate_ssrf(url: str) -> None:
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")
    blocked = (
        _sync_ssrf(url) if not _has_running_loop() else asyncio.run(is_ssrf_target(url))
    )
    if blocked:
        raise HTTPException(status_code=400, detail="URL targets a blocked address.")


def _is_safe_sql_dsn(dsn: str) -> bool:
    """Reject DSNs with shell metacharacters or query-string injection."""
    if not dsn:
        return False
    try:
        parsed = urlparse(dsn)
    except ValueError:
        return False
    if not parsed.scheme or parsed.scheme not in {
        "sqlite",
        "postgresql",
        "mysql",
        "mssql",
        "oracle",
    }:
        return False
    return not any(ch in dsn for ch in (";", "\n", "\r", "\x00"))


def _build_parser_kwargs(source: GlossaryImportSource) -> tuple[dict[str, Any], str]:
    """Translate the request source spec into parser kwargs.

    ``name`` is intentionally omitted here: it is surfaced only by the
    router as the saved glossary's display name, not a parser argument.
    Other metadata (e.g. ``max_entries``) that the router also surfaces is
    popped off inside :func:`parse`.
    """
    format_name = GlossaryFormat(source.format).value
    kwargs: dict[str, Any] = {"max_entries": source.max_entries}

    if format_name in {"csv", "tsv", "xliff", "tbx", "tmx", "json_pairs"}:
        if source.text is not None:
            kwargs["text"] = source.text
        elif source.inline_bytes_b64 is not None:
            kwargs["data"] = _decode_bytes_payload(source.inline_bytes_b64)
        else:
            raise HTTPException(
                status_code=422,
                detail="Provide 'text' or 'inline_bytes_b64' for inline formats.",
            )
        kwargs["encoding"] = source.encoding
    elif format_name == "git_glossary":
        if not source.git_url:
            raise HTTPException(
                status_code=422, detail="git_url is required for git_glossary imports."
            )
        _validate_ssrf(source.git_url)
        kwargs.update(
            {
                "url": source.git_url,
                "ref": source.git_ref or "HEAD",
                "path": source.git_path or "GLOSSARY.md",
                "credentials": source.git_credentials,
            }
        )
    elif format_name == "sql_table":
        if not (
            source.sql_dsn
            and source.sql_source_table
            and source.sql_source_col
            and source.sql_target_col
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "sql_dsn, sql_source_table, sql_source_col and sql_target_col "
                    "are required for sql_table imports."
                ),
            )
        if not _is_safe_sql_dsn(source.sql_dsn):
            raise HTTPException(
                status_code=422, detail="sql_dsn contains unsafe characters."
            )
        kwargs.update(
            {
                "dsn": source.sql_dsn,
                "source_table": source.sql_source_table,
                "source_col": source.sql_source_col,
                "target_table": source.sql_target_table,
                "target_col": source.sql_target_col,
                "where_clause": source.sql_where,
                "encoding": source.encoding,
            }
        )
    else:  # pragma: no cover - exhausted by GlossaryFormat
        raise HTTPException(
            status_code=422, detail=f"Unsupported format: {format_name}."
        )
    return kwargs, format_name


def _resolve_request_name(req: GlossaryImportRequest) -> str | None:
    """Return the caller-supplied display name, or None when not provided."""
    candidate = getattr(req.source, "name", None)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


def _entry_count_estimate(kwargs: dict[str, Any]) -> int:
    """Estimate entry count for sync/async threshold selection."""
    text = kwargs.get("text")
    data = kwargs.get("data")
    if isinstance(text, str) and text:
        return max(text.count("\n"), 1)
    if isinstance(data, (bytes, bytearray)) and data:
        return max(bytes(data).count(b"\n"), 1)
    if kwargs.get("dsn") and kwargs.get("source_table"):
        return SYNC_THRESHOLD + 1  # assume large; favor async for SQL.
    if kwargs.get("url"):
        return SYNC_THRESHOLD + 1  # git/remote fetch always async.
    return SYNC_THRESHOLD + 1


def _default_name(format_name: str, kwargs: dict[str, Any]) -> str:
    raw_name = kwargs.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    if kwargs.get("url"):
        return f"Git glossary {kwargs['url']}"
    if kwargs.get("dsn") and kwargs.get("source_table"):
        target = kwargs.get("target_table") or kwargs["source_table"]
        return f"SQL {kwargs['source_table']} \u2192 {target}"
    return f"{format_name.upper()} import"


def _build_async_payload(format_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-safe payload for the Celery task."""
    payload: dict[str, Any] = {"format": format_name}
    for key, value in kwargs.items():
        if key in {"name", "max_entries"}:
            continue
        if isinstance(value, (bytes, bytearray)):
            payload[key] = base64.b64encode(bytes(value)).decode("ascii")
        else:
            payload[key] = value
    if "data" in payload and isinstance(payload["data"], str):
        payload["inline_bytes_b64"] = payload.pop("data")
    return payload


def _process_sync(req: GlossaryImportRequest) -> GlossaryImportJobResponse:
    """Synchronous import path (small to medium files)."""
    kwargs, format_name = _build_parser_kwargs(req.source)
    summary = parse(format=format_name, **kwargs)
    explicit_name = _resolve_request_name(req)
    display_name = explicit_name or _default_name(format_name, kwargs)
    stored = _library().save(
        name=display_name,
        format=format_name,
        entries=summary.entries,
        source_uri=summary.source_uri,
        encoding=summary.encoding,
    )
    return GlossaryImportJobResponse(
        glossary_id=stored.id,
        format=GlossaryFormat(format_name),
        name=stored.name,
        entry_count=len(summary.entries),
        warnings=list(summary.warnings),
        queued=False,
    )


def _process_async(req: GlossaryImportRequest) -> GlossaryImportJobResponse:
    """Queue the import on Celery; returns a job_id."""
    from local_deepl.api.tasks import process_glossary_import_task

    kwargs, format_name = _build_parser_kwargs(req.source)
    explicit_name = _resolve_request_name(req)
    display_name = explicit_name or _default_name(format_name, kwargs)
    payload = _build_async_payload(format_name, kwargs)
    try:
        result = process_glossary_import_task.delay(
            payload,
            display_name,
            req.channel_id,
            req.session_token,
        )
    except AsyncTranslationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return GlossaryImportJobResponse(
        job_id=str(result.id),
        format=GlossaryFormat(format_name),
        name=display_name,
        entry_count=0,
        warnings=[],
        queued=True,
    )


@router.post("/api/glossary/import")
def import_glossary(req: GlossaryImportRequest) -> GlossaryImportJobResponse:
    """Import a glossary; sync up to 5,000 entries, otherwise async."""
    kwargs, _format_name = _build_parser_kwargs(req.source)
    try:
        estimate = _entry_count_estimate(kwargs)
        if estimate <= SYNC_THRESHOLD:
            return _process_sync(req)
        return _process_async(req)
    except FormatNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GlossaryImportLimitError as exc:
        raise HTTPException(
            status_code=413,
            detail={"error": "Too many entries", "max": exc.limit},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/glossary/import/url")
def import_glossary_from_url(
    url: str = Query(..., min_length=1),
    name: str | None = Query(default=None, max_length=200),
    encoding: str | None = Query(default=None),
    format_param: GlossaryFormat | None = Query(default=None, alias="format"),
) -> GlossaryImportJobResponse:
    """Infer format from URL extension (or use ?format=) and run the sync path."""
    _validate_ssrf(url)
    extension_to_format = {
        "csv": GlossaryFormat.CSV,
        "tsv": GlossaryFormat.TSV,
        "xlf": GlossaryFormat.XLIFF,
        "xliff": GlossaryFormat.XLIFF,
        "tbx": GlossaryFormat.TBX,
        "tmx": GlossaryFormat.TMX,
        "json": GlossaryFormat.JSON_PAIRS,
    }
    path = urlparse(url).path
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    fmt = format_param or extension_to_format.get(suffix)
    if fmt is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not infer format from URL. Pass ?format=csv|tsv|xliff|tbx|tmx|json_pairs."
            ),
        )

    try:
        from local_deepl.api.services.http_fetch import fetch_url_bytes
    except ImportError:
        fetch_url_bytes = None  # type: ignore[assignment]

    if fetch_url_bytes is None:
        raise HTTPException(
            status_code=503,
            detail="URL fetching is not configured. Use inline 'text' or 'inline_bytes_b64'.",
        )

    try:
        payload = asyncio.run(fetch_url_bytes(url))
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch URL: {exc}"
        ) from exc

    source = GlossaryImportSource(
        format=fmt,
        inline_bytes_b64=base64.b64encode(payload).decode("ascii"),
        encoding=encoding,
        name=name,
    )
    return import_glossary(GlossaryImportRequest(source=source))


@router.get("/api/glossary/library")
def list_library() -> list[GlossaryListItem]:
    """Return every stored glossary in priority/insertion order."""
    return _serialize_items(_library().items())


@router.post("/api/glossary/library/{glossary_id}/enable")
def toggle_library_entry(
    glossary_id: str,
    req: GlossaryToggleRequest,
) -> GlossaryListItem:
    try:
        stored = _library().toggle(glossary_id, enabled=req.enabled)
    except GlossaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Glossary not found.") from exc
    return _serialize_item(stored)


@router.post("/api/glossary/library/reorder")
def reorder_library(req: GlossaryReorderRequest) -> dict[str, Any]:
    try:
        _library().reorder(req.ordered_ids)
    except GlossaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Glossary not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/api/glossary/library/{glossary_id}")
def delete_library_entry(glossary_id: str) -> dict[str, Any]:
    deleted = _library().delete(glossary_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Glossary not found.")
    return {"ok": True, "id": glossary_id}


@router.get("/api/glossary/library/preview")
def library_preview() -> GlossaryPreviewResponse:
    payload = _library().preview()
    conflicts_value = payload.get("conflicts", [])
    enabled_value = payload.get("enabled_glossaries", [])
    if not isinstance(conflicts_value, list):
        conflicts_value = []
    if not isinstance(enabled_value, list):
        enabled_value = []
    return GlossaryPreviewResponse(
        count=int(str(payload.get("count", 0) or 0)),
        conflicts=[dict(item) for item in conflicts_value if isinstance(item, dict)],
        enabled_glossaries=[str(item) for item in enabled_value],
    )


@router.get("/api/glossary/library/{glossary_id}/entries")
def library_entries(glossary_id: str) -> dict[str, Any]:
    stored = _library().get(glossary_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Glossary not found.")
    return {
        "id": stored.id,
        "name": stored.name,
        "format": stored.format,
        "entries": [dict(item) for item in stored.entries],
    }


@router.get("/api/glossary/library/merged")
def merged_entries() -> dict[str, Any]:
    """Return the merged enabled glossary for use by translation requests."""
    return _library().merged_enabled().to_dict()
