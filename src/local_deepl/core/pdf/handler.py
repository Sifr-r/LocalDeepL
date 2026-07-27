"""
PDFHandler module.

High-level PDF processing handler facade for OCR workflows, providing
conversion to images and searchable sandwich PDF embedding.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from local_deepl.core.pdf.embedder import (
    _draw_invisible_text,
    _draw_single_line_text,
    _embed_from_image_input,
    _handle_fullpage_fallback,
    _split_and_draw_lines,
    embed_structured_text,
)
from local_deepl.core.pdf.rasterizer import (
    MAX_SAFE_PIXELS,
    _calculate_safe_dpi,
    _images_from_image_file,
    convert_pdf_to_images,
)

if TYPE_CHECKING:
    from local_deepl.core.document import DocumentResult


class PDFHandler:
    """
    PDF processing handler for OCR workflows.

    Handles:
    - Converting PDF pages to base64 PNG/JPEG images
    - Embedding an invisible text layer to produce a "sandwich" PDF
      (image background + selectable/searchable text overlay)
    """

    MAX_SAFE_PIXELS = MAX_SAFE_PIXELS

    _calculate_safe_dpi = staticmethod(_calculate_safe_dpi)
    _images_from_image_file = staticmethod(_images_from_image_file)
    _embed_from_image_input = staticmethod(_embed_from_image_input)
    _draw_invisible_text = staticmethod(_draw_invisible_text)
    _handle_fullpage_fallback = staticmethod(_handle_fullpage_fallback)
    _split_and_draw_lines = staticmethod(_split_and_draw_lines)
    _draw_single_line_text = staticmethod(_draw_single_line_text)

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

        Returns a dict of {page_num: base64_str}.
        """
        return convert_pdf_to_images(pdf_path, dpi=dpi, max_image_dim=max_image_dim)

    def write_document_result(
        self,
        input_pdf_path: str,
        output_pdf_path: str,
        document_result: DocumentResult,
        dpi: int = 200,
    ) -> None:
        """Rich-writer interface: embed text from a full DocumentResult.

        Implements :class:`~local_deepl.core.workflows.base.DocumentResultWriter`
        so the engine can pass the lossless IR directly.
        """
        self.embed_structured_text(
            input_pdf_path, output_pdf_path, document_result.to_pages_data(), dpi
        )

    def embed_structured_text(
        self,
        input_pdf_path: str | Path | Any,
        output_pdf_path: str | Path | Any,
        pages_data: dict[int, list[tuple[list[float], str]]],
        dpi: int = 200,
    ) -> None:
        """
        Build a searchable "sandwich" PDF: rasterize each page as a background
        image and overlay invisible text positioned to match the source layout.

        Accepts either a PDF or a raw image (JPEG/PNG/TIFF/BMP/WebP/AVIF)
        as input. Image inputs are converted to a 1-page-per-frame PDF —
        no rasterization-to-PDF-to-rasterization round trip required.
        """
        embed_structured_text(
            input_pdf_path, output_pdf_path, pages_data, dpi=dpi
        )
