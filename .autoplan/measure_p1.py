"""Premise gate measurement (read-only): Surya miss rate vs GT fixtures + booster recovery/junk rate.

Uses omniscribe.evaluation.load_ground_truth (axis-order auto-detection) for GT normalization.
"""

from pathlib import Path

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.text_recall import WhitespaceRecallBooster
from omniscribe.evaluation import load_ground_truth

ROOT = Path(r"d:\OmniScribe")
FIX = ROOT / "tests" / "fixtures"
EX = ROOT / "examples"

CASES = [
    ("dense.pdf", "ground_truth_dense.json"),
    ("digital.pdf", "ground_truth_digital.json"),
    ("handwritten.pdf", "ground_truth_handwritten.json"),
    ("hybrid.pdf", "ground_truth_hybrid.json"),
    ("notes.pdf", "ground_truth_notes.json"),
]


def grid_coverage(block, boxes, grid=40):
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


def to_bytes(img):
    import io

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def main():
    ph = PDFHandler()
    aligner = HybridAligner()
    booster = WhitespaceRecallBooster()
    DENSE = 60
    print(f"{'file':<16}{'page':>5}{'blocks':>7}{'missed':>7}{'partial':>8}{'recall%':>8}{'surya':>6}{'extra':>6}{'post':>5}{'flip':>5}{'recov':>6}{'junk':>5}")
    tot = {"blocks": 0, "missed": 0, "extra": 0, "recov": 0, "junk": 0, "flip": 0, "pages": 0}
    for pdf_name, gt_name in CASES:
        gt_blocks, _size = load_ground_truth(FIX / gt_name)
        images = {}
        for batch in ph.convert_batches(str(EX / pdf_name), batch_size=10, dpi=200, max_image_dim=1024):
            for page_num, img, _b64 in batch:
                images[page_num] = img
        page_nums = sorted(images)
        surya_all = aligner.get_detected_boxes_batch([to_bytes(images[p]) for p in page_nums])
        for idx, p_num in enumerate(page_nums):
            img = images[p_num]
            surya = surya_all[idx]
            blocks = [b.bbox for b in gt_blocks if b.page_index == p_num and b.text.strip()]
            texts = {tuple(b.bbox): b.text[:50] for b in gt_blocks if b.page_index == p_num and b.text.strip()}
            extra = booster.supplement(img, list(surya))
            post = len(surya) + len(extra)
            flip_now = len(surya) <= DENSE < post
            missed = partial = recov = junk = 0
            for blk in blocks:
                cov = grid_coverage(blk, surya)
                if cov < 0.5:
                    missed += 1
                    if any(grid_coverage(blk, [e]) >= 0.5 for e in extra):
                        recov += 1
                elif cov < 0.9:
                    partial += 1
            for e in extra:
                if blocks and max(grid_coverage(e, [g]) for g in blocks) < 0.3:
                    junk += 1
            n = len(blocks)
            recall_pct = 100.0 * (n - missed) / n if n else 100.0
            tot["blocks"] += n
            tot["missed"] += missed
            tot["extra"] += len(extra)
            tot["recov"] += recov
            tot["junk"] += junk
            tot["flip"] += int(flip_now)
            tot["pages"] += 1
            print(
                f"{pdf_name:<16}{p_num:>5}{n:>7}{missed:>7}{partial:>8}{recall_pct:>7.0f}%"
                f"{len(surya):>6}{len(extra):>6}{post:>5}{'YES' if flip_now else '-':>5}{recov:>6}{junk:>5}"
            )
            if missed:
                for blk in blocks:
                    if grid_coverage(blk, surya) < 0.5:
                        print(f"    MISSED block bbox={[round(v, 3) for v in blk]} text={texts[tuple(blk)]!r}")
                for e in extra:
                    print(f"    EXTRA box   bbox={[round(v, 3) for v in e]}")
    print(
        f"TOTAL pages={tot['pages']} blocks={tot['blocks']} missed={tot['missed']} "
        f"block-recall={100.0 * (tot['blocks'] - tot['missed']) / tot['blocks']:.0f}% "
        f"extra={tot['extra']} recovered={tot['recov']} junk={tot['junk']} dense-flips={tot['flip']}"
    )


if __name__ == "__main__":
    main()
