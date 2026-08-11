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
from collections.abc import Iterator
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageSequence

_LOGGER = logging.getLogger(__name__)

# E5: this flag guards the one-shot PyMuPDF AGPL notice. The read-modify-
# write sequence in ``_emit_pymupdf_agpl_notice`` is intentionally NOT
# protected by a lock — two concurrent workers could each see ``False``,
# each emit the notice, and each flip the flag. The duplicate log line is
# purely cosmetic (the notice is informational; nothing depends on its
# being emitted exactly once), so the race is documented rather than
# synchronised. If we ever need strict single-emission semantics, wrap
# the body in a module-level ``threading.Lock`` — the cost is negligible.
_PYMUPDF_AGPL_NOTICE_EMITTED = False


def _emit_pymupdf_agpl_notice() -> None:
    global _PYMUPDF_AGPL_NOTICE_EMITTED
    if _PYMUPDF_AGPL_NOTICE_EMITTED:
        return
    _PYMUPDF_AGPL_NOTICE_EMITTED = True
    _LOGGER.warning(
        "OmniScribe is built on PyMuPDF (Artifex Software). PyMuPDF is "
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

VLM_JPEG_QUALITY_PDF_PATH: int
VLM_JPEG_QUALITY_GROUNDED: int
EMBED_JPEG_QUALITY_PDF: int
EMBED_JPEG_QUALITY_IMAGE: int

MAX_SAFE_PIXELS: int

# Resolve the tunables from env once at import time. The previous
# hardcoded values are kept as the defaults in
# ``RasterizationSettings`` so behaviour is unchanged when no env vars
# are set; operators can override via ``OMNISCRIBE_RASTERIZER_*``.
# See deep_refactor_report.md §4.7.
from omniscribe.core.pdf.rasterization_settings import (  # noqa: E402
    RasterizationSettings as _RasterizationSettings,
)

_rasterization_settings = _RasterizationSettings.from_env()
VLM_JPEG_QUALITY_PDF_PATH = _rasterization_settings.vlm_jpeg_quality_pdf_path
VLM_JPEG_QUALITY_GROUNDED = _rasterization_settings.vlm_jpeg_quality_grounded
EMBED_JPEG_QUALITY_PDF = _rasterization_settings.embed_jpeg_quality_pdf
EMBED_JPEG_QUALITY_IMAGE = _rasterization_settings.embed_jpeg_quality_image

MAX_SAFE_PIXELS = _rasterization_settings.max_safe_pixels


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


def _parse_page_range_local(page_str: str, total_pages: int) -> list[int]:
    """Parse a 1-indexed range like '1-3,5,7-9' into sorted 0-indexed pages.

    Locally scoped (not imported from ``workflows.utils``) to break a
    circular-import chain: rasterizer -> workflows.utils -> workflows
    package init -> hybrid -> pdf, which deadlocked the ``import omniscribe
    .core.pdf`` entry point. Mirrors the canonical implementation in
    :func:`omniscribe.core.workflows.utils.parse_page_range`.
    """
    pages: set[int] = set()
    try:
        for part in page_str.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s), int(end_s)
                for p in range(start, end + 1):
                    if 1 <= p <= total_pages:
                        pages.add(p - 1)
            else:
                p = int(part)
                if 1 <= p <= total_pages:
                    pages.add(p - 1)
    except ValueError as e:
        raise ValueError(f"Invalid page range syntax: '{page_str}'") from e
    return sorted(pages)


def _generator_from_image_source(
    source: str | bytes | Path,
    pages: str | None,
    max_image_dim: int,
) -> Iterator[tuple[int, Image.Image, str]]:
    if isinstance(source, (str, Path)):
        src_context = Image.open(source)
    else:
        src_context = Image.open(io.BytesIO(source))

    with src_context as src:
        frames = list(ImageSequence.Iterator(src))
        total_pages = len(frames)
        selected_pages: set[int] | None = None
        if pages:
            selected_pages = set(_parse_page_range_local(pages, total_pages))

        for page_num, frame in enumerate(frames):
            if selected_pages is not None and page_num not in selected_pages:
                continue
            img = frame.convert("RGB")
            img.thumbnail((max_image_dim, max_image_dim))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            yield page_num, img, b64_str


