"""Translate service: sync re-home, async tree runner, status mapping.

The sync path is a verbatim re-home of the pre-harness
``api/services/ai.py`` ``translate_text`` (commit ``44ef123^``), adapted
to harness settings resolution and the token-bound ``ArtifactStore``.
The module deliberately imports ``TRANSLATION_SYSTEM_MESSAGE`` from
``core.translate.nodes`` — the same system message the LangGraph workflow
uses — rather than redefining it. The async runner and status mapping
land in Task 3.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from omniscribe.config import RuntimeSettings
from omniscribe.core.llm.client import call_llm
from omniscribe.core.llm.temperatures import TEMPERATURE_TRANSLATION
from omniscribe.core.translate.nodes import TRANSLATION_SYSTEM_MESSAGE
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.documents.service import load_pages
from omniscribe.plugins.translate.schemas import TranslationRequest
from omniscribe.utils.prompt_safety import sanitize_prompt_input
from omniscribe.utils.security import check_ssrf_target_sync

_LOGGER = logging.getLogger("omniscribe.plugins.translate")


class TranslateError(Exception):
    """User-facing translate error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def build_translation_prompt(text: str, target_language: str) -> str:
    """Verbatim re-home from ``api/services/ai.py`` (44ef123^)."""
    safe_text = sanitize_prompt_input(text)
    return (
        f"Translate the following document text into {target_language}. "
        f"Maintain all markdown formatting, headings, lists, tables, and mathematical formulas exactly. "
        f"Do not add any introductory or concluding comments, explanations, or meta-commentary. "
        f"Only output the direct translation.\n\n"
        f"TEXT:\n{safe_text}"
    )


def _parse_json_object(blob: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(blob)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _resolve_coordinates(
    request_base: str | None,
    request_key: str | None,
    request_model: str | None,
    settings: RuntimeSettings,
) -> tuple[str, str, str]:
    """Override → settings trio; SSRF-check the override only
    (pipeline_bridge trust boundary)."""
    if request_base and request_base.strip():
        check = check_ssrf_target_sync(request_base.strip())
        if not check.allowed:
            raise TranslateError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason}",
            )
    return (
        (request_base or settings.llm_api_base).strip(),
        (request_key or settings.llm_api_key).strip(),
        (request_model or settings.llm_model).strip(),
    )


async def translate_text(
    request: TranslationRequest,
    settings: RuntimeSettings,
    store: ArtifactStore | None = None,
) -> str:
    """Sync single-shot translation; verbatim old semantics.

    ``store=None`` exists only so pure-function tests can call this
    without a store; the route always passes the injected store.
    """
    source_text = request.text.strip()
    if not source_text and request.text_artifact_id and request.text_artifact_token:
        if store is None:
            raise TranslateError(404, "not_found", "text artifact not found")
        blob = await store.get(request.text_artifact_id, request.text_artifact_token)
        if blob is None:
            raise TranslateError(404, "not_found", "text artifact not found")
        raw = _parse_json_object(blob.blob)
        if raw is not None:
            pages = load_pages(raw)
            source_text = "\n\n".join(
                "\n".join(lines) for _page, lines in sorted(pages.items())
            ).strip()

    if not source_text:
        return ""

    api_base, api_key, model = _resolve_coordinates(
        request.api_base, request.api_key, request.model, settings
    )
    prompt = build_translation_prompt(source_text, request.target_language)
    try:
        content = await call_llm(
            model=model,
            api_base=api_base,
            api_key=api_key,
            temperature=TEMPERATURE_TRANSLATION,
            system_prompt=TRANSLATION_SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        _LOGGER.exception("Translation request failed")
        raise TranslateError(502, "ai_error", "The AI service request failed.") from exc
    return content.strip()
