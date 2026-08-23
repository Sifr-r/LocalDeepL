#!/usr/bin/env python3
"""Unified bounding-box visualization CLI for OCR debugging.

Subcommands:

- ``boxes``   — draw Surya detection boxes over the first page of a PDF
                in ``examples/`` (formerly ``visualize_bboxes.py``).
- ``compare`` — side-by-side raw Surya boxes vs DP-aligned output
                (formerly ``visualize_comparison.py``).
- ``align``   — aligned boxes with per-block text labels
                (formerly ``debug_alignment.py``).
- ``image``   — run the hybrid pipeline on an image input and dump the
                raw LLM lines, Surya boxes, and embedded word positions
                (formerly ``debug_image_input.py``).

Usage:
    uv run python scripts/visualize.py boxes hybrid.pdf
    uv run python scripts/visualize.py compare examples/hybrid.pdf compare.png
    uv run python scripts/visualize.py align examples/hybrid.pdf
    uv run python scripts/visualize.py image examples/image.png out.pdf

Heavy dependencies (Surya, PIL, pymupdf) are imported lazily inside the
subcommands so ``--help`` and the import smoke test stay fast.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
from collections import Counter

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import PROJECT_ROOT, setup_sys_path

setup_sys_path()

EXAMPLES_DIR = PROJECT_ROOT / "examples"
_DEFAULT_BOXES_SAMPLES = ("digital.pdf", "hybrid.pdf", "handwritten.pdf")


def _draw_boxes(
    draw, boxes, width: int, height: int, *, outline: str, line_width: int = 2
) -> None:
    """Draw normalized ``[nx0, ny0, nx1, ny1]`` boxes scaled to image dims."""
    for nx0, ny0, nx1, ny1 in boxes:
        draw.rectangle(
            [nx0 * width, ny0 * height, nx1 * width, ny1 * height],
            outline=outline,
            width=line_width,
        )


def cmd_boxes(args: argparse.Namespace) -> None:
    """Visualize Surya detection boxes for PDFs in ``examples/``."""
    import pymupdf as fitz
    from PIL import Image, ImageDraw

    from omniscribe.core.aligner import HybridAligner

    names = [args.pdf_filename] if args.pdf_filename else list(_DEFAULT_BOXES_SAMPLES)
    aligner = HybridAligner()

    for pdf_filename in names:
        input_path = EXAMPLES_DIR / pdf_filename
        if not input_path.exists():
            print(f"File not found: {input_path}")
            continue

        print(f"Processing {pdf_filename}...")
        doc = fitz.open(str(input_path))
        page = doc[0]  # first page only
        img_bytes = page.get_pixmap().tobytes("png")

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        width, height = img.size

        boxes = aligner.get_detected_boxes_batch([img_bytes])[0]
        print(f"  Found {len(boxes)} text blocks.")
        _draw_boxes(draw, boxes, width, height, outline="red")

        output_filename = f"bbox_{os.path.splitext(pdf_filename)[0]}.png"
        img.save(output_filename)
        print(f"  Saved visualization to {output_filename}")


async def cmd_compare(args: argparse.Namespace) -> None:
    """Side-by-side comparison of raw Surya boxes vs aligned output."""
    import pymupdf as fitz
    from PIL import Image, ImageDraw

    from omniscribe.core.aligner import HybridAligner
    from omniscribe.core.ocr import OCRProcessor

    print(f"Processing {args.input_pdf}...")

    # 1. Convert first page to image.
    doc = fitz.open(args.input_pdf)
    img_data = doc[0].get_pixmap(dpi=200).tobytes("png")

    original_img = Image.open(io.BytesIO(img_data)).convert("RGB")
    width, height = original_img.size

    # Compress to JPEG for the LLM; downscale to avoid 400 Bad Request.
    max_dim = 1500
    if width > max_dim or height > max_dim:
        original_img.thumbnail((max_dim, max_dim))
    buffer = io.BytesIO()
    original_img.save(buffer, format="JPEG", quality=50)
    jpeg_bytes = buffer.getvalue()
    print(f"Compressed Image Size: {len(jpeg_bytes) / 1024:.2f} KB")

    # 2. Surya layout via the batch API with a single-element list.
    aligner = HybridAligner()
    print("Running Surya Detection...")
    batch = await asyncio.to_thread(aligner.get_detected_boxes_batch, [img_data])
    structured_data = [(box, "") for box in batch[0]]

    # 3. LLM OCR (processor expects a base64 string).
    processor = OCRProcessor()
    print("Running LLM OCR...")
    try:
        b64_img = base64.b64encode(jpeg_bytes).decode("utf-8")
        llm_text_lines = await processor.perform_ocr(b64_img)
        print(f"LLM Response: {len(llm_text_lines)} lines found.")
    except Exception as e:
        print(f"LLM Failed: {e}. Alignment will run against zero lines.")
        llm_text_lines = []

    # 4. Hybrid alignment.
    print("Running Hybrid Alignment...")
    final_output = aligner.align_text(structured_data, llm_text_lines)

    img_raw = original_img.copy()
    _draw_boxes(
        ImageDraw.Draw(img_raw),
        [r for r, _ in structured_data],
        width,
        height,
        outline="red",
    )

    img_hybrid = original_img.copy()
    _draw_boxes(
        ImageDraw.Draw(img_hybrid),
        [r for r, _ in final_output],
        width,
        height,
        outline="#00ff00",
        line_width=3,
    )

    gap = 50
    comparison_img = Image.new("RGB", (width * 2 + gap, height), color="white")
    comparison_img.paste(img_raw, (0, 0))
    comparison_img.paste(img_hybrid, (width + gap, 0))

    draw = ImageDraw.Draw(comparison_img)
    draw.text((10, 10), "Before: Raw Surya Boxes", fill="red")
    draw.text((width + gap + 10, 10), "After: Aligned (Gap Filling)", fill="#00aa00")

    comparison_img.save(args.output_image)
    print(f"Comparison saved to {args.output_image}")


def cmd_align(args: argparse.Namespace) -> None:
    """Visualize alignment between Surya boxes and LLM text with labels."""
    from PIL import Image, ImageDraw, ImageFont

    from omniscribe.core.aligner import HybridAligner
    from omniscribe.core.ocr import OCRProcessor
    from omniscribe.core.pdf import PDFHandler

    print(f"Debug Alignment for: {args.pdf_path}")

    pdf_handler = PDFHandler()
    ocr_processor = OCRProcessor()
    hybrid_aligner = HybridAligner()

    print("Converting PDF to images...")
    images_dict = pdf_handler.convert_to_images(args.pdf_path)

    # First page only.
    page_num = 0
    if page_num not in images_dict:
        print("No page 0 found.")
        return

    print("Processing Page 1...")
    image_base64 = images_dict[page_num]
    image_bytes = base64.b64decode(image_base64)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = img.size
    print(f"Image Size: {width}x{height}")

    print("Running Surya Layout...")
    boxes = hybrid_aligner.get_detected_boxes_batch([image_bytes])[0]
    structured_data = [(box, "") for box in boxes]
    print(f"Surya found {len(structured_data)} boxes.")

    print("Running LLM OCR...")
    llm_lines = asyncio.run(ocr_processor.perform_ocr(image_base64))
    print(f"LLM found {len(llm_lines)} lines.")

    print("Aligning...")
    aligned_data = hybrid_aligner.align_text(structured_data, llm_lines)
    print(f"Aligned into {len(aligned_data)} blocks.")

    draw = ImageDraw.Draw(img)
    try:
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "arial.ttf", 15
        )
    except Exception:
        font = ImageFont.load_default()

    for i, (rect, text) in enumerate(aligned_data):
        nx0, ny0, nx1, ny1 = rect
        x0, y0 = nx0 * width, ny0 * height
        draw.rectangle([x0, y0, nx1 * width, ny1 * height], outline="green", width=2)
        if text:
            draw.text((x0, y0 - 15), f"{i}: {text}", fill="red", font=font)

    output_filename = f"debug_align_{os.path.basename(args.pdf_path)}.png"
    img.save(output_filename)
    print(f"Saved debug image to {output_filename}")


async def cmd_image(args: argparse.Namespace) -> None:
    """Run the hybrid pipeline on an image and dump every intermediate."""
    import pymupdf as fitz
    from PIL import Image, ImageDraw

    from omniscribe import HybridAligner, OCRPipeline, OCRProcessor, PDFHandler

    pipeline = OCRPipeline(
        aligner=(aligner := HybridAligner()),
        ocr_processor=OCRProcessor(),
        pdf_handler=PDFHandler(),
    )

    # Disable refine so we see raw DP output.
    pages_text = await pipeline.run(
        args.image_path, args.output_pdf, dpi=200, refine=False
    )
    print("\n=== LLM lines per page ===")
    for p, lines in pages_text.items():
        print(f"page {p}: {len(lines)} lines")
        repeats = [(k, v) for k, v in Counter(lines).items() if v > 3]
        if repeats:
            print(f"  REPETITION DETECTED: {repeats[:5]}")
        for i, line in enumerate(lines[:30]):
            print(f"  [{i}] {line!r}")
        if len(lines) > 30:
            print(f"  ... [{len(lines) - 30} more lines]")
            for i, line in enumerate(lines[-5:]):
                print(f"  [{len(lines) - 5 + i}] {line!r}")

    # Visualize Surya boxes on the source image.
    img = Image.open(args.image_path).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    boxes = aligner.get_detected_boxes_batch([buf.getvalue()])[0]
    print(f"\n=== Surya boxes: {len(boxes)} ===")
    for i, b in enumerate(boxes):
        print(f"  [{i}] {b}")

    draw_img = img.copy()
    _draw_boxes(
        ImageDraw.Draw(draw_img), boxes, *draw_img.size, outline="red", line_width=3
    )
    boxes_png = os.path.splitext(args.output_pdf)[0] + "_boxes.png"
    draw_img.save(boxes_png)
    print(f"\nSaved Surya bbox visualization -> {boxes_png}")

    # Inspect text positions in the output PDF — word level (not block grouped).
    out = fitz.open(args.output_pdf)
    print("\n=== Output PDF words ===")
    for pn, page in enumerate(out):
        print(f"page {pn} size={page.rect}")
        for x0, y0, x1, y1, w, *_ in page.get_text("words"):
            print(f"  bbox=({x0:6.1f},{y0:6.1f},{x1:6.1f},{y1:6.1f}) word={w!r}")
    out.close()

    # Run align_text directly to inspect post-DP mapping.
    aligned = aligner.align_text([(b, "") for b in boxes], pages_text[0])
    print("\n=== Aligned (box, text) pairs (raw DP, no refine) ===")
    for i, (bbox, text) in enumerate(aligned):
        print(f"  [{i}] {bbox} -> {text!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_boxes = sub.add_parser(
        "boxes", help="Draw Surya detection boxes for a PDF in examples/"
    )
    p_boxes.add_argument(
        "pdf_filename",
        nargs="?",
        default=None,
        help=(
            "Single PDF filename in examples/ to visualize (e.g. hybrid.pdf). "
            "If omitted, runs against digital.pdf, hybrid.pdf, handwritten.pdf."
        ),
    )
    p_boxes.set_defaults(func=lambda a: cmd_boxes(a))

    p_compare = sub.add_parser(
        "compare", help="Side-by-side raw Surya boxes vs aligned output"
    )
    p_compare.add_argument("input_pdf", help="Path to the input PDF.")
    p_compare.add_argument("output_image", help="Path to the output comparison image.")
    p_compare.set_defaults(func=lambda a: asyncio.run(cmd_compare(a)))

    p_align = sub.add_parser("align", help="Aligned boxes with per-block text labels")
    p_align.add_argument(
        "pdf_path",
        nargs="?",
        default="examples/hybrid.pdf",
        help="Path to the PDF to debug (default: examples/hybrid.pdf).",
    )
    p_align.set_defaults(func=lambda a: cmd_align(a))

    p_image = sub.add_parser(
        "image", help="Full-pipeline debug dump for an image input"
    )
    p_image.add_argument("image_path", help="Path to the input image (PNG/JPG).")
    p_image.add_argument("output_pdf", help="Path to the output PDF.")
    p_image.set_defaults(func=lambda a: asyncio.run(cmd_image(a)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
