#!/usr/bin/env python3
"""Unified document inspection CLI for OmniScribe outputs.

Subcommands:

- ``pdf``    — inspect PDF metadata and dimensions of ``examples/`` files
               (formerly ``inspect_pdf.py``).
- ``lines``  — dump every word and its bbox from an output PDF, grouped
               into visual lines and sorted by y (formerly
               ``inspect_grounded_lines.py``).
- ``verify`` — verify that an OCR output PDF contains searchable,
               sensibly-distributed text (formerly ``verify_output.py``).
- ``raw``    — dump the raw LLM lines per page for a PDF/image input,
               no DP alignment, no embed (formerly ``debug_llm_raw.py``).

Usage:
    uv run python scripts/inspect_doc.py pdf hybrid.pdf digital.pdf
    uv run python scripts/inspect_doc.py lines output_ocr.pdf
    uv run python scripts/inspect_doc.py verify output_ocr.pdf
    uv run python scripts/inspect_doc.py raw examples/hybrid.pdf

Heavy dependencies (pymupdf, omniscribe) are imported lazily inside the
subcommands so ``--help`` and the import smoke test stay fast.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

# Force UTF-8 stdout on Windows so unicode in OCR'd text doesn't blow up.
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import PROJECT_ROOT, setup_sys_path

setup_sys_path()

EXAMPLES_DIR = PROJECT_ROOT / "examples"
_DEFAULT_PDF_SAMPLES = ("hybrid.pdf", "digital.pdf", "handwritten.pdf")
_DEFAULT_VERIFY_KEYWORDS = ("Algorithms", "computational", "finite", "mapped")


def cmd_pdf(args: argparse.Namespace) -> None:
    """Inspect PDF metadata and dimensions."""
    import pymupdf as fitz

    for filename in args.filenames or list(_DEFAULT_PDF_SAMPLES):
        path = EXAMPLES_DIR / filename
        print(f"\nInspecting {filename}...")
        doc = fitz.open(str(path))
        page = doc[0]
        print(f"  Rotation: {page.rotation}")
        print(f"  MediaBox: {page.mediabox}")
        print(f"  CropBox:  {page.cropbox}")
        print(f"  Rect:     {page.rect}")

        pix = page.get_pixmap()
        print(f"  Pixmap:   {pix.width} x {pix.height}")
        doc.close()


def _flush_line(
    line_words: list[str],
    line_x: tuple[float, float] | None,
    line_y: float | None,
) -> None:
    if line_words and line_x is not None and line_y is not None:
        x0, x1 = line_x
        print(
            f"  y={line_y:6.1f} x=({x0:6.1f},{x1:6.1f}) text={' '.join(line_words)!r}"
        )


def cmd_lines(args: argparse.Namespace) -> None:
    """Dump every word and its bbox from an output PDF, sorted by y."""
    import pymupdf as fitz

    doc = fitz.open(args.pdf_path)
    for pn, page in enumerate(doc):
        words = list(page.get_text("words"))
        # Group words by approximate baseline (y0 rounded to 5pt).
        words.sort(key=lambda w: (round(w[1] / 5) * 5, w[0]))

        prev_y: float | None = None
        line_words: list[str] = []
        line_x: tuple[float, float] | None = None
        line_y: float | None = None

        print(f"page {pn}:")
        for x0, y0, x1, _y1, w, *_ in words:
            row_y = round(y0 / 5) * 5
            if prev_y is None or row_y != prev_y:
                _flush_line(line_words, line_x, line_y)
                line_words = [w]
                line_x = (x0, x1)
                line_y = y0
            else:
                line_words.append(w)
                lx0, lx1 = line_x  # type: ignore[misc]
                line_x = (min(lx0, x0), max(lx1, x1))
            prev_y = row_y
        _flush_line(line_words, line_x, line_y)
    doc.close()


def cmd_verify(args: argparse.Namespace) -> None:
    """Verify that an OCR output PDF contains searchable text."""
    import pymupdf as fitz

    print(f"Verifying '{args.pdf_path}'...")
    try:
        doc = fitz.open(args.pdf_path)
        text_found = False
        full_text = ""
        positions: list[tuple[float, float]] = []

        for i, page in enumerate(doc):
            # get_text("words") returns (x0, y0, x1, y1, "word", block, line, word_no)
            words = page.get_text("words")
            if words:
                text_found = True
                for w in words:
                    full_text += w[4] + " "
                    positions.append((w[0], w[1]))

            print(f"--- Page {i + 1} Stats ---")
            print(f"Word count: {len(words)}")
            if words:
                y_vals = sorted(w[1] for w in words)
                print(f"Y-coordinate samples: {y_vals[:: max(1, len(y_vals) // 5)]}")
            print("-----------------------------")

        doc.close()

        if not text_found:
            print("FAILURE: No text found in PDF.")
            sys.exit(1)

        # Positions must be distributed (not all clustered near one y).
        y_coords = [p[1] for p in positions]
        if not y_coords:
            print("FAILURE: No words.")
            sys.exit(1)

        min_y, max_y = min(y_coords), max(y_coords)
        print(f"Y-coordinate range: {min_y} - {max_y}")

        if max_y - min_y < 10:
            print("WARNING: Text seems clustered vertically (bad distribution).")

        keywords = args.keywords or list(_DEFAULT_VERIFY_KEYWORDS)
        found_keywords = [k for k in keywords if k.lower() in full_text.lower()]
        print(f"Keywords found: {found_keywords}")

        if found_keywords:
            print("SUCCESS: Text content verified.")
        else:
            print("FAILURE: Text content missing keywords.")
            sys.exit(1)

    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)


async def cmd_raw(args: argparse.Namespace) -> None:
    """Dump the raw LLM lines per page for a PDF/image input."""
    from omniscribe import OCRProcessor, PDFHandler

    handler = PDFHandler()
    ocr = OCRProcessor()
    images = await asyncio.to_thread(handler.convert_to_images, args.input_path)

    for page_num in sorted(images):
        print(f"\n=== page {page_num} ===")
        lines = await ocr.perform_ocr(images[page_num])
        print(f"  {len(lines)} lines")
        repeats = sorted(
            ((k, v) for k, v in Counter(lines).items() if v > 2),
            key=lambda kv: -kv[1],
        )
        if repeats:
            print(f"  REPETITION: {repeats[:5]}")
        for i, line in enumerate(lines[:20]):
            print(f"  [{i}] {line!r}")
        if len(lines) > 20:
            print(f"  ... [{len(lines) - 20} more]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pdf = sub.add_parser("pdf", help="Inspect PDF metadata and dimensions")
    p_pdf.add_argument(
        "filenames",
        nargs="*",
        help="PDF filenames in examples/ to inspect (default: hybrid, digital, handwritten).",
    )
    p_pdf.set_defaults(func=cmd_pdf)

    p_lines = sub.add_parser("lines", help="Dump words + bboxes from an output PDF")
    p_lines.add_argument("pdf_path", help="Path to the output PDF to inspect.")
    p_lines.set_defaults(func=cmd_lines)

    p_verify = sub.add_parser(
        "verify", help="Verify an OCR output PDF has searchable text"
    )
    p_verify.add_argument(
        "pdf_path",
        nargs="?",
        default="output_ocr.pdf",
        help="Path to the OCR-output PDF to verify (default: output_ocr.pdf).",
    )
    p_verify.add_argument(
        "--keywords",
        nargs="*",
        default=None,
        help="Content keywords to look for (default: a dense.pdf-specific set).",
    )
    p_verify.set_defaults(func=cmd_verify)

    p_raw = sub.add_parser("raw", help="Dump raw LLM lines per page (no DP, no embed)")
    p_raw.add_argument("input_path", help="Path to the input PDF or image.")
    p_raw.set_defaults(func=lambda a: asyncio.run(cmd_raw(a)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
