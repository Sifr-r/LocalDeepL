"""Sanity probe: inspect digital.pdf GT vs Surya boxes directly (diagnostic, read-only)."""

import io
import json
from pathlib import Path

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler

ROOT = Path(r"d:\OmniScribe")


def to_bytes(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


ph = PDFHandler()
aligner = HybridAligner()
for batch in ph.convert_batches(str(ROOT / "examples" / "digital.pdf"), batch_size=4, dpi=200, max_image_dim=1024):
    for page_num, img, _b64 in batch:
        print("rendered size:", img.size)
        boxes = aligner.get_detected_boxes_batch([to_bytes(img)])[0]
        print(f"surya boxes: {len(boxes)}")
        for b in boxes[:12]:
            print("  S", tuple(round(v, 3) for v in b))

gt = json.loads((ROOT / "tests" / "fixtures" / "ground_truth_digital.json").read_text(encoding="utf-8"))["data"]
pi = gt["data_info"]["pages"][0]
w, h = pi["width"], pi["height"]
print("GT page size:", w, h)
for b in gt["layout"][:8]:
    x0, y0, x1, y1 = b["bbox"]
    print("  G", (round(x0 / w, 3), round(y0 / h, 3), round(x1 / w, 3), round(y1 / h, 3)), repr(b["block_content"][:40]))
