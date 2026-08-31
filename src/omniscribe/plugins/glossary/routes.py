"""HTTP routes for the glossary plugin (client-frozen contract).

Import routes accept BOTH shapes (user decision 2026-08-31):
`POST /api/glossary/import` takes the old JSON envelope (application/json)
or the Flutter client's multipart upload; `POST /api/glossary/import/url`
takes old query params or the client's JSON body. Business-rule 422s carry
the `{"error": "validation_failed"}` envelope (old contract); malformed
request schemas return FastAPI-native 422.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportRequest,
    GlossaryReorderRequest,
    GlossaryToggleRequest,
    GlossaryUrlImportBody,
)
from omniscribe.plugins.glossary.service import (
    GlossaryError,
    GlossaryImportService,
)

EXTENSION_TO_FORMAT: dict[str, GlossaryFormat] = {
    "csv": GlossaryFormat.CSV,
    "tsv": GlossaryFormat.TSV,
    "xlf": GlossaryFormat.XLIFF,
    "xliff": GlossaryFormat.XLIFF,
    "tbx": GlossaryFormat.TBX,
    "tmx": GlossaryFormat.TMX,
    "json": GlossaryFormat.JSON_PAIRS,
}

INFERENCE_FAILURE_DETAIL = (
    "Could not infer format from URL. Pass ?format=csv|tsv|xliff|tbx|tmx|json_pairs."
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def _infer_format_from_name(name: str) -> GlossaryFormat | None:
    path = urlparse(name).path if "://" in name else name
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return EXTENSION_TO_FORMAT.get(suffix)


def build_glossary_router(service: GlossaryImportService) -> APIRouter:
    router = APIRouter(tags=["glossary"])

    @router.post("/api/glossary/import", response_model=None)
    async def import_glossary(request: Request) -> dict[str, Any] | JSONResponse:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                return _envelope(400, "bad_request", "missing 'file' field")
            raw: bytes = await upload.read()
            fields: dict[str, Any] = {
                key: value
                for key, value in form.items()
                if key != "file" and isinstance(value, str)
            }
            fmt = fields.pop("format", None)
            if fmt:
                try:
                    format_enum: GlossaryFormat | None = GlossaryFormat(str(fmt))
                except ValueError:
                    return _envelope(422, "validation_failed", f"Unknown format: {fmt}")
            else:
                format_enum = _infer_format_from_name(
                    str(getattr(upload, "filename", "") or "")
                )
                if format_enum is None:
                    return _envelope(
                        422,
                        "validation_failed",
                        "Could not infer format from filename. Pass format=csv|tsv|xliff|tbx|tmx|json_pairs.",
                    )
            try:
                source = GlossaryImportRequest.model_validate(
                    {
                        "source": {
                            "format": format_enum,
                            "inline_bytes_b64": base64.b64encode(raw).decode("ascii"),
                            "encoding": fields.get("encoding"),
                            "name": fields.get("name"),
                        }
                    }
                )
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )
        else:
            try:
                payload = await request.json()
            except Exception:
                return _envelope(400, "bad_request", "Malformed JSON body.")
            try:
                source = GlossaryImportRequest.model_validate(payload)
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )

        try:
            body = await service.import_glossary(source.source)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return body

    @router.post("/api/glossary/import/url", response_model=None)
    async def import_glossary_from_url(
        request: Request,
        url: str | None = None,
        name: str | None = None,
        encoding: str | None = None,
        format: GlossaryFormat | None = None,
    ) -> dict[str, Any] | JSONResponse:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                payload = await request.json()
            except Exception:
                return _envelope(400, "bad_request", "Malformed JSON body.")
            try:
                body_model = GlossaryUrlImportBody.model_validate(payload)
            except ValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": exc.errors(include_url=False)},
                )
            url = body_model.url
            name = body_model.name
            encoding = body_model.encoding
            format = body_model.format
        if not url:
            return _envelope(400, "bad_request", "URL is required.")
        fmt = format or _infer_format_from_name(url)
        if fmt is None:
            return _envelope(422, "validation_failed", INFERENCE_FAILURE_DETAIL)

        try:
            from omniscribe.plugins.glossary.http_fetch import fetch_url_bytes
        except ImportError:
            fetch_url_bytes = None  # type: ignore[assignment]
        if fetch_url_bytes is None:
            return _envelope(
                503,
                "backend_unavailable",
                "URL fetching is not configured. Use inline 'text' or 'inline_bytes_b64'.",
            )
        try:
            payload_bytes = await fetch_url_bytes(url)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        except Exception as exc:
            return _envelope(502, "ai_error", f"Failed to fetch URL: {exc}")

        source = GlossaryImportRequest.model_validate(
            {
                "source": {
                    "format": fmt,
                    "inline_bytes_b64": base64.b64encode(payload_bytes).decode("ascii"),
                    "encoding": encoding,
                    "name": name,
                }
            }
        )
        try:
            body = await service.import_glossary(source.source)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return body

    @router.get("/api/glossary/library", response_model=None)
    async def list_library() -> list[dict[str, Any]] | JSONResponse:
        try:
            return service.list_library()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.post("/api/glossary/library/{glossary_id}/enable", response_model=None)
    async def toggle_library_entry(
        glossary_id: str, req: GlossaryToggleRequest
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.toggle(glossary_id, enabled=req.enabled)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.post("/api/glossary/library/reorder", response_model=None)
    async def reorder_library(
        req: GlossaryReorderRequest,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.reorder(req.ordered_ids)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.delete("/api/glossary/library/{glossary_id}", response_model=None)
    async def delete_library_entry(
        glossary_id: str,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.delete(glossary_id)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/preview", response_model=None)
    async def library_preview() -> dict[str, Any] | JSONResponse:
        try:
            return service.library_preview()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/{glossary_id}/entries", response_model=None)
    async def library_entries(
        glossary_id: str,
    ) -> dict[str, Any] | JSONResponse:
        try:
            return service.entries(glossary_id)
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/glossary/library/merged", response_model=None)
    async def merged_entries() -> dict[str, Any] | JSONResponse:
        try:
            return service.merged()
        except GlossaryError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    return router
