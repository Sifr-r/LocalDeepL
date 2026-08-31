"""HTTP routes for the translate plugin (client-frozen contract)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.plugins.translate.schemas import (
    AsyncTranslationRequest,
    NllbRequest,
    TranslationRequest,
)
from omniscribe.plugins.translate.service import (
    TranslateError,
    TranslationService,
)


def _envelope(status_code: int, error: str, detail: str) -> JSONResponse:
    """Stable error envelope the Flutter client parses."""
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def build_translate_router(service: TranslationService) -> APIRouter:
    router = APIRouter(tags=["translate"])

    @router.post("/api/translate", response_model=None)
    async def translate(body: TranslationRequest) -> dict[str, Any] | JSONResponse:
        if not body.text.strip() and not (
            body.text_artifact_id and body.text_artifact_token
        ):
            return _envelope(
                400,
                "bad_request",
                "'text' or 'text_artifact_id'/'text_artifact_token' is required",
            )
        try:
            translated = await service.translate_sync(body)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)
        return {"translated_text": translated}

    @router.post("/api/translate/async", response_model=None)
    async def translate_async(
        body: AsyncTranslationRequest,
    ) -> dict[str, Any] | JSONResponse:
        # The artifact pair is optional-with-bounds on the schema, so a
        # missing pair never 422s; the route owns the 400 contract.
        if not (body.text_artifact_id and body.text_artifact_token):
            return _envelope(
                400,
                "bad_request",
                "'text_artifact_id'/'text_artifact_token' is required",
            )
        try:
            return await service.submit(body)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    @router.get("/api/translate/status/{job_id}", response_model=None)
    async def translation_status(
        job_id: str,
    ) -> dict[str, Any] | JSONResponse:
        body = await service.job_status(job_id)
        if body is None:
            return _envelope(404, "not_found", "unknown job")
        return body

    @router.get("/api/translate/result/{job_id}", response_model=None)
    async def translate_result(
        job_id: str,
        token: str = "",
    ) -> dict[str, Any] | JSONResponse:
        body = await service.result(job_id, token)
        if body is None:
            # Missing/wrong token, unknown job, or incomplete job all map to
            # the same 404 (no existence leak; C-3/H-3 semantics).
            return _envelope(404, "not_found", "result not found")
        return body

    @router.post("/api/translate/nllb", response_model=None)
    async def translate_nllb(body: NllbRequest) -> dict[str, Any] | JSONResponse:
        try:
            return await service.translate_nllb(body.text, body.target_language)
        except TranslateError as exc:
            return _envelope(exc.status_code, exc.error, exc.detail)

    return router
