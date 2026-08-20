#!/usr/bin/env python3
"""
Visualize bounding boxes detected by HybridAligner.
"""

import argparse
import io
import os
import sys

import pymupdf as fitz
from PIL import Image, ImageDraw

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import setup_sys_path

setup_sys_path()

from omniscribe.core.aligner import HybridAligner


def visualize_boxes(pdf_filename):
    examples_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
    )
    input_path = os.path.join(examples_dir, pdf_filename)
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        return

    print(f"Processing {pdf_filename}...")

    # Initialize aligner
    aligner = HybridAligner()

    # Load PDF
    doc = fitz.open(input_path)
    page = doc[0]  # Just checking first page
    pix = page.get_pixmap()
    img_bytes = pix.tobytes("png")

    # Create PIL Image for drawing
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Get boxes (batch API with a single-element list)
    boxes = aligner.get_detected_boxes_batch([img_bytes])[0]
    print(f"  Found {len(boxes)} text blocks.")

    for rect in boxes:
        # rect is normalized [nx0, ny0, nx1, ny1]
        nx0, ny0, nx1, ny1 = rect

        # Scale to image dimensions
        x0 = nx0 * width
        y0 = ny0 * height
        x1 = nx1 * width
        y1 = ny1 * height

        # Draw rectangle
        draw.rectangle([x0, y0, x1, y1], outline="red", width=2)

    output_filename = f"bbox_{os.path.splitext(pdf_filename)[0]}.png"
    img.save(output_filename)
    print(f"  Saved visualization to {output_filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdf_filename",
        nargs="?",
        default=None,
        help=(
            "Single PDF filename in examples/ to visualize "
            "(e.g. hybrid.pdf). If omitted, runs against "
            "digital.pdf, hybrid.pdf, handwritten.pdf."
        ),
    )
    args = parser.parse_args()
    if args.pdf_filename:
        visualize_boxes(args.pdf_filename)
    else:
        visualize_boxes("digital.pdf")
        visualize_boxes("hybrid.pdf")
        visualize_boxes("handwritten.pdf")
