from __future__ import annotations

import base64
import io
from collections.abc import Sequence
from typing import TYPE_CHECKING

from PIL import Image

from omniscribe.core.pdf.page_range import parse_page_range as _parse_page_range_spec

if TYPE_CHECKING:
    from omniscribe.core.workflows.base import PageBoxes


# Confidence awarded to well-formed OCR output (multiple words, mostly
# alphabetic). Deliberately above the default quality-loop target (0.98)
# so healthy blocks are never repair candidates; noisy text lands in the
# 0.85 band below it. See spec §3.2.
WELL_FORMED_CONFIDENCE = 0.99


def _estimate_confidence(text: str) -> float:
    """Cheap confidence proxy for OCR output.

    Returns a value in [0, 1] based on text quality signals:
    - empty / whitespace => 0.0
    - no alphabetic characters at all => 0.3
    - 3+ words that are mostly alphabetic => 0.99 (clears the default
      0.98 quality target so healthy text is not re-OCRed)
    - 3+ words with heavy digit/punctuation noise => 0.85
    - 1-2 words with enough alpha => 0.7
    - anything else => 0.4
    """
    if not text or not text.strip():
        return 0.0
    stripped = text.strip()
    alpha = sum(1 for c in stripped if c.isalpha())
    if alpha == 0:
        return 0.3
    words = stripped.split()
    if len(words) >= 3:
        return WELL_FORMED_CONFIDENCE if alpha / len(stripped) >= 0.6 else 0.85
    if len(words) >= 1 and alpha >= 3:
        return 0.7
    return 0.4


# A bbox is "refinable" if it has enough normalized area to be worth a
# per-crop re-OCR pass; below these sizes the LLM round-trip costs more
# than it gains.
REFINABLE_MIN_WIDTH = 0.03
REFINABLE_MIN_HEIGHT = 0.008

# Surya layout detection is batched; this chunk size keeps memory + GPU pressure
# predictable without dominating the detect stage wall clock.
DETECT_CHUNK_SIZE = 10


def parse_page_range(page_str: str, total_pages: int) -> list[int]:
    """Parse a 1-indexed range like '1-3,5,7-9' into sorted 0-indexed pages.

    Thin wrapper over the leaf parser in
    :mod:`omniscribe.core.pdf.page_range` that adds the ``total_pages``
    clamp and the ``ValueError`` on invalid input. Kept as a wrapper
    (rather than a re-export of the leaf function) so the public
    ``parse_page_range`` symbol exposed via ``omniscribe.core.workflows``
    and ``omniscribe.parse_page_range`` retains the
    ``(page_str, total_pages) -> list[int]`` contract that
    :func:`omniscribe.core.workflows.hybrid.HybridEngine.execute` and
    the existing tests depend on.
    """
    ranges = _parse_page_range_spec(page_str)
    if ranges is None:
        raise ValueError(f"Invalid page range syntax: '{page_str}'")
    pages: set[int] = set()
    for start, end in ranges:
        for p in range(start, end + 1):
            if 1 <= p <= total_pages:
                pages.add(p - 1)
    return sorted(pages)


def _decode_page_image(image_b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")


def _normalize_for_dedup(text: str) -> str:
    return " ".join(text.lower().split())


def _drop_refined_duplicates(
    page_boxes: PageBoxes,
    refined_indices: set[int],
    *,
    radius: int = 4,
) -> None:
    for r_idx in sorted(refined_indices):
        r_bbox, r_text = page_boxes[r_idx]
        if not r_text:
            continue
        r_norm = _normalize_for_dedup(r_text)
        if not r_norm:
            continue
        lo = max(0, r_idx - radius)
        hi = min(len(page_boxes), r_idx + radius + 1)
        for o_idx in range(lo, hi):
            if o_idx == r_idx or o_idx in refined_indices:
                continue
            _, o_text = page_boxes[o_idx]
            if not o_text:
                continue
            o_norm = _normalize_for_dedup(o_text)
            if r_norm in o_norm:
                page_boxes[r_idx] = (r_bbox, "")
                break


def _is_refinable(bbox: Sequence[float]) -> bool:
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width > REFINABLE_MIN_WIDTH and height > REFINABLE_MIN_HEIGHT