def _generator_from_pdf_source(
    source: str | bytes | Path,
    dpi: int,
    pages: str | None,
    max_image_dim: int,
) -> Iterator[tuple[int, Image.Image, str]]:
    _emit_pymupdf_agpl_notice()

    if isinstance(source, bytes):
        doc = fitz.open(stream=source, filetype="pdf")
    else:
        doc = fitz.open(source)

    try:
        total_pages = len(doc)
        selected_pages: set[int] | None = None
        if pages:
            selected_pages = set(_parse_page_range_local(pages, total_pages))

        for page_num in range(total_pages):
            if selected_pages is not None and page_num not in selected_pages:
                continue
            page = doc[page_num]
            safe_dpi = _calculate_safe_dpi(page.rect.width, page.rect.height, dpi)
            pix = page.get_pixmap(dpi=safe_dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.thumbnail((max_image_dim, max_image_dim))

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            yield page_num, img, b64_str
    finally:
        doc.close()


def convert_generator(
    source: str | bytes | Path,
    dpi: int = 200,
    pages: str | None = None,
    max_image_dim: int = 1024,
) -> Iterator[tuple[int, Image.Image, str]]:
    """Stream page images and base64-encoded JPEGs lazily one page at a time.

    Accepts either a PDF or raw image file/bytes (JPEG, PNG, TIFF, BMP,
    WebP, AVIF). Yields ``(page_num, image_pil, base64_jpeg_str)``
    tuples. The source PDF/document is kept open until the generator is
    exhausted; the caller MUST consume the iterator (or call ``.close()``
    on it) so PyMuPDF releases the file handle promptly.

    Raises ``ValueError`` for empty paths / empty bytes / non-positive DPI.
    """
    if dpi <= 0:
        raise ValueError("dpi must be greater than 0")

    if isinstance(source, (str, Path)) and not str(source).strip():
        raise ValueError("Source file path cannot be empty")
    if isinstance(source, bytes) and len(source) == 0:
        raise ValueError("Source bytes cannot be empty")

    is_image = False
    if isinstance(source, (str, Path)):
        is_image = _is_image_path(source)
    elif isinstance(source, bytes) and not source.startswith(b"%PDF"):
        try:
            with Image.open(io.BytesIO(source)) as test_img:
                test_img.verify()
            is_image = True
        except Exception:
            is_image = False

    if is_image:
        yield from _generator_from_image_source(
            source, pages=pages, max_image_dim=max_image_dim
        )
    else:
        yield from _generator_from_pdf_source(
            source, dpi=dpi, pages=pages, max_image_dim=max_image_dim
        )


def convert_batches(
    source: str | bytes | Path,
    *,
    batch_size: int = 8,
    dpi: int = 200,
    pages: str | None = None,
    max_image_dim: int = 1024,
) -> Iterator[list[tuple[int, Image.Image, str]]]:
    """Stream pages from ``source`` in bounded batches.

    Audit H1 fix: this is the bounded-memory counterpart to
    :func:`convert_pdf_to_images`. Where the eager API materializes every
    page's PIL image and base64 string into a single ``dict`` up-front
    (peak memory grows linearly with page count), ``convert_batches``
    only holds at most ``batch_size`` pages worth of decoded images and
    encoded JPEGs at any one time. Each yielded batch is an independent
    ``list`` so the caller can release the previous batch's PIL objects
    as soon as downstream processing finishes.

    The last batch may be shorter than ``batch_size`` when the source
    page count is not an exact multiple. Page selection via ``pages`` is
    delegated to :func:`convert_generator`, so the same ``"1,3-5,7"``
    syntax is supported.

    Parameters
    ----------
    source
        Path, ``bytes``, or :class:`~pathlib.Path` to a PDF, JPEG, PNG,
        TIFF, BMP, WebP, or AVIF file. Multi-frame TIFFs are expanded
        one frame per page.
    batch_size
        Maximum number of pages per yielded batch. Must be ``>= 1``.
        ``batch_size=1`` is equivalent to consuming
        :func:`convert_generator` one item at a time; ``batch_size>=2``
        amortizes per-batch overhead (generator setup, base64 encode)
        while still bounding peak memory.
    dpi
        PyMuPDF rasterization DPI. Ignored for raw image inputs.
    pages
        Optional page selector passed through to
        :func:`convert_generator`.
    max_image_dim
        Longest-edge cap applied to each rasterized page.

    Yields
    ------
    list[tuple[int, Image.Image, str]]
        A batch of at most ``batch_size`` ``(page_num, image, b64_str)``
        triples. Each batch is a fresh list; the caller may mutate or
        discard it freely.

    Raises
    ------
    ValueError
        If ``batch_size`` is not a positive integer, or if
        :func:`convert_generator` rejects the source (empty path,
        empty bytes, non-positive DPI).
    """
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    batch: list[tuple[int, Image.Image, str]] = []
    for item in convert_generator(
        source, dpi=dpi, pages=pages, max_image_dim=max_image_dim
    ):
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def convert(
    pdf_path: str | Path,
    dpi: int = 150,
    max_image_dim: int = 1024,
) -> dict[int, str]:
    """Backward-compatible alias for :func:`convert_pdf_to_images`.

    Historical name kept for callers (and pre-existing tests) that
    expect ``from omniscribe.core.pdf.rasterizer import convert``.
    For large PDFs prefer :func:`convert_batches` (bounded peak memory)
    or :func:`convert_generator` (single-page streaming).
    """
    return convert_pdf_to_images(pdf_path, dpi=dpi, max_image_dim=max_image_dim)


def convert_pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 150,
    max_image_dim: int = 1024,
) -> dict[int, str]:
    """
    Render every page to a base64-encoded JPEG, capped at `max_image_dim`
    pixels on the longest edge so the image fits the VLM's context window.

    Backward-compatible eager entry point. For large PDFs prefer
    :func:`convert_batches` (bounded peak memory) or
    :func:`convert_generator` (single-page streaming).
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
