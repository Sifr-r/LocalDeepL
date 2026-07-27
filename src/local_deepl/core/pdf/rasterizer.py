"""
Rasterizer module for PDF and image inputs.

Provides PyMuPDF AGPL licensing warning emission, safe DPI calculations,
image extension validation, and rasterization of PDF pages and images
(JPEG, PNG, BMP, WebP, TIFF, AVIF) into base64 JPEGs.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageSequence

_LOGGER = logging.getLogger(__name__)
_PYMUPDF_AGPL_NOTICE_EMITTED = False


def _emit_pymupdf_agpl_notice() -> None:
    global _PYMUPDF_AGPL_NOTICE_EMITTED
    if _PYMUPDF_AGPL_NOTICE_EMITTED:
        return
    _PYMUPDF_AGPL_NOTICE_EMITTED = True
    _LOGGER.warning(
        "LocalDeepL is built on PyMuPDF (Artifex Software). PyMuPDF is "
        "AGPL-3.0; if you distribute this binary or a non-AGPL derivative "
        "to anyone outside your organization you may owe Artifex a "
        "commercial license. See README > Third-Party Software Notices."
    )


IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
        ".avif",
    }
)

VLM_JPEG_QUALITY_PDF_PATH: int = 50
VLM_JPEG_QUALITY_GROUNDED: int = 80
EMBED_JPEG_QUALITY_PDF: int = 80
EMBED_JPEG_QUALITY_IMAGE: int = 85

MAX_SAFE_PIXELS: int = 25_000_000


def _is_image_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def _calculate_safe_dpi(width: float, height: float, requested_dpi: int) -> int:
    """Cap DPI to prevent PyMuPDF OOM on massive pages (e.g. blueprints)."""
    page_area = width * height
    page_pixels = page_area * (requested_dpi / 72) ** 2

    if page_pixels <= MAX_SAFE_PIXELS:
        return requested_dpi

    if page_area <= 0:
        return 72

    safe_dpi = int(72 * (MAX_SAFE_PIXELS / page_area) ** 0.5)
    return max(72, min(requested_dpi, safe_dpi))


def _images_from_image_file(path: str | Path, max_image_dim: int) -> dict[int, str]:
    """Load a JPEG/PNG/TIFF/BMP; multi-frame TIFFs become multiple pages."""
    images: dict[int, str] = {}
    with Image.open(path) as src:
        for page_num, frame in enumerate(ImageSequence.Iterator(src)):
            img = frame.convert("RGB")
            img.thumbnail((max_image_dim, max_image_dim))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
            images[page_num] = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return images


def convert_pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 150,
    max_image_dim: int = 1024,
) -> dict[int, str]:
    """
    Render every page to a base64-encoded JPEG, capped at `max_image_dim`
    pixels on the longest edge so the image fits the VLM's context window.

    Accepts either a PDF or a raw image file (JPEG/PNG/TIFF/BMP/WebP/AVIF).
    """
    if _is_image_path(pdf_path):
        return _images_from_image_file(pdf_path, max_image_dim)

    _emit_pymupdf_agpl_notice()

    images: dict[int, str] = {}
    doc = fitz.open(pdf_path)
    try:
        for page_num, page in enumerate(doc):
            safe_dpi = _calculate_safe_dpi(page.rect.width, page.rect.height, dpi)
            pix = page.get_pixmap(dpi=safe_dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.thumbnail((max_image_dim, max_image_dim))

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
            images[page_num] = base64.b64encode(buffer.getvalue()).decode("utf-8")
    finally:
        doc.close()
    return images
