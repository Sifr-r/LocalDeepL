#!/usr/bin/env python3
"""Build a ground-truth JSON fixture for the confidence-eval scripts.

Two sources are supported, selected with ``--from-vlm`` (default) or
``--from-pdf``:

``--from-vlm``
    Bootstrap a fixture from a grounded VLM run. Used for examples that
    are too dense to hand-build (dense.pdf, notes.pdf, ...): the
    grounded path produces accurate (bbox, text) pairs in one shot which
    we serialize into the fixture format that ``scripts/confidence_eval.py``
    understands. The fixture is then useful for *regression* testing —
    confidence drops on future runs flag that something got worse, even
    if the absolute baseline is biased toward whichever model produced
    the fixture.

``--from-pdf``
    Extract text + bboxes from an already-produced sandwich PDF (formerly
    ``fixture_from_output.py``). Useful when the hybrid pipeline already
    produced per-box (bbox, text) pairs and we can read them straight
    back out of the embedded text layer.

Usage:
    uv run scripts/build_fixture.py examples/dense.pdf tests/fixtures/ground_truth_dense.json
    uv run scripts/build_fixture.py examples/notes.pdf tests/fixtures/ground_truth_notes.json \\
        --model qwen/qwen3-vl-4b
    uv run scripts/build_fixture.py scratch/output_notes.pdf \\
        tests/fixtures/ground_truth_notes.json --from-pdf
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
from _common import setup_sys_path

setup_sys_path()


def _write_fixture(fixture: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    print(f"  -> {out_path}")


async def _build_from_vlm(args: argparse.Namespace) -> None:
    from omniscribe import PromptedGroundedOCR

    api_base = args.api_base or os.getenv("LLM_API_BASE", "http://localhost:1234/v1")
    in_path = Path(args.input)
    out_path = Path(args.output)

    print(f"Building fixture from {in_path.name} via grounded ({args.model})")
    print(f"  api_base={api_base}")

    backend = PromptedGroundedOCR(
        api_base=api_base,
        model=args.model,
        max_image_dim=args.max_image_dim,
        max_tokens=8192,
        concurrency=3,
    )
    response = await backend.ocr_document(str(in_path))

    if not response.blocks:
        print("  ERROR: grounded returned 0 blocks; refusing to write empty fixture")
        sys.exit(1)

    layout = []
    for block_id, b in enumerate(response.blocks):
        # GroundedBlock.bbox is normalized [nx0, ny0, nx1, ny1].
        nx0, ny0, nx1, ny1 = b.bbox
        pw, ph = response.page_sizes[b.page_index]
        # Fixture format used by digital/hybrid: [y0, x0, y1, x1] in pixels.
        layout.append(
            {
                "block_content": b.text,
                "bbox": [
                    round(ny0 * ph),
                    round(nx0 * pw),
                    round(ny1 * ph),
                    round(nx1 * pw),
                ],
                "block_id": block_id,
                "page_index": b.page_index,
                "block_label": b.label or "text",
                "score": 1.0,
            }
        )

    fixture = {
        "data": {
            "file_name": in_path.name,
            "file_type": "pdf" if in_path.suffix.lower() == ".pdf" else "image",
            "layout": layout,
            "data_info": {
                "pages": [
                    {"width": int(w), "height": int(h)}
                    for (w, h) in response.page_sizes
                ],
                "num_pages": len(response.page_sizes),
            },
        }
    }

    print(f"  wrote {len(layout)} blocks across {len(response.page_sizes)} pages")
    _write_fixture(fixture, out_path)


def _build_from_pdf(args: argparse.Namespace) -> None:
    import pymupdf as fitz

    out_pdf = Path(args.input)
    fixture_path = Path(args.output)
    source_name = args.source_name or out_pdf.name.replace("output_", "")

    doc = fitz.open(str(out_pdf))
    page_sizes: list[tuple[int, int]] = []
    layout: list[dict] = []
    block_id = 0

    for page_idx, page in enumerate(doc):
        pw, ph = round(page.rect.width), round(page.rect.height)
        page_sizes.append((pw, ph))
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    layout.append(
                        {
                            "block_content": text,
                            "bbox": [round(y0), round(x0), round(y1), round(x1)],
                            "block_id": block_id,
                            "page_index": page_idx,
                            "block_label": "text",
                            "score": 1.0,
                        }
                    )
                    block_id += 1
    doc.close()

    if not layout:
        print(
            f"ERROR: extracted 0 blocks from {out_pdf}; refusing to write empty fixture"
        )
        sys.exit(1)

    fixture = {
        "data": {
            "file_name": source_name,
            "file_type": "pdf" if source_name.lower().endswith(".pdf") else "image",
            "layout": layout,
            "data_info": {
                "pages": [{"width": w, "height": h} for (w, h) in page_sizes],
                "num_pages": len(page_sizes),
            },
        }
    }

    dims = "x".join(f"{w}x{h}" for w, h in page_sizes[:3])
    suffix = "..." if len(page_sizes) > 3 else ""
    print(
        f"wrote {len(layout)} blocks across {len(page_sizes)} pages (dims={dims}{suffix})"
    )
    _write_fixture(fixture, fixture_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "input", help="Input PDF/image (--from-vlm) or sandwich PDF (--from-pdf)"
    )
    parser.add_argument("output", help="Output fixture JSON path")

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--from-vlm",
        dest="from_pdf",
        action="store_false",
        help="Build the fixture from a grounded VLM run (default).",
    )
    source.add_argument(
        "--from-pdf",
        dest="from_pdf",
        action="store_true",
        help="Build the fixture from an already-produced sandwich PDF output.",
    )

    # --from-vlm options.
    parser.add_argument(
        "--api-base",
        default=None,
        help="Defaults to LLM_API_BASE env var, then localhost:1234",
    )
    parser.add_argument("--model", default="qwen/qwen3-vl-4b")
    parser.add_argument("--max-image-dim", type=int, default=1024)
    # --from-pdf options.
    parser.add_argument(
        "--source-name",
        default=None,
        help="file_name field for the fixture (defaults to the output PDF stem "
        "with the 'output_' prefix stripped — e.g. output_notes.pdf -> notes.pdf)",
    )
    args = parser.parse_args()

    if args.from_pdf:
        _build_from_pdf(args)
    else:
        asyncio.run(_build_from_vlm(args))


if __name__ == "__main__":
    main()
