from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from omniscribe.core.workflows.base import PageBoxes


# Lightweight per-crop confidence heuristic (no new deps).
def _estimate_confidence(text: str) -> float:
    """Cheap confidence proxy for OCR output.

    Returns a value in [0, 1] based on text quality signals:
    - non-empty + alphabetic characters + multiple words => high
    - single character or empty => low
    - mostly punctuation or digits => medium
    """
    if not text or not text.strip():
        return 0.0
    stripped = text.strip()
    alpha = sum(1 for c in stripped if c.isalpha())
    if alpha == 0:
        return 0.3
    words = stripped.split()
    if len(words) >= 3:
        return 0.85
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
    """Parse a 1-indexed range like '1-3,5,7-9' into sorted 0-indexed pages."""
    pages: set[int] = set()
    try:
        for part in page_str.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s), int(end_s)
                for p in range(start, end + 1):
                    if 1 <= p <= total_pages:
                        pages.add(p - 1)
            else:
                p = int(part)
                if 1 <= p <= total_pages:
                    pages.add(p - 1)
    except ValueError as e:
        raise ValueError(f"Invalid page range syntax: '{page_str}'") from e
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


def _is_refinable(bbox: list[float]) -> bool:
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width > REFINABLE_MIN_WIDTH and height > REFINABLE_MIN_HEIGHT
