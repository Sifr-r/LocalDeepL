"""Script detection for the OCR quality trust layer.

When the VLM has already returned OCR text, we use Unicode-range
analysis to identify the dominant script — fast (sub-millisecond) and
accurate for the common Latin/CJK/Arabic/Devanagari/Cyrillic split.
When text is not available, we return ``None`` rather than guess.

The detector never raises: any malformed input returns ``None``.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

from .types import ScriptHint

# Unicode ranges per https://www.unicode.org/charts/ — broad buckets only.
_SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "Latin": (0x0041, 0x024F),
    "CJK": (0x4E00, 0x9FFF),
    "Hiragana": (0x3040, 0x309F),
    "Katakana": (0x30A0, 0x30FF),
    "Arabic": (0x0600, 0x06FF),
    "Devanagari": (0x0900, 0x097F),
    "Cyrillic": (0x0400, 0x04FF),
    "Greek": (0x0370, 0x03FF),
    "Hebrew": (0x0590, 0x05FF),
    "Hangul": (0xAC00, 0xD7AF),
}


def _classify_char(ch: str) -> str | None:
    """Return the script bucket for ``ch``, or ``None`` for neutral chars."""
    if not ch.isalpha():
        return None
    cp = ord(ch)
    for script, (lo, hi) in _SCRIPT_RANGES.items():
        if lo <= cp <= hi:
            return script
    # Fall back to Unicode's own database for less common scripts.
    try:
        name = unicodedata.name(ch, "")
    except ValueError:
        return None
    if "CJK" in name:
        return "CJK"
    if "HIRAGANA" in name:
        return "Hiragana"
    if "KATAKANA" in name:
        return "Katakana"
    if "ARABIC" in name:
        return "Arabic"
    if "DEVANAGARI" in name:
        return "Devanagari"
    if "CYRILLIC" in name:
        return "Cyrillic"
    if "GREEK" in name:
        return "Greek"
    if "HEBREW" in name:
        return "Hebrew"
    if "HANGUL" in name:
        return "Hangul"
    if "LATIN" in name:
        return "Latin"
    return None


def detect(text: str | None) -> ScriptHint | None:
    """Return the dominant script of ``text`` or ``None`` if undetectable.

    Parameters
    ----------
    text:
        OCR result for the page. ``None`` or empty → ``None``.
    """
    if not text:
        return None
    counts: Counter[str] = Counter()
    for ch in text:
        bucket = _classify_char(ch)
        if bucket is not None:
            counts[bucket] += 1
    if not counts:
        return None
    primary, primary_count = counts.most_common(1)[0]
    total = sum(counts.values())
    confidence = primary_count / total if total else 0.0
    # Group CJK + Hiragana + Katakana + Hangul under the "CJK" label.
    if primary in {"Hiragana", "Katakana", "Hangul"}:
        primary = "CJK"
    return ScriptHint(script=primary, confidence=confidence)


__all__ = ["detect"]
