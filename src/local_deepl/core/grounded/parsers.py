"""JSON parsers + small helpers for grounded OCR responses.

Three parsers + their shared helpers live here:

- :func:`parse_glm_layout_details` — GLM-OCR / vLLM ``layout_details``
  block list, either flat or nested per page.
- :func:`_parse_grounded_json` — generic JSON-array parser used by
  :mod:`.prompted` (Qwen2.5-VL / Qwen3-VL style responses).

The non-content label set (``_NON_CONTENT_LABELS``) and the
shared ``_clamp`` helper sit here too — single source of truth for
which structural regions get dropped before the pipeline embeds them.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from local_deepl.core.grounded.models import (
    GroundedBlock,
    GroundedResponse,
)

logger = logging.getLogger(__name__)

# Labels we treat as *non-content* — structural regions that aren't meant
# to carry selectable text. Newer grounded responses emit labels like
# "title", "list_item", "form_field", "diagram_node" etc. alongside "text";
# the old handwritten fixture was pure "text" + "image". Instead of allow-
# listing content labels (brittle across schema versions) we deny-list the
# structural ones.
_NON_CONTENT_LABELS = frozenset(
    {
        "empty_line",  # unfilled underline fields
        "signature_line",  # form signature placeholder
        "list_marker",  # lone bullet/dash glyphs
    }
)

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", re.IGNORECASE
)
_BARE_ARRAY = re.compile(r"(\[[\s\S]*\])")


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def parse_glm_layout_details(
    payload_or_json: Any, page_index: int = 0
) -> GroundedResponse:
    """Parse ``layout_details`` emitted by GLM-OCR / vLLM.

    Each block has ``bbox_2d: [x0, y0, x1, y1]`` in pixel coords
    relative to the rendered page image. Accepts either the full JSON
    object or a pre-parsed dict. ``page_index`` specifies which page
    the blocks belong to (single-page calls).
    """
    if isinstance(payload_or_json, str):
        payload_or_json = json.loads(payload_or_json)
    d = payload_or_json

    pages = d.get("data_info", {}).get("pages", [])
    page_sizes = [(int(p["width"]), int(p["height"])) for p in pages]
    if not page_sizes:
        raise ValueError("parse_glm_layout_details: missing data_info.pages")

    # layout_details can be list[list[block]] (per page) or flat list.
    raw = d.get("layout_details", [])
    if raw and isinstance(raw[0], list):
        raw_blocks = raw[page_index] if page_index < len(raw) else []
    else:
        raw_blocks = raw

    blocks: list[GroundedBlock] = []
    pw, ph = page_sizes[page_index]
    for b in raw_blocks:
        if b.get("label") != "text":
            continue
        content = (b.get("content") or "").strip()
        if not content:
            continue
        x0, y0, x1, y1 = b["bbox_2d"]
        blocks.append(
            GroundedBlock(
                bbox=[
                    _clamp(x0 / pw),
                    _clamp(y0 / ph),
                    _clamp(x1 / pw),
                    _clamp(y1 / ph),
                ],
                text=content,
                page_index=page_index,
            )
        )
    return GroundedResponse(blocks=blocks, page_sizes=page_sizes)


def _parse_grounded_json(
    text: str,
    page_idx: int,
    img_w: int,
    img_h: int,
) -> list[GroundedBlock]:
    """Extract a JSON array of ``{bbox_2d, content}`` blocks from a VLM response.

    Handles three observed response shapes:
      1. Bare JSON array (Qwen3-VL)
      2. JSON wrapped in ```json ... ``` fence (Qwen2.5-VL)
      3. JSON with preamble prose before the array
    """
    raw = text.strip()
    if not raw:
        return []

    # Strip code fence if present.
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1)
    elif raw.startswith("```"):
        # Defensive: open fence but closing dropped by truncation.
        raw = raw.lstrip("`").lstrip("json").lstrip().rstrip("`").rstrip()

    # Try a direct parse; fall back to greediest array substring.
    data: Any
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m2 = _BARE_ARRAY.search(raw)
        if not m2:
            logger.warning(
                "Grounded bbox JSON parsing failed on page %d: no array "
                "found in response: %r",
                page_idx,
                raw[:200],
            )
            return []
        try:
            data = json.loads(m2.group(1))
        except json.JSONDecodeError as e:
            logger.warning(
                "Grounded bbox JSON parsing failed on page %d: %s — raw=%r",
                page_idx,
                e,
                raw[:200],
            )
            return []

    if isinstance(data, dict):
        # Some models wrap the array in {"results": [...]} or similar.
        for key in ("results", "blocks", "layout", "layout_details", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]  # single object → one-element list

    if not isinstance(data, list):
        return []

    blocks: list[GroundedBlock] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox_2d") or item.get("bbox")
        content = item.get("content") or item.get("text") or ""
        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        content = str(content).strip()
        if not content:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        blocks.append(
            GroundedBlock(
                bbox=[
                    _clamp(x0 / img_w),
                    _clamp(y0 / img_h),
                    _clamp(x1 / img_w),
                    _clamp(y1 / img_h),
                ],
                text=content,
                page_index=page_idx,
            )
        )
    return blocks


def log_grounded_parse_failure(text: str, page_idx: int, exc: BaseException) -> None:
    """Public hook for callers that catch a parse failure upstream.

    Surfaces a warning when the grounded response payload is not
    parseable, so an operator can spot a regression in the LLM's
    response shape. Kept separate from :func:`_parse_grounded_json` so
    callers parsing the same response shape from a different code path
    get the same observability.
    """
    logger.warning(
        "Grounded bbox JSON parsing failed on page %d: %s — raw=%r",
        page_idx,
        exc,
        text[:200],
    )


__all__ = [
    "_BARE_ARRAY",
    "_JSON_FENCE",
    "_NON_CONTENT_LABELS",
    "_clamp",
    "_parse_grounded_json",
    "parse_glm_layout_details",
]
