"""NLLB-200 fast translation engine.

Wraps :mod:`transformers` to provide CPU-friendly translation when the user
selects "fast" mode or when the configured LLM is unavailable. Lazy-loaded.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import typing
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Map UI-friendly language names to NLLB language codes.
LANGUAGE_CODE_MAP: dict[str, str] = {
    "english": "eng_Latn",
    "spanish": "spa_Latn",
    "french": "fra_Latn",
    "german": "deu_Latn",
    "arabic": "arb_Arab",
    "chinese": "zho_Hans",
    "japanese": "jpn_Jpan",
    "russian": "rus_Cyrl",
    "portuguese": "por_Latn",
    "italian": "ita_Latn",
    "dutch": "nld_Latn",
    "swedish": "swe_Latn",
}


def resolve_nllb_code(language: str) -> str:
    raw = language.strip()
    key = raw.lower()
    if key in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[key]
    # Heuristic: if the language string already looks like a code, use it.
    if "_" in raw and any(c.isupper() for c in raw):
        return raw
    return "eng_Latn"


@dataclass(slots=True)
class NLLBResult:
    text: str
    source_lang: str
    target_lang: str


class NLLBEngine:
    """Lazy wrapper around :mod:`transformers`' NLLB-200 pipeline."""

    DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._lock = threading.Lock()
        self._pipeline: typing.Any = None
        self._tokenizer = None

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        with self._lock:
            if self._pipeline is not None:
                return
            try:
                import torch
                from transformers import (
                    AutoModelForSeq2SeqLM,
                    AutoTokenizer,
                    pipeline,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "NLLBEngine requires the 'nllb' extra (transformers + torch)."
                ) from exc
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._pipeline = pipeline(
                "translation",
                model=model,
                tokenizer=self._tokenizer,
                device=0 if device == "cuda" else -1,
            )
            logger.info("NLLBEngine loaded model=%s device=%s", self.model_name, device)

    async def translate(self, text: str, target_language: str) -> NLLBResult:
        """Translate ``text`` to ``target_language``.

        ``target_language`` may be a UI-friendly name (e.g. ``"French"``) or an
        NLLB code (e.g. ``"fra_Latn"``).
        """
        if not text or not text.strip():
            return NLLBResult(
                text="", source_lang="auto", target_lang=target_language
            )
        self._ensure_loaded()
        loop = asyncio.get_event_loop()
        target_code = resolve_nllb_code(target_language)
        source_code = "eng_Latn"  # assume English source for NLLB fallback

        def _run() -> NLLBResult:
            assert self._pipeline is not None
            out = self._pipeline(
                text,
                src_lang=source_code,
                tgt_lang=target_code,
                max_length=1024,
            )
            translated = ""
            if isinstance(out, list) and out:
                first = out[0]
                if isinstance(first, dict):
                    translated = str(first.get("translation_text", ""))
            return NLLBResult(
                text=translated.strip(),
                source_lang=source_code,
                target_lang=target_code,
            )

        return await loop.run_in_executor(None, _run)
