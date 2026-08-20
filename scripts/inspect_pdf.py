#!/usr/bin/env python3
"""
Inspect PDF metadata and dimensions.
"""

import argparse
import os
import sys

import pymupdf as fitz

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import setup_sys_path

setup_sys_path()


def inspect_pdf(filename):
    examples_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
    )
    path = os.path.join(examples_dir, filename)
    print(f"\nInspecting {filename}...")
    doc = fitz.open(path)
    page = doc[0]
    print(f"  Rotation: {page.rotation}")
    print(f"  MediaBox: {page.mediabox}")
    print(f"  CropBox:  {page.cropbox}")
    print(f"  Rect:     {page.rect}")

    # Check image size
    pix = page.get_pixmap()
    print(f"  Pixmap:   {pix.width} x {pix.height}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "filenames",
        nargs="*",
        default=["hybrid.pdf", "digital.pdf", "handwritten.pdf"],
        help="PDF filenames in examples/ to inspect (default: hybrid, digital, handwritten).",
    )
    args = parser.parse_args()
    for name in args.filenames:
        inspect_pdf(name)
