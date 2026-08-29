"""
PDF subpackage re-exporting PDFHandler and PDF processing utilities.
"""

from omniscribe.core.pdf.embedder import (
    embed_structured_text,
)
from omniscribe.core.pdf.embedder_helpers import (
    _draw_invisible_text,
    _draw_single_line_text,
    _embed_from_image_input,
    _handle_fullpage_fallback,
    _split_and_draw_lines,
)
from omniscribe.core.pdf.handler import PDFHandler
from omniscribe.core.pdf.rasterizer import (
    EMBED_JPEG_QUALITY_IMAGE,
    EMBED_JPEG_QUALITY_PDF,
    IMAGE_EXTENSIONS,
    MAX_SAFE_PIXELS,
    VLM_JPEG_QUALITY_GROUNDED,
    VLM_JPEG_QUALITY_PDF_PATH,
    _calculate_safe_dpi,
    _emit_pymupdf_agpl_notice,
    _images_from_image_file,
    _is_image_path,
    convert_batches,
    convert_generator,
    convert_pdf_to_images,
)
from omniscribe.core.workflows.base import DocumentResultWriter

__all__ = [
    "EMBED_JPEG_QUALITY_IMAGE",
    "EMBED_JPEG_QUALITY_PDF",
    "IMAGE_EXTENSIONS",
    "MAX_SAFE_PIXELS",
    "VLM_JPEG_QUALITY_GROUNDED",
    "VLM_JPEG_QUALITY_PDF_PATH",
    "DocumentResultWriter",
    "PDFHandler",
    "_calculate_safe_dpi",
    "_draw_invisible_text",
    "_draw_single_line_text",
    "_embed_from_image_input",
    "_emit_pymupdf_agpl_notice",
    "_handle_fullpage_fallback",
    "_images_from_image_file",
    "_is_image_path",
    "_split_and_draw_lines",
    "convert_batches",
    "convert_generator",
    "convert_pdf_to_images",
    "embed_structured_text",
]
