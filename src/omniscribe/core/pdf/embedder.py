"""
Embedder module for invisible text layer PDF rendering.

Handles embedding selectable invisible text over rasterized background pages
matching normalized bbox coordinates ([x0, y0, x1, y1] in 0..1), font sizing,
and searchable PDF output generation.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from PIL import Image, ImageSequence

from omniscribe.core.document import BBox
from omniscribe.core.pdf.rasterizer import (
    EMBED_JPEG_QUALITY_IMAGE,
    EMBED_JPEG_QUALITY_PDF,
    _calculate_safe_dpi,
    _emit_pymupdf_agpl_notice,
    _is_image_path,
)


def _handle_fullpage_fallback(
    page: fitz.Page,
    rect_coords: Sequence[float],
    text: str,
    page_width: float,
    page_height: float,
) -> bool:
    nx0, ny0, nx1, ny1 = rect_coords
    is_full_page_fallback = (
        nx0 <= 0.001 and ny0 <= 0.001 and nx1 >= 0.999 and ny1 >= 0.999 and "\n" in text
    )
    if is_full_page_fallback:
        fallback_rect = fitz.Rect(10, 10, page_width - 10, page_height - 10)
        page.insert_textbox(
            fallback_rect,
            text,
            fontsize=6,
            fontname="helv",
            render_mode=3,
            color=(0, 0, 0),
            align=0,
        )
        return True
    return False


def _split_and_draw_lines(
    page: fitz.Page,
    rect_coords: Sequence[float],
    text: str,
    page_width: float,
    page_height: float,
) -> bool:
    nx0, ny0, nx1, ny1 = rect_coords
    if "\n" in text:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if len(lines) > 1:
            slice_h = (ny1 - ny0) / len(lines)
            for i, line in enumerate(lines):
                _draw_invisible_text(
                    page,
                    (nx0, ny0 + i * slice_h, nx1, ny0 + (i + 1) * slice_h),
                    line,
                    page_width,
                    page_height,
                )
            return True
        text = lines[0] if lines else text

    pdf_rect = fitz.Rect(
        nx0 * page_width,
        ny0 * page_height,
        nx1 * page_width,
        ny1 * page_height,
    )
    box_width = pdf_rect.width
    box_height = pdf_rect.height
    if box_width <= 0 or box_height <= 0:
        return True

    words = text.split()
    norm_height = ny1 - ny0
    aspect = box_height / max(0.01, box_width)
    if norm_height > 0.07 and aspect > 0.20 and len(words) >= 2:
        n_lines = 3 if norm_height > 0.13 else 2
        n_lines = min(n_lines, len(words))
        slice_h = (ny1 - ny0) / n_lines
        for i in range(n_lines):
            start = round(i * len(words) / n_lines)
            end = round((i + 1) * len(words) / n_lines)
            line_text = " ".join(words[start:end])
            if not line_text:
                continue
            _draw_invisible_text(
                page,
                (nx0, ny0 + i * slice_h, nx1, ny0 + (i + 1) * slice_h),
                line_text,
                page_width,
                page_height,
            )
        return True
    return False


def _draw_single_line_text(
    page: fitz.Page,
    rect_coords: Sequence[float],
    text: str,
    page_width: float,
    page_height: float,
) -> None:
    nx0, ny0, nx1, ny1 = rect_coords
    pdf_rect = fitz.Rect(
        nx0 * page_width,
        ny0 * page_height,
        nx1 * page_width,
        ny1 * page_height,
    )
    box_width = pdf_rect.width
    box_height = pdf_rect.height

    font = fitz.Font("helv")
    ascender = getattr(font, "ascender", 1.075)
    descender = getattr(font, "descender", -0.299)
    extent_em = max(0.01, ascender - descender)
    fontsize = max(3.0, min(72.0, box_height / extent_em))

    natural_width = font.text_length(text, fontsize=fontsize)
    if natural_width <= 0:
        return

    target_width = max(1.0, box_width * 0.98)
    scale_x = min(50.0, target_width / natural_width)
    baseline = fitz.Point(pdf_rect.x0, pdf_rect.y1 + descender * fontsize)
    morph = (baseline, fitz.Matrix(scale_x, 1.0))
    page.insert_text(
        baseline,
        text,
        fontsize=fontsize,
        fontname="helv",
        render_mode=3,
        color=(0, 0, 0),
        morph=morph,
    )


def _draw_invisible_text(
    page: fitz.Page,
    rect_coords: Sequence[float],
    text: str,
    page_width: float,
    page_height: float,
) -> None:
    """
    Embed invisible `text` so its glyph bboxes span the *full width* of
    the source bbox — selecting anywhere inside the bbox in a PDF viewer
    returns the text.
    """
    text = (text or "").strip()
    if not text:
        return

    # Phase 1: Handle full-page fallback detection
    if _handle_fullpage_fallback(page, rect_coords, text, page_width, page_height):
        return

    # Phase 2: Handle multi-line block detection and splitting
    if _split_and_draw_lines(page, rect_coords, text, page_width, page_height):
        return

    # Phase 3: Single-line drawing
    _draw_single_line_text(page, rect_coords, text, page_width, page_height)


def _embed_from_image_input(
    image_path: str | Path,
    output_pdf_path: str | Path,
    pages_data: dict[int, list[tuple[BBox, str]]] | dict[Any, Any],
) -> None:
    """Build a sandwich PDF directly from an image (single- or multi-frame)."""
    new_doc = fitz.open()
    try:
        with Image.open(image_path) as src:
            for page_num, frame in enumerate(ImageSequence.Iterator(src)):
                img = frame.convert("RGB")
                width, height = float(img.width), float(img.height)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=EMBED_JPEG_QUALITY_IMAGE)
                img_data = buf.getvalue()

                new_page = new_doc.new_page(width=width, height=height)
                new_page.insert_image(new_page.rect, stream=img_data)

                for rect_coords, text in pages_data.get(page_num, []):
                    _draw_invisible_text(new_page, rect_coords, text, width, height)
        new_doc.save(output_pdf_path)
    finally:
        new_doc.close()


def embed_structured_text(
    input_pdf_path: str | Path,
    output_pdf_path: str | Path,
    pages_data: dict[int, list[tuple[BBox, str]]],
    dpi: int = 200,
) -> None:
    """
    Build a searchable "sandwich" PDF: rasterize each page as a background
    image and overlay invisible text positioned to match the source layout.

    Accepts either a PDF or a raw image (JPEG/PNG/TIFF/BMP/WebP/AVIF)
    as input.
    """
    if _is_image_path(input_pdf_path):
        _embed_from_image_input(input_pdf_path, output_pdf_path, pages_data)
        return

    _emit_pymupdf_agpl_notice()

    doc = fitz.open(input_pdf_path)
    new_doc = fitz.open()

    try:
        for page_num in range(len(doc)):
            old_page = doc[page_num]
            width = old_page.rect.width
            height = old_page.rect.height

            safe_dpi = _calculate_safe_dpi(width, height, dpi)
            pix = old_page.get_pixmap(dpi=safe_dpi)
            img_data = pix.tobytes("jpg", jpg_quality=EMBED_JPEG_QUALITY_PDF)

            new_page = new_doc.new_page(width=width, height=height)
            new_page.insert_image(new_page.rect, stream=img_data)

            for rect_coords, text in pages_data.get(page_num, []):
                _draw_invisible_text(new_page, rect_coords, text, width, height)

        new_doc.save(output_pdf_path)
    finally:
        new_doc.close()
        doc.close()
