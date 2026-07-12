"""Translation API routes: glossary, tree-aware translation, NLLB fast path.

Adds the following endpoints to the existing AI service:

- ``POST /api/glossary`` -> upload a glossary (JSON or paired-lines text)
- ``POST /api/translate/tree`` -> translate a stored text artifact
  (structure-preserving). Streams ``translate_chunk_complete`` events if a
  ``channel_id`` is supplied.
- ``POST /api/translate/nllb`` -> fast translation via NLLB-200
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from local_deepl.api.routers import state
from local_deepl.api.routers.websocket import manager
from local_deepl.api.schemas.requests import (
    GlossaryRequest,
    TreeTranslationRequest,
)
from local_deepl.core.glossary import Glossary
from local_deepl.core.translation_tree import translate_tree

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_pages_from_artifact(artifact_id: str, token: str) -> dict:
    try:
        path = state.text_artifacts.get(artifact_id, token)
        import json

        with open(path, encoding="utf-8") as f:
            raw_data = json.load(f)
        pages_data = {
            int(p): [([0.0, 0.0, 0.0, 0.0], txt) for txt in lines]
            for p, lines in raw_data.items()
        }
        return pages_data
    except Exception as exc:
        raise HTTPException(status_code=404, detail="text artifact not found") from exc


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
        raise HTTPException(status_code=422, detail="Provide 'entries' or 'text'.")
    return glossary.to_dict()


@router.post("/api/translate/tree")
async def translate_tree_endpoint(req: TreeTranslationRequest) -> dict[str, Any]:
    """Translate a stored text artifact with structure preservation.

    Walks the artifact's pages, translates each text block, and writes the
    result back. If ``channel_id`` is supplied, streams
    ``translate_chunk_complete`` events.
    """
    pages_data = _load_pages_from_artifact(
        req.text_artifact_id, req.text_artifact_token
    )
    if not pages_data:
        return {"status": "empty", "translated_pages": {}}

    from local_deepl.core.block_tree import from_pages_data

    tree = from_pages_data(pages_data)

    glossary = Glossary()
    if req.glossary:
        glossary = Glossary.from_dict({"entries": req.glossary})

    api_base = (
        req.api_base or state.config.api_base if hasattr(state, "config") else None
    )
    api_key = req.api_key or state.config.api_key if hasattr(state, "config") else None
    model = req.model or (state.config.model if hasattr(state, "config") else None)

    from local_deepl.core.llm_client import call_llm

    async def _llm_translate(prompt: str, lang: str) -> str:
        return await call_llm(
            model=model or "allenai/olmocr-2-7b",
            api_base=api_base or "http://localhost:1234/v1",
            api_key=api_key or "lm-studio",
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

    second = None
    if req.dual_translate:

        async def _secondary(prompt: str, lang: str) -> str:
            return await _llm_translate(prompt, lang)

        second = _secondary

    from local_deepl.core.entity_memory import EntityMemory

    memory = EntityMemory()
    for _page_lines in pages_data.values():
        for _bbox, text in _page_lines:
            if text:
                memory.add_text(text)

    # Phase C (review M1) — wire the WebSocket streaming through
    # `translate_tree`'s `on_translate_chunk` parameter. The pre-fix
    # code path duplicated `translate_tree`'s body (skip headers, build
    # context, sliding window, LLM call, write-back) so the WS frame
    # could be emitted per chunk. After the callback lands, the core
    # does the work and the API layer only translates callback args
    # into the right transport frame.
    async def _on_translate_chunk(
        chunk_idx: int,
        source_chars: int,
        translated_text: str,
        target_language: str,
    ) -> None:
        # The channel_id auth check is the WS manager's responsibility
        # (silently no-ops on an unbound / un-authorized channel). The
        # routing contract: `channel_id` presence is the only
        # "should I emit" signal this layer owns.
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
        raise HTTPException(status_code=422, detail="'text' is required")

    from local_deepl.core.nllb_engine import NLLBEngine

    engine = NLLBEngine()
    if not engine.is_available():
        raise HTTPException(
            status_code=503,
            detail="NLLBEngine is not available. Install the 'nllb' extra: uv sync --extra nllb",
        )
    result = await engine.translate(text, target)
    return {
        "translated_text": result.text,
        "source_lang": result.source_lang,
        "target_lang": result.target_lang,
    }
