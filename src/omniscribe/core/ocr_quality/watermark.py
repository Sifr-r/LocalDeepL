"""Watermark detection for the OCR quality trust layer.

Lightweight detector: looks for horizontal bands of pixels that look
like a faint watermark (mid-gray on near-white background — DRAFT,
CONFIDENTIAL, page-number stripes, etc.). PIL-only — no OpenCV, no
scipy required — so the trust layer adds zero heavy dependencies.

Always fails open: any exception, oversized image, or absent input
returns the original image unchanged with ``WatermarkHit(bbox=None)``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PIL import Image

from .events import emit
from .types import WatermarkHit

_LOG = logging.getLogger(__name__)

# 20000x20000 is approx 1.6 GB decoded - refuse and pass through.
_MAX_IMAGE_PIXELS = 20000 * 20000
# Watermark pixels are mid-gray: brighter than typical text (<180) but
# darker than paper (>240). Tuned for the 200-240 mid-band.
_WATERMARK_LO = 200
_WATERMARK_HI = 240
# A row counts as a "band row" when this fraction of sampled pixels are
# in the mid-gray watermark range. A clean white page has 0%, a fully
# watermarked band approaches 1.0.
_BAND_ROW_FRACTION = 0.80
# A band must span at least this fraction of the page height.
_MIN_BAND_HEIGHT_FRACTION = 0.02
# How many rows a band must span at minimum to avoid noise spikes.
_MIN_BAND_ROW_COUNT = 3


def _midgray_fraction(image: Image.Image) -> list[float]:
    """Return per-row fraction of pixels in the watermark mid-gray range."""
    w, h = image.size
    gray = image.convert("L")
    pixels = gray.load()
    assert pixels is not None
    sample_step = max(1, w // 64)
    sample_count = (w + sample_step - 1) // sample_step
    fractions: list[float] = []
    for y in range(h):
        mid = 0
        for x in range(0, w, sample_step):
            raw_v = pixels[x, y]
            # PIL pixel access returns ``int | float | tuple[int, ...]``.
            # ``L`` mode is always an ``int``; assert + cast to keep mypy happy.
            assert isinstance(raw_v, int)
            v = raw_v
            if _WATERMARK_LO <= v <= _WATERMARK_HI:
                mid += 1
        fractions.append(mid / sample_count if sample_count else 0.0)
    return fractions


def _largest_band_bbox(
    fractions: list[float], height: int
) -> tuple[float, float, float, float] | None:
    """Find the longest run of consecutive watermark band-rows."""
    if not fractions:
        return None
    best_run = 0
    best_start = -1
    cur_start = -1
    cur_run = 0
    for y, frac in enumerate(fractions):
        if frac >= _BAND_ROW_FRACTION:
            if cur_start == -1:
                cur_start = y
                cur_run = 1
            else:
                cur_run += 1
        else:
            if cur_run > best_run:
                best_run = cur_run
                best_start = cur_start
            cur_start = -1
            cur_run = 0
    if cur_run > best_run:
        best_run = cur_run
        best_start = cur_start
    if best_start < 0 or best_run < _MIN_BAND_ROW_COUNT:
        return None
    height_fraction = best_run / height
    if height_fraction < _MIN_BAND_HEIGHT_FRACTION:
        return None
    y0 = best_start / height
    y1 = (best_start + best_run) / height
    return (0.0, y0, 1.0, y1)


def detect(
    image: Image.Image | None,
    *,
    hint: WatermarkHit | None = None,
    aggressiveness: float = 0.5,
) -> tuple[Image.Image, WatermarkHit | None]:
    """Detect (and optionally mask) a watermark on ``image``.

    Returns the (possibly masked) image and a :class:`WatermarkHit`. When
    nothing is detected, the returned image is byte-identical to the input
    and the hit is ``None``.

    Parameters
    ----------
    image:
        PIL image to inspect. ``None`` is treated as a passthrough.
    hint:
        Caller-supplied hint (e.g. from a previous page). When set, the
        detector trusts the hint over its own output — used by engines
        that already know there's a watermark.
    aggressiveness:
        ``0.0`` → never mask (passthrough even when a hit is found).
        ``1.0`` → aggressively inpaint the band. Intermediate values
        linearly interpolate. Default ``0.5``.
    """
    started = _now_ms()
    try:
        if image is None:
            return image, None  # type: ignore[return-value]
        w, h = image.size
        if w * h > _MAX_IMAGE_PIXELS:
            _LOG.warning(
                "watermark detector skipped: image too large (%dx%d)",
                w,
                h,
            )
            emit(
                "watermark",
                doc_id="-",
                page=-1,
                duration_ms=_now_ms() - started,
                decision="skipped_large",
                fallback_used=True,
            )
            return image, None

        if hint is not None and hint.bbox is not None:
            return _maybe_mask(image, hint.bbox, aggressiveness), hint

        fractions = _midgray_fraction(image)
        bbox = _largest_band_bbox(fractions, h)
        if bbox is None:
            emit(
                "watermark",
                doc_id="-",
                page=-1,
                duration_ms=_now_ms() - started,
                decision="none",
                fallback_used=False,
            )
            return image, None
        hit = WatermarkHit(bbox=bbox, confidence=0.6)
        emit(
            "watermark",
            doc_id="-",
            page=-1,
            duration_ms=_now_ms() - started,
            decision="hit",
            fallback_used=False,
        )
        return _maybe_mask(image, bbox, aggressiveness), hit
    except Exception as exc:
        _LOG.debug("watermark detector failed: %s", exc)
        emit(
            "watermark",
            doc_id="-",
            page=-1,
            duration_ms=_now_ms() - started,
            decision="error",
            fallback_used=True,
        )
        assert image is not None
        return image, None


def _maybe_mask(
    image: Image.Image,
    bbox: Sequence[float],
    aggressiveness: float,
) -> Image.Image:
    """Inpaint the band region with paper-white when ``aggressiveness > 0``."""
    if aggressiveness <= 0.0:
        return image
    x0, y0, x1, y1 = bbox
    w, h = image.size
    px0, py0, px1, py1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
    mask = Image.new("L", image.size, 0)
    band_mask = Image.new(
        "L", (max(1, px1 - px0), max(1, py1 - py0)), int(255 * aggressiveness)
    )
    mask.paste(band_mask, (px0, py0, px1, py1))
    white = Image.new(image.mode, image.size, (255,) * len(image.getbands()))
    return Image.composite(white, image, mask)


def _now_ms() -> int:
    import time

    return int(time.monotonic() * 1000)


__all__ = ["detect"]
