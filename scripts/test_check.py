#!/usr/bin/env python3
"""
Test script to check HybridAligner output format.
"""

import argparse
import os
import sys

import pymupdf as fitz

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import setup_sys_path

setup_sys_path()

from omniscribe.core.aligner import HybridAligner


def check_file(filename):
    examples_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
    )
    path = os.path.join(examples_dir, filename)
    if not os.path.exists(path):
        print(f"Skipping {path} (not found)")
        return

    print(f"\nEvaluating {filename}...")
    try:
        aligner = HybridAligner()
        doc = fitz.open(path)
        page = doc[0]
        pix = page.get_pixmap()
        image_bytes = pix.tobytes("png")

        boxes = aligner.get_detected_boxes_batch([image_bytes])[0]
        structured_data = [(box, "") for box in boxes]
        print(f"  Items found: {len(structured_data)}")
        if structured_data:
            print(f"  First item: {structured_data[0]}")
            # Check range
            r = structured_data[0][0]
            if all(0.0 <= x <= 1.0 for x in r):
                print("  Status: OK (Normalized)")
            else:
                print(f"  Status: FAIL (Not Normalized: {r})")

            # Check sorting
            y_iter = [item[0][1] for item in structured_data]  # y0
            is_sorted = all(y_iter[i] <= y_iter[i + 1] for i in range(len(y_iter) - 1))
            print(f"  Sorted by Y: {is_sorted}")
            if not is_sorted:
                print(f"  Y-coords first 10: {y_iter[:10]}")
        else:
            print("  Status: WARNING (No text found)")

    except Exception as e:
        print(f"  Status: ERROR ({e})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "filenames",
        nargs="*",
        default=["digital.pdf", "hybrid.pdf", "handwritten.pdf"],
        help="PDF filenames in examples/ to evaluate (default: digital, hybrid, handwritten).",
    )
    args = parser.parse_args()
    for name in args.filenames:
        check_file(name)
