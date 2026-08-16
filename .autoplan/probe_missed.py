"""Root-cause probe: which text_recall filter rejects the digital.pdf form lines? (read-only)"""

import io
import statistics
from pathlib import Path

import cv2
import numpy as np

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler
from omniscribe.core import text_recall as tr

ROOT = Path(r"d:\OmniScribe")
MISSED = [
    (0.095, 0.124, 0.726, 0.139, "Student Name (Last, First): ___"),
    (0.095, 0.161, 0.726, 0.176, "Student e-mail address: ___"),
    (0.095, 0.198, 0.726, 0.214, "Student G#: ___"),
    (0.095, 0.235, 0.726, 0.269, "Name of the CS faculty member..."),
]

ph = PDFHandler()
aligner = HybridAligner()
img = None
for batch in ph.convert_batches(str(ROOT / "examples" / "digital.pdf"), batch_size=4, dpi=200, max_image_dim=1024):
    for page_num, im, _b64 in batch:
        if page_num == 0:
            img = im

buf = io.BytesIO()
img.convert("RGB").save(buf, format="PNG")
surya = aligner.get_detected_boxes_batch([buf.getvalue()])[0]
print(f"image size: {img.size}, surya boxes: {len(surya)}")
median_h = statistics.median(b[3] - b[1] for b in surya)
min_height = tr._MIN_HEIGHT_FRACTION * median_h
print(f"median surya height={median_h:.4f} -> min_height={min_height:.4f}")

gray = np.array(img.convert("L"))
h, w = gray.shape
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
kw = tr._clamp(w // tr._DILATION_WIDTH_DIVISOR, tr._KERNEL_W_RANGE)
kh = tr._clamp(h // tr._DILATION_HEIGHT_DIVISOR, tr._KERNEL_H_RANGE)
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
dilated = cv2.dilate(binary, kernel)
count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
print(f"kernel=({kw},{kh}) components={count - 1}")

for mx0, my0, mx1, my1, label in MISSED:
    hits = []
    for i in range(1, count):
        x, y, bw, bh = (int(v) for v in stats[i, :4])
        nx0, ny0, nx1, ny1 = x / w, y / h, (x + bw) / w, (y + bh) / h
        ix0, iy0 = max(nx0, mx0), max(ny0, my0)
        ix1, iy1 = min(nx1, mx1), min(my1, my1) if False else min(ny1, my1)
        if ix1 > ix0 and iy1 > iy0:
            hits.append((i, x, y, bw, bh, nx0, ny0, nx1, ny1))
    if not hits:
        print(f"MISS {label!r}: NO component intersects -> dilation never formed a blob")
        continue
    for i, x, y, bw, bh, nx0, ny0, nx1, ny1 in hits:
        nw, nh = nx1 - nx0, ny1 - ny0
        rect = binary[y : y + bh, x : x + bw]
        density = cv2.countNonZero(rect) / max(1, bw * bh)
        verdicts = []
        if bh < tr._MIN_COMPONENT_HEIGHT_PX:
            verdicts.append(f"REJECT height_px({bh}<{tr._MIN_COMPONENT_HEIGHT_PX})")
        if nw < tr._MIN_ASPECT_RATIO * nh:
            verdicts.append(f"REJECT aspect({nw:.3f}<{tr._MIN_ASPECT_RATIO}*{nh:.3f})")
        if nh < min_height:
            verdicts.append(f"REJECT min_height({nh:.4f}<{min_height:.4f})")
        if nw * nh > tr._MAX_AREA_FRACTION:
            verdicts.append(f"REJECT area({nw * nh:.3f}>{tr._MAX_AREA_FRACTION})")
        if not tr._MIN_INK_DENSITY <= density <= tr._MAX_INK_DENSITY:
            verdicts.append(f"REJECT density({density:.2f})")
        verdicts.append("PASS-filters" if not verdicts else "")
        dedup = tr._overlaps_surya((nx0, ny0, nx1, ny1), list(surya))
        print(
            f"MISS {label!r}: comp#{i} bbox=({nx0:.3f},{ny0:.3f},{nx1:.3f},{ny1:.3f}) "
            f"px={bw}x{bh} density={density:.2f} dedup_reject={dedup} | {'; '.join(v for v in verdicts if v)}"
        )
