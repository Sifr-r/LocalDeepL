"""Measure whitespace-recall booster impact against ground-truth fixtures.

Runs Surya detection on the ``examples/*.pdf`` corpus, then scores each page
twice: baseline (Surya boxes only) vs booster-ON (Surya + recall extras).
Reports per-page block recall, recovered missed blocks, junk extras, and
dense-threshold flips — the data backing any recall-benefit claim
(plan tasks T7/T3, 2026-08-14-whitespace-recall.md).

Usage:
    uv run python scripts/measure_recall_delta.py
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from omniscribe.confidence_eval import load_ground_truth
from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.recall.whitespace import WhitespaceRecallBooster

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"
DENSE_THRESHOLD = 60

CASES = [
    ("dense.pdf", "ground_truth_dense.json"),
    ("digital.pdf", "ground_truth_digital.json"),
    ("handwritten.pdf", "ground_truth_handwritten.json"),
    ("hybrid.pdf", "ground_truth_hybrid.json"),
    ("notes.pdf", "ground_truth_notes.json"),
]


def grid_coverage(block, boxes, grid: int = 20) -> float:
    """Fraction of a block's sampled interior covered by any box."""
    x0, y0, x1, y1 = block
    n = hit = 0
    for i in range(grid):
        for j in range(grid):
            px = x0 + (i + 0.5) * (x1 - x0) / grid
            py = y0 + (j + 0.5) * (y1 - y0) / grid
            n += 1
            if any(
                bx0 <= px <= bx1 and by0 <= py <= by1 for bx0, by0, bx1, by1 in boxes
            ):
                hit += 1
    return hit / n


def _to_png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    handler = PDFHandler()
    aligner = HybridAligner()
    booster = WhitespaceRecallBooster()
    header = (
        f"{'file':<16}{'page':>5}{'blocks':>7}{'missed':>7}{'recall%':>8}"
        f"{'surya':>6}{'extra':>6}{'post':>5}{'flip':>5}{'recov':>6}{'junk':>5}"
    )
    print(header)
    totals = {
        "pages": 0,
        "blocks": 0,
        "missed": 0,
        "extra": 0,
        "recov": 0,
        "junk": 0,
        "flip": 0,
    }
    for pdf_name, gt_name in CASES:
        gt_blocks, _size = load_ground_truth(FIXTURES / gt_name)
        images: dict[int, object] = {}
        for batch in handler.convert_batches(
            str(EXAMPLES / pdf_name), batch_size=10, dpi=200, max_image_dim=1024
        ):
            for page_num, img, _b64 in batch:
                images[page_num] = img
        page_nums = sorted(images)
        surya_all = aligner.get_detected_boxes_batch(
            [_to_png_bytes(images[p]) for p in page_nums]
        )
        for idx, p_num in enumerate(page_nums):
            surya = list(surya_all[idx])
            extras = booster.supplement(images[p_num], surya)  # type: ignore[arg-type]
            blocks = [
                b.bbox for b in gt_blocks if b.page_index == p_num and b.text.strip()
            ]
            post = len(surya) + len(extras)
            flip = len(surya) <= DENSE_THRESHOLD < post
            missed = recov = junk = 0
            for blk in blocks:
                if grid_coverage(blk, surya) < 0.5:
                    missed += 1
                    if any(grid_coverage(blk, [e]) >= 0.5 for e in extras):
                        recov += 1
            for e in extras:
                if blocks and max(grid_coverage(e, [g]) for g in blocks) < 0.3:
                    junk += 1
            n = len(blocks)
            recall_pct = 100.0 * (n - missed) / n if n else 100.0
            totals["pages"] += 1
            totals["blocks"] += n
            totals["missed"] += missed
            totals["extra"] += len(extras)
            totals["recov"] += recov
            totals["junk"] += junk
            totals["flip"] += int(flip)
            print(
                f"{pdf_name:<16}{p_num:>5}{n:>7}{missed:>7}{recall_pct:>7.0f}%"
                f"{len(surya):>6}{len(extras):>6}{post:>5}{'YES' if flip else '-':>5}"
                f"{recov:>6}{junk:>5}"
            )
    block_recall = 100.0 * (totals["blocks"] - totals["missed"]) / totals["blocks"]
    print(
        f"TOTAL pages={totals['pages']} blocks={totals['blocks']} "
        f"missed={totals['missed']} block-recall={block_recall:.0f}% "
        f"extra={totals['extra']} recovered={totals['recov']} junk={totals['junk']} "
        f"dense-flips={totals['flip']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    main()
