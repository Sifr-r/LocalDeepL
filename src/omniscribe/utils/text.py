"""Shared text normalization helpers.

The two callsites that need consistent text matching
(``confidence_eval._normalize_text`` for similarity scoring and
``core.ocr.filters._is_fallback_response`` for hallucination pattern
detection) previously each defined their own ad-hoc lowercase + strip
pass. Sprint 1 / L-7 audit fix: consolidate the common shape here so
the canonical "lowercase + collapse whitespace + strip markdown-ish
punctuation" rule has a single owner.

The legacy call-sites keep their existing behaviour exactly; the
shared helper is layered on top of the more-specialized
``_is_fallback_response`` rules (which need ``_trim`` character-class
stripping that the similarity helper does not).
"""
from __future__ import annotations

import re

# Whitespace collapse: any run of 1+ whitespace characters becomes a
# single space. ``\s`` matches ASCII + Unicode whitespace, which is the
# right default for OCR output (curly quotes etc. are not whitespace).
_WS = re.compile(r"\s+")

# Markdown-ish punctuation that does NOT carry lexical meaning for OCR
# similarity: bold/italic/heading markers + list markers + backticks.
# The hyphen-minus is included so OCR artefacts like ``**- bullet**``
# collapse to ``bullet``. Code-fence backticks are stripped.
_MD_PUNCT = re.compile(r"[*_`#\-]+")


def normalize_text(s: str) -> str:
    """Lowercase, strip markdown-ish punctuation, collapse whitespace.

    Used by :func:`omniscribe.confidence_eval.text_similarity` and the
    ``_drop_refined_duplicates`` post-refine dedup pass. Pure function;
    no I/O. Stripping the trailing ``_MD_PUNCT``-set punctuation also
    keeps the output stable across OCR text that includes stray
    formatting markers (LM Studio OCR rarely emits these, but the
    local VLM OCR stack does).
    """
    s = s.lower()
    s = _MD_PUNCT.sub(" ", s)
    s = _WS.sub(" ", s)
    return s.strip()


__all__ = ["normalize_text"]
