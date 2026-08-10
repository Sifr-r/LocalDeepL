"""Top-level orchestrator for the OCR quality trust layer.

Given a page image and the OCR blocks for that page, runs whichever
sub-modules are enabled in :class:`OCrQualitySettings`, applies
calibration, calls :func:`trust_scorer.score` per block, and writes the
results back onto new :class:`DocumentBlock` copies.

Failures in any sub-module degrade to passthrough for the affected
signal — the orchestrator never raises out of :func:`run`. This is a
hard requirement (spec §4) so a broken watermark detector can never
block OCR jobs.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from PIL import Image

from ..document import DocumentBlock
from . import calibration, hallucination, script_detector, trust_scorer, watermark
from .config import OCrQualitySettings
from .events import emit
from .types import HallucinationRisk

_LOG = logging.getLogger(__name__)

_T = TypeVar("_T")


def _safe(
    fn: Callable[[], _T],
    *,
    default: _T,
    sub_module: str,
    fallback_used_box: list[bool],
) -> _T:
    """Run ``fn``, returning ``default`` (and flipping the fallback flag) on any error."""
    try:
        return fn()
    except Exception as exc:
        _LOG.debug("ocr_quality %s sub-module failed: %s", sub_module, exc)
        fallback_used_box[0] = True
        return default


def _bbox_intersects(
    a: list[float] | tuple[float, ...], b: tuple[float, float, float, float]
) -> bool:
    if len(a) != 4 or any(v is None for v in a):
        return False
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def run(
    blocks: list[DocumentBlock],
    page_image: Image.Image | None,
    settings: OCrQualitySettings,
    *,
    model_id: str,
    page_size: tuple[int, int] | None = None,
    cross_check_fn: Callable[[str, tuple[float, float, float, float]], str]
    | None = None,
) -> list[DocumentBlock]:
    """Score ``blocks`` with the trust layer.

    Returns a new list — input blocks are never mutated. When every
    sub-module is off, the returned blocks are byte-identical to the
    inputs (including ``trust_score=None``).
    """
    started = time.monotonic()
    fallback_used_box = [False]

    if not blocks:
        return []

    # Short-circuit when the whole layer is disabled.
    if not settings.any_submodule_enabled():
        return [
            dataclasses.replace(b, trust_score=None, trust_flags=None) for b in blocks
        ]

    # Resolved page size: prefer explicit arg, else derive from image.
    resolved_page_size = page_size
    if resolved_page_size is None and page_image is not None:
        resolved_page_size = page_image.size

    # Sub-module: watermark (page-level — pre-OCR or no-op on block list).
    hit = None
    if settings.watermark_enabled and page_image is not None:
        hit = _safe(
            lambda: watermark.detect(
                page_image,
                aggressiveness=settings.watermark_aggressiveness,
            )[1],
            default=None,
            sub_module="watermark",
            fallback_used_box=fallback_used_box,
        )

    # Sub-module: script_detect — derive page-level script from any block's
    # text, then per-block mismatch flag.
    page_script: str | None = None
    if settings.script_detect_enabled:
        any_text = next((b.text for b in blocks if b.text), "")
        hint = _safe(
            lambda: script_detector.detect(any_text),
            default=None,
            sub_module="script_detect",
            fallback_used_box=fallback_used_box,
        )
        if hint is not None:
            page_script = hint.script

    # Sub-module: hallucination — per block.
    hallucination_risks: list[HallucinationRisk] = [HallucinationRisk.NONE] * len(
        blocks
    )
    if settings.hallucination_enabled:
        for i, block in enumerate(blocks):

            def _eval_block(b: DocumentBlock = block) -> HallucinationRisk:
                bbox_tuple: tuple[float, float, float, float] | None
                if b.bbox is None or len(b.bbox) != 4:
                    bbox_tuple = None
                else:
                    bbox_tuple = (
                        float(b.bbox[0]),
                        float(b.bbox[1]),
                        float(b.bbox[2]),
                        float(b.bbox[3]),
                    )
                return hallucination.evaluate(
                    b.text,
                    bbox_tuple,
                    page_size=resolved_page_size,
                    repetition_window=settings.hallucination_repetition_window,
                    length_plausibility_min=settings.hallucination_length_plausibility_min,
                    cross_check=settings.hallucination_cross_check,
                    cross_check_fn=cross_check_fn,
                    cross_check_threshold=settings.hallucination_cross_check_threshold,
                )

            risk = _safe(
                _eval_block,
                default=HallucinationRisk.LOW,
                sub_module="hallucination",
                fallback_used_box=fallback_used_box,
            )
            assert isinstance(risk, HallucinationRisk)
            hallucination_risks[i] = risk

    # Sub-module: calibration — per block.
    calibrated: list[float] = [
        b.confidence if b.confidence is not None else 0.0 for b in blocks
    ]
    if settings.calibration_enabled:
        for i, block in enumerate(blocks):
            raw = block.confidence if block.confidence is not None else 0.0

            def _calibrate_block(r: float = raw, m: str = model_id) -> float:
                return calibration.calibrate(r, m)

            calibrated[i] = float(
                _safe(
                    _calibrate_block,
                    default=raw,
                    sub_module="calibration",
                    fallback_used_box=fallback_used_box,
                )
            )

    # Compose BlockTrust per block.
    new_blocks: list[DocumentBlock] = []
    watermark_bbox = hit.bbox if hit is not None else None
    for i, block in enumerate(blocks):
        watermark_in_block = (
            watermark_bbox is not None
            and block.bbox is not None
            and _bbox_intersects(block.bbox, watermark_bbox)
        )
        per_block_script_mismatch = False
        if settings.script_detect_enabled and page_script is not None:
            block_hint = script_detector.detect(block.text)
            if block_hint is not None and block_hint.script != page_script:
                # Only count as mismatch when the per-block hint has
                # reasonable confidence.
                per_block_script_mismatch = block_hint.confidence >= 0.5

        verdict = trust_scorer.score(
            calibrated[i],
            hallucination=hallucination_risks[i],
            watermark_in_block=watermark_in_block,
            script_mismatch=per_block_script_mismatch,
        )
        trust_score = verdict.score
        trust_flags = tuple(f.value for f in verdict.flags) if verdict.flags else None
        new_blocks.append(
            dataclasses.replace(
                block,
                trust_score=trust_score,
                trust_flags=trust_flags,
            )
        )

    emit(
        "orchestrator",
        doc_id="-",
        page=-1,
        duration_ms=int((time.monotonic() - started) * 1000),
        decision=f"{len(new_blocks)} blocks",
        fallback_used=fallback_used_box[0],
    )

    return new_blocks


__all__ = ["run"]
