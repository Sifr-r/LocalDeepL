"""Translation API routes: async tasks, glossary, tree-aware translation, NLLB fast path."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter

from omniscribe.api.routers import state
from omniscribe.api.routers.websocket import manager
from omniscribe.api.schemas.requests import (
    GlossaryRequest,
    TranslationRequest,
    TreeTranslationRequest,
)
from omniscribe.api.services.ai import (
    AIServiceError,
)
from omniscribe.api.services.ai import (
    translate_text as translate_document_text,
)
from omniscribe.api.services.envelope import (
    BackendUnavailable,
    BadRequest,
    NotFound,
    SSRFBlocked,
    ValidationFailed,
    envelope_error,
)
from omniscribe.api.services.security import SERVER_ERROR_MESSAGE
from omniscribe.core.glossary import Glossary
from omniscribe.core.translation_config import AsyncTranslationUnavailable
from omniscribe.core.translation_tree import translate_tree
from omniscribe.utils.security import is_ssrf_target

from ..services.api_helpers import stable_server_error
from .config import _config

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_pages_from_artifact(artifact_id: str, token: str) -> dict:
    try:
        path = await state.text_artifacts.get(artifact_id, token)
        import json

        with open(path, encoding="utf-8") as f:
            raw_data = json.load(f)
        pages_data = {
            int(p): [([0.0, 0.0, 0.0, 0.0], txt) for txt in lines]
            for p, lines in raw_data.items()
        }
        return pages_data
    except Exception as exc:
        raise NotFound(detail="text artifact not found") from exc


@router.post("/api/translate")
async def translate_text(body: TranslationRequest):
    """Translate OCR text into the requested target language."""
    if not body.text.strip() and not (
        body.text_artifact_id and body.text_artifact_token
    ):
        raise BadRequest(
            detail="'text' or 'text_artifact_id'/'text_artifact_token' is required"
        )
    try:
        translated = await translate_document_text(body, config=_config)
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
        logger.exception("Translation request failed")
        return stable_server_error()
    return {"translated_text": translated}


@router.post("/api/translate/async")
async def translate_text_async(body: TreeTranslationRequest):
    """Trigger a background tree translation job via Celery.

    Returns 503 if the optional async-translation extras are not installed.
    """
    from omniscribe.api.tasks import process_translation_task

    try:
        task = process_translation_task.delay(
            body.text_artifact_id,
            body.text_artifact_token,
            body.target_language,
            body.glossary or [],
        )
    except AsyncTranslationUnavailable as exc:
        raise BackendUnavailable(detail=str(exc)) from exc

    return {"job_id": task.id, "status": "Processing"}


@router.get("/api/translate/status/{job_id}")
async def get_translation_status(job_id: str):
    """Poll the status of a Celery background translation job."""
    from omniscribe.api.celery_app import celery_app

    try:
        task = celery_app.AsyncResult(job_id)
    except AsyncTranslationUnavailable as exc:
        raise BackendUnavailable(detail=str(exc)) from exc

    try:
        response: dict[str, Any] = {
            "job_id": job_id,
            "state": task.state,
        }
        if task.state == "PENDING":
            response["status"] = "Pending..."
            return response
        if task.state == "FAILURE":
            logger.error("Async translation task failed: %s", task.info)
            return envelope_error(
                status_code=200,
                error="internal_error",
                detail=SERVER_ERROR_MESSAGE,
                extra={"job_id": job_id, "state": task.state},
            )
        response["info"] = task.info
        if task.state == "SUCCESS":
            response["result"] = task.get()
        return response
    except Exception:
        logger.exception("Async translation status lookup failed")
        return stable_server_error()


@router.post("/api/glossary")
async def upload_glossary(req: GlossaryRequest) -> dict[str, Any]:
    """Accept a glossary either as JSON entries or as paired-lines text.

    Returns the parsed glossary as JSON so the client can verify it.
    """
    if req.entries:
        glossary = Glossary.from_dict({"entries": req.entries})
    elif req.text:
        glossary = Glossary.from_paired_lines(req.text)
    else:
        raise ValidationFailed(detail="Provide 'entries' or 'text'.")
    return glossary.to_dict()


@router.post("/api/translate/tree")
async def translate_tree_endpoint(req: TreeTranslationRequest) -> dict[str, Any]:
    """Translate a stored text artifact with structure preservation.

    Walks the artifact's pages, translates each text block, and writes the
    result back. If ``channel_id`` is supplied, streams
    ``translate_chunk_complete`` events.
    """
    pages_data = await _load_pages_from_artifact(
        req.text_artifact_id, req.text_artifact_token
    )
    if not pages_data:
        return {"status": "empty", "translated_pages": {}}

    from omniscribe.core.block_tree import from_pages_data

    tree = from_pages_data(pages_data)

    glossary = Glossary()
    if req.glossary:
        glossary = Glossary.from_dict({"entries": req.glossary})

    # Precedence note: the previous form
    # ``req.api_base or state.config.api_base if hasattr(state, "config") else None``
    # parsed as ``(a or b) if cond else None`` and ``state.config`` is never
    # set, so request-level overrides and the SSRF guard were both dead
    # code. Resolve through the runtime config store like the model
    # discovery routes do.
    config = cast(dict[str, Any], _config)
    api_base = req.api_base or config.get("translation_api_base") or config["api_base"]
    if api_base and not (await is_ssrf_target(api_base)).allowed:
        raise SSRFBlocked(url=api_base, reason="api_base_blocked")
    api_key = req.api_key or config.get("translation_api_key") or config["api_key"]
    model = req.model or config.get("translation_model") or config.get("model")

    from omniscribe.core.llm_client import call_llm
    from omniscribe.core.llm_temperatures import TEMPERATURE_TRANSLATION_TREE
    from omniscribe.core.translation import TRANSLATION_SYSTEM_MESSAGE

    async def _llm_translate(prompt: str, lang: str) -> str:
        return await call_llm(
            model=model or "allenai/olmocr-2-7b",
            api_base=api_base or "http://localhost:1234/v1",
            api_key=api_key or "lm-studio",
            temperature=TEMPERATURE_TRANSLATION_TREE,
            system_prompt=TRANSLATION_SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": prompt}],
        )

    second = None
    if req.dual_translate:

        async def _secondary(prompt: str, lang: str) -> str:
            return await _llm_translate(prompt, lang)

        second = _secondary

    from omniscribe.core.entity_memory import EntityMemory

    memory = EntityMemory()
    for _page_lines in pages_data.values():
        for _bbox, text in _page_lines:
            if text:
                memory.add_text(text)

    async def _on_translate_chunk(
        chunk_idx: int,
        source_chars: int,
        translated_text: str,
        target_language: str,
    ) -> None:
        if not req.channel_id:
            return
        await manager.send_translate_chunk(
            req.channel_id,
            chunk_idx=chunk_idx,
            source_chars=source_chars,
            translated_text=translated_text,
            target_language=target_language,
        )

    if req.channel_id:
        await manager.send_progress(req.channel_id, "Translating...", 0, "translate")

    await translate_tree(
        tree,
        target_language=req.target_language,
        translator=_llm_translate,
        glossary=glossary,
        memory=memory,
        second_translator=second,
        on_translate_chunk=_on_translate_chunk,
    )

    if req.channel_id:
        await manager.send_progress(
            req.channel_id, "Translation complete.", 100, "translate"
        )

    return {
        "status": "ok",
        "tree": tree.to_dict(),
        "page_count": len(tree.pages),
        "block_count": sum(len(p.children) for p in tree.pages),
    }


@router.post("/api/translate/nllb")
async def translate_nllb(req: dict[str, Any]) -> dict[str, Any]:
    """Fast translation via the local NLLB-200 model.

    Request body: ``{"text": "...", "target_language": "French"}``
    """
    text = (req.get("text") or "").strip() if isinstance(req, dict) else ""
    target = (
        (req.get("target_language") or "English")
        if isinstance(req, dict)
        else "English"
    )
    if not text:
        raise ValidationFailed(detail="'text' is required")

    from omniscribe.core.nllb_engine import NLLBEngine

    engine = NLLBEngine()
    if not engine.is_available():
        raise BackendUnavailable(
            detail="NLLBEngine is not available. Install the 'nllb' extra: uv sync --extra nllb"
        )
    result = await engine.translate(text, target)
    return {
        "translated_text": result.text,
        "source_lang": result.source_lang,
        "target_lang": result.target_lang,
    }
