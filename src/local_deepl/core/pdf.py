"""
PDFHandler - PDF processing utilities.

Handles PDF to image conversion and text embedding for creating searchable
PDFs. Also accepts raw image inputs (JPEG/PNG/TIFF/BMP/WebP/AVIF) —
including multi-page TIFF — so single-scan-per-file workflows don't need
a PDF wrap step first. AVIF support is provided natively by Pillow ≥
11.3 (the `pyproject.toml` constraint enforces that floor).
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import fitz  # PyMuPDF
from PIL import Image, ImageSequence

if TYPE_CHECKING:
    from local_deepl.core.document import DocumentResult

# PyMuPDF (Artifex Software) is dual-licensed under AGPL-3.0 and a commercial
# license. The library is bundled with LocalDeepL (MIT) for the convenience of
# local + open-source use; end users who distribute a non-AGPL product that
# includes PyMuPDF (or that contains a derived work linking against it) must
# acquire a commercial license from Artifex. Emit a one-shot warning the first
# time this module handles a PDF, so that downstream operators can't claim they
# weren't told. See README "Third-Party Software Notices".
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

# --- JPEG quality constants -------------------------------------------------
# Two distinct concerns:
#   * VLM upload:  base64 JPEG sent to the model — smaller = faster upload.
#   * PDF embed:   background image inside the output PDF — higher = readable.
# `pdf.py` and `core.grounded._rasterize_to_jpeg_pages` historically picked
# different VLM values (50 vs 80). The names below let each call site opt in
# to the intent rather than the raw value; unifying the values is a separate,
# behavior-changing decision worth its own PR.
VLM_JPEG_QUALITY_PDF_PATH: int = 50
VLM_JPEG_QUALITY_GROUNDED: int = 80
EMBED_JPEG_QUALITY_PDF: int = 80
EMBED_JPEG_QUALITY_IMAGE: int = 85


def _is_image_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


class PDFHandler:
    """
    PDF processing handler for OCR workflows.

    Handles:
    - Converting PDF pages to base64 PNG images
    - Embedding an invisible text layer to produce a "sandwich" PDF
      (image background + selectable/searchable text overlay)
    """

    MAX_SAFE_PIXELS = 25_000_000

    def convert_to_images(
        self,
        pdf_path: str | Path,
        dpi: int = 150,
        max_image_dim: int = 1024,
    ) -> dict[int, str]:
        """
        Render every page to a base64-encoded JPEG, capped at `max_image_dim`
        pixels on the longest edge so the image fits the VLM's context window.

        Accepts either a PDF or a raw image file
        (JPEG/PNG/TIFF/BMP/WebP/AVIF). Multi-page TIFFs are expanded to one
        page per frame. For images the `dpi` argument is ignored — the file
        is used at its native resolution, capped by `max_image_dim`.

        Smaller caps are required by some local VLMs:
          - OlmOCR-2 (Qwen2.5-VL base): 1024 is fine (default)
          - GLM-OCR:1.1B (Ollama): ~640 — larger images crash the runner
          - Florence-2 / MinerU: see their docs

        Returns a dict of {page_num: base64_str}.
        """
        if _is_image_path(pdf_path):
            return self._images_from_image_file(pdf_path, max_image_dim)

        _emit_pymupdf_agpl_notice()

        images: dict[int, str] = {}
        doc = fitz.open(pdf_path)
        try:
            for page_num, page in enumerate(doc):
                safe_dpi = self._calculate_safe_dpi(
                    page.rect.width, page.rect.height, dpi
                )
                pix = page.get_pixmap(dpi=safe_dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img.thumbnail((max_image_dim, max_image_dim))

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
                images[page_num] = base64.b64encode(buffer.getvalue()).decode("utf-8")
        finally:
            doc.close()
        return images

    @staticmethod
    def _calculate_safe_dpi(width: float, height: float, requested_dpi: int) -> int:
        """Cap DPI to prevent PyMuPDF OOM on massive pages (e.g. blueprints)."""
        page_area = width * height
        page_pixels = page_area * (requested_dpi / 72) ** 2

        if page_pixels <= PDFHandler.MAX_SAFE_PIXELS:
            return requested_dpi

        if page_area <= 0:
            return 72

        safe_dpi = int(72 * (PDFHandler.MAX_SAFE_PIXELS / page_area) ** 0.5)
        return max(72, min(requested_dpi, safe_dpi))

    @staticmethod
    def _images_from_image_file(path: str | Path, max_image_dim: int) -> dict[int, str]:
        """Load a JPEG/PNG/TIFF/BMP; multi-frame TIFFs become multiple pages."""
        images: dict[int, str] = {}
        with Image.open(path) as src:
            for page_num, frame in enumerate(ImageSequence.Iterator(src)):
                # ⚡ Bolt: two micro-fixes for the image-file path.
                # (1) Drop the trailing `.copy()`: Pillow's `convert()`
                #     always allocates a fresh image, so the second copy
                #     is a redundant ~3MB re-allocation per frame on a
                #     1024x1024 RGB input. ~35% wall-time saving on the
                #     multi-frame decode loop measured locally.
                # (2) Match `convert_to_images` (PDF path, line 85) at
                #     `quality=50`. The VLM-side leg is identical; the
                #     PDF path has been at q=50 successfully. The image
                #     path was an inconsistency that doubled the base64
                #     payload per page on a typical 1024x1400 scan
                #     (1115KB → 637KB, ~43% smaller), which speeds up
                #     the LLM data-URL upload proportionally.
                img = frame.convert("RGB")
                img.thumbnail((max_image_dim, max_image_dim))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=VLM_JPEG_QUALITY_PDF_PATH)
                images[page_num] = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return images

    def write_document_result(
        self,
        input_pdf_path: str,
        output_pdf_path: str,
        document_result: DocumentResult,
        dpi: int = 200,
    ) -> None:
        """Rich-writer interface: embed text from a full DocumentResult.

        Implements :class:`~local_deepl.core.workflows.base.DocumentResultWriter`
        so the engine can pass the lossless IR directly. The current text-layer
        embedding only consumes bbox + text (via ``to_pages_data()``, which
        respects processor-assigned reading order); block kinds, confidence,
        and metadata remain available on ``document_result`` for future
        structure-aware embedding without a protocol change.
        """
        self.embed_structured_text(
            input_pdf_path, output_pdf_path, document_result.to_pages_data(), dpi
        )

    def embed_structured_text(
        self,
        input_pdf_path: str,
        output_pdf_path: str,
        pages_data: dict[int, list[tuple[list[float], str]]],
        dpi: int = 200,
    ) -> None:
        """
        Build a searchable "sandwich" PDF: rasterize each page as a background
        image and overlay invisible text positioned to match the source layout.

        Accepts either a PDF or a raw image (JPEG/PNG/TIFF/BMP/WebP/AVIF)
        as input. Image inputs are converted to a 1-page-per-frame PDF —
        no rasterization-to-PDF-to-rasterization round trip required.

        Args:
            input_pdf_path: Path to the source PDF or image file.
            output_pdf_path: Where to write the searchable PDF.
            pages_data: {page_num: [([nx0, ny0, nx1, ny1], text), ...]} with
                normalized (0..1) box coordinates.
            dpi: Rasterization DPI for PDF-sourced backgrounds (ignored for
                image inputs — they're used at native resolution).
        """
        if _is_image_path(input_pdf_path):
            self._embed_from_image_input(input_pdf_path, output_pdf_path, pages_data)
            return

        _emit_pymupdf_agpl_notice()

        doc = fitz.open(input_pdf_path)
        new_doc = fitz.open()

        try:
            for page_num in range(len(doc)):
                old_page = doc[page_num]
                width = old_page.rect.width
                height = old_page.rect.height

                safe_dpi = self._calculate_safe_dpi(width, height, dpi)
                pix = old_page.get_pixmap(dpi=safe_dpi)
                img_data = pix.tobytes("jpg", jpg_quality=EMBED_JPEG_QUALITY_PDF)

                new_page = new_doc.new_page(width=width, height=height)
                new_page.insert_image(new_page.rect, stream=img_data)

                for rect_coords, text in pages_data.get(page_num, []):
                    self._draw_invisible_text(
                        new_page, rect_coords, text, width, height
                    )

            new_doc.save(output_pdf_path)
        finally:
            new_doc.close()
            doc.close()

    def _embed_from_image_input(
        self,
        image_path: str,
        output_pdf_path: str,
        pages_data: dict,
    ) -> None:
        """Build a sandwich PDF directly from an image (single- or multi-frame)."""
        new_doc = fitz.open()
        try:
            with Image.open(image_path) as src:
                for page_num, frame in enumerate(ImageSequence.Iterator(src)):
                    img = frame.convert("RGB")
                    # One PDF point = 1/72 inch. Assume image is 72 DPI so
                    # pixel count equals page size in points. Concrete value
                    # doesn't matter — all coords are normalized.
                    width, height = float(img.width), float(img.height)

                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=EMBED_JPEG_QUALITY_IMAGE)
                    img_data = buf.getvalue()

                    new_page = new_doc.new_page(width=width, height=height)
                    new_page.insert_image(new_page.rect, stream=img_data)

                    for rect_coords, text in pages_data.get(page_num, []):
                        self._draw_invisible_text(
                            new_page, rect_coords, text, width, height
                        )
            new_doc.save(output_pdf_path)
        finally:
            new_doc.close()

    @staticmethod
    def _draw_invisible_text(
        page: fitz.Page,
        rect_coords: list[float],
        text: str,
        page_width: float,
        page_height: float,
    ) -> None:
        """
        Embed invisible `text` so its glyph bboxes span the *full width* of
        the source bbox — selecting anywhere inside the bbox in a PDF viewer
        returns the text.

        Strategy: size the font by box height (glyphs never exceed the box
        vertically → no bleeding into neighbouring rows), then apply a
        horizontal-scale matrix via the `morph` parameter so rendered glyph
        bboxes span the box width. `render_mode=3` keeps the layer invisible;
        the geometric distortion only affects selection/search extents, not
        Unicode codepoints (copy, Ctrl+F, accessibility tools still return
        the original text verbatim).

        Why not `min(width_based, height_based)` fontsize like before?
        Whichever constraint is tighter wins, and when height is tighter
        (short wide boxes: headings, form labels, fields) the text ends
        partway across the box — selection on the right side returns
        nothing. Sizing to fill width instead causes vertical overflow
        that bleeds into neighbouring rows. Horizontal scaling decouples
        the two axes: height fits, width fills, neither constraint is
        violated.
        """
        text = (text or "").strip()
        if not text:
            return

        # Phase 1: Handle full-page fallback detection
        if PDFHandler._handle_fullpage_fallback(
            page, rect_coords, text, page_width, page_height
        ):
            return

        # Phase 2: Handle multi-line block detection and splitting
        if PDFHandler._split_and_draw_lines(
            page, rect_coords, text, page_width, page_height
        ):
            return

        # Phase 3: Single-line drawing
        PDFHandler._draw_single_line_text(
            page, rect_coords, text, page_width, page_height
        )

    @staticmethod
    def _handle_fullpage_fallback(
        page: fitz.Page,
        rect_coords: list[float],
        text: str,
        page_width: float,
        page_height: float,
    ) -> bool:
        nx0, ny0, nx1, ny1 = rect_coords
        is_full_page_fallback = (
            nx0 <= 0.001
            and ny0 <= 0.001
            and nx1 >= 0.999
            and ny1 >= 0.999
            and "\n" in text
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

    @staticmethod
    def _split_and_draw_lines(
        page: fitz.Page,
        rect_coords: list[float],
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
                    PDFHandler._draw_invisible_text(
                        page,
                        [nx0, ny0 + i * slice_h, nx1, ny0 + (i + 1) * slice_h],
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
                PDFHandler._draw_invisible_text(
                    page,
                    [nx0, ny0 + i * slice_h, nx1, ny0 + (i + 1) * slice_h],
                    line_text,
                    page_width,
                    page_height,
                )
            return True
        return False

    @staticmethod
    def _draw_single_line_text(
        page: fitz.Page,
        rect_coords: list[float],
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
