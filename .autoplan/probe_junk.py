"""Dump booster extras with density + GT proximity for the junk-heavy pages (read-only)."""

import io
from pathlib import Path

import cv2
import numpy as np

from omniscribe.core import text_recall as tr
from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler
from omniscribe.evaluation import load_ground_truth

ROOT = Path(r"d:\OmniScribe")
TARGETS = [("notes.pdf", "ground_truth_notes.json", [15, 3, 5])]


def grid_coverage(block, boxes, grid=20):
    x0, y0, x1, y1 = block
    n = hit = 0
    for i in range(grid):
        for j in range(grid):
            px = x0 + (i + 0.5) * (x1 - x0) / grid
            py = y0 + (j + 0.5) * (y1 - y0) / grid
            n += 1
            if any(bx0 <= px <= bx1 and by0 <= py <= by1 for bx0, by0, bx1, by1 in boxes):
                hit += 1
    return hit / n


ph = PDFHandler()
aligner = HybridAligner()
for pdf, gt_name, pages in TARGETS:
    gt_blocks, _ = load_ground_truth(ROOT / "tests" / "fixtures" / gt_name)
    images = {}
    for batch in ph.convert_batches(str(ROOT / "examples" / pdf), batch_size=10, dpi=200, max_image_dim=1024):
        for pn, im, _b64 in batch:
            images[pn] = im
    wanted = [p for p in pages if p in images]
    pngs = []
    for p in wanted:
        buf = io.BytesIO()
        images[p].convert("RGB").save(buf, format="PNG")
        pngs.append(buf.getvalue())
    surya_all = aligner.get_detected_boxes_batch(pngs)
    booster = tr.WhitespaceRecallBooster()
    for idx, p in enumerate(wanted):
        img = images[p]
        surya = list(surya_all[idx])
        extras = booster.supplement(img, surya)
        gray = np.array(img.convert("L"))
        h, w = gray.shape
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        blocks = [b.bbox for b in gt_blocks if b.page_index == p and b.text.strip()]
        print(f"--- {pdf} page {p}: surya={len(surya)} extras={len(extras)} ---")
        for e in extras:
            x0, y0, x1, y1 = e
            px0, py0, px1, py1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
            rect = binary[py0:py1, px0:px1]
            density = cv2.countNonZero(rect) / max(1, rect.size)
            best = max((grid_coverage(e, [g]) for g in blocks), default=0.0)
            nearest = ""
            if blocks:
                gi = max(range(len(blocks)), key=lambda k: grid_coverage(e, [blocks[k]]))
                texts = [b.text for b in gt_blocks if b.page_index == p and b.text.strip()]
                nearest = texts[gi][:45]
            print(f"  extra bbox={[round(v, 3) for v in e]} density={density:.2f} gt_cov={best:.2f} nearest_gt={nearest!r}")
