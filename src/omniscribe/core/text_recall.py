"""Secondary whitespace-based text discovery for the hybrid pipeline.

Surya layout detection occasionally misses individual text lines; a missed
box means lost text on dense pages and mis-placed text on sparse pages.
This module masks away a rendered page's whitespace (binarize + invert),
merges the remaining ink into line blobs via horizontal dilation, and
returns conservative candidate boxes for regions Surya did not detect.
``HybridEngine._detect_layout`` merges them into the detected boxes before
dense selection, OCR, and DP alignment.
"""

from __future__ import annotations

import logging
import os
import statistics
from dataclasses import dataclass

from PIL import Image

from omniscribe.core.document import BBox

logger = logging.getLogger(__name__)

_ENV_RECALL = "OMNISCRIBE_WHITESPACE_RECALL"
_DISABLE_VALUES = {"0", "false", "no", "off"}

# Horizontal dilation kernel sizing (ratios of page dimensions, clamped).
# The kernel must bridge inter-character gaps without fusing stacked lines.
_DILATION_WIDTH_DIVISOR = 48
_DILATION_HEIGHT_DIVISOR = 150
_KERNEL_W_RANGE = (7, 35)
_KERNEL_H_RANGE = (3, 11)

# Conservative candidate filters.
_MIN_ASPECT_RATIO = 2.0
_MIN_INK_DENSITY = 0.10
_MAX_INK_DENSITY = 0.75
_MIN_HEIGHT_FRACTION = 0.45
_FALLBACK_MIN_HEIGHT = 0.006
_MAX_AREA_FRACTION = 0.25
# Post-dilation hairline rules land at ~3-8 px while real text lines render
# at ~10 px or more at every supported rasterization size, so an absolute
# pixel floor rejects rules that survive the density check.
_MIN_COMPONENT_HEIGHT_PX = 10

# Dedup against Surya boxes. Containment catches a candidate that is mostly
# inside an existing box (a partial duplicate); IoU catches a candidate that
# nearly coincides with one even if neither fully contains the other.
_MAX_CONTAINMENT = 0.5
_MAX_IOU = 0.3


@dataclass(frozen=True, slots=True)
class WhitespaceRecallOptions:
    enabled: bool = True

    @classmethod
    def from_env(cls) -> WhitespaceRecallOptions:
        """Seed from ``OMNISCRIBE_WHITESPACE_RECALL`` (default on).

        Only explicit disable values (``0``/``false``/``no``/``off``,
        case-insensitive) turn the pass off; unset or unrecognized values
        keep it enabled.
        """
        raw = os.environ.get(_ENV_RECALL, "").strip().lower()
        return cls(enabled=raw not in _DISABLE_VALUES)


class WhitespaceRecallBooster:
    """Recovers text-line boxes Surya missed via whitespace masking.

    Requires ``opencv-python-headless`` and ``numpy`` at runtime (the
    ``preprocessing`` extra). When they are missing the booster logs one
    warning and returns no boxes, leaving pipeline output unchanged.
    """

    def __init__(self, options: WhitespaceRecallOptions | None = None) -> None:
        self.options = options or WhitespaceRecallOptions()
        self._cv2_warned = False

    def supplement(self, image: Image.Image, surya_boxes: list[BBox]) -> list[BBox]:
        """Return new text-line boxes not already covered by ``surya_boxes``.

        Returns only the *additional* boxes; the caller appends them. Empty
        when disabled, when cv2 is unavailable, or when nothing survives
        the filters.
        """
        if not self.options.enabled:
            return []
        try:
            import cv2
            import numpy as np
        except ImportError:
            if not self._cv2_warned:
                logger.warning(
                    "Whitespace recall disabled: opencv is not installed "
                    "(install the `preprocessing` extra to enable)."
                )
                self._cv2_warned = True
            return []

        gray = np.array(image.convert("L"))
        if gray.size == 0:
            return []
        h, w = gray.shape
        # Invert so ink is foreground and whitespace is masked away.
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        kw = _clamp(w // _DILATION_WIDTH_DIVISOR, _KERNEL_W_RANGE)
        kh = _clamp(h // _DILATION_HEIGHT_DIVISOR, _KERNEL_H_RANGE)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
        dilated = cv2.dilate(binary, kernel)

        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            dilated, connectivity=8
        )
        if count <= 1:
            return []

        if surya_boxes:
            median_h = statistics.median(b[3] - b[1] for b in surya_boxes)
            min_height = _MIN_HEIGHT_FRACTION * median_h
        else:
            min_height = _FALLBACK_MIN_HEIGHT

        candidates: list[BBox] = []
        for i in range(1, count):
            x, y, bw, bh = (int(v) for v in stats[i, :4])
            if bh < _MIN_COMPONENT_HEIGHT_PX:
                continue
            nx0, ny0 = x / w, y / h
            nx1, ny1 = (x + bw) / w, (y + bh) / h
            nw, nh = nx1 - nx0, ny1 - ny0
            if nw < _MIN_ASPECT_RATIO * nh:
                continue
            if nh < min_height or nw * nh > _MAX_AREA_FRACTION:
                continue
            # Ink density on the PRE-dilation mask: dilated blobs are nearly
            # solid, real glyph lines sit ~0.2-0.6, solid rules ~1.0.
            rect = binary[y : y + bh, x : x + bw]
            density = cv2.countNonZero(rect) / max(1, bw * bh)
            if not _MIN_INK_DENSITY <= density <= _MAX_INK_DENSITY:
                continue
            candidates.append((nx0, ny0, nx1, ny1))

        return [c for c in candidates if not _overlaps_surya(c, surya_boxes)]


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    lo, hi = bounds
    return max(lo, min(hi, value))


def _overlaps_surya(candidate: BBox, surya_boxes: list[BBox]) -> bool:
    """True when the candidate is already explained by a Surya box."""
    cx0, cy0, cx1, cy1 = candidate
    c_area = max(1e-9, (cx1 - cx0) * (cy1 - cy0))
    for bx0, by0, bx1, by1 in surya_boxes:
        ix0, iy0 = max(cx0, bx0), max(cy0, by0)
        ix1, iy1 = min(cx1, bx1), min(cy1, by1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        inter = (ix1 - ix0) * (iy1 - iy0)
        if inter / c_area >= _MAX_CONTAINMENT:
            return True
        b_area = max(1e-9, (bx1 - bx0) * (by1 - by0))
        if inter / (c_area + b_area - inter) >= _MAX_IOU:
            return True
    return False
