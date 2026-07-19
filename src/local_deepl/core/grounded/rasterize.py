"""Synchronous PDF/image → JPEG page rasterization for grounded backends.

The :func:`_rasterize_to_jpeg_pages` helper is shared by every grounded
backend that wants to call the VLM on JPEG bytes (rather than the raw PDF).
It is intentionally *blocking* — callers MUST run it via
``asyncio.to_thread`` so the event loop doesn't stall on
``fitz.open`` / ``get_pixmap`` / ``PIL.thumbnail``.
"""

from __future__ import annotations

import base64
import io


def _rasterize_to_jpeg_pages(
    path: str,
    max_image_dim: int,
    dpi: int,
) -> list[tuple[str, int, int]]:
    """Return JPEG-encoded pages as ``(base64_str, width, height)``.

    PDF pages are rendered at the requested ``dpi``; image inputs are
    decoded and walked frame-by-frame. The result is shrunk to fit
    inside ``max_image_dim`` (uniform thumbnail) before being encoded
    as JPEG at the project's VLM-grounded quality setting.

    Callers MUST run this on a worker thread:
        ``page_imgs = await asyncio.to_thread(
            _rasterize_to_jpeg_pages, path, max_dim, dpi,
        )``
    """
    import fitz
    from PIL import Image, ImageSequence

    from local_deepl.core.pdf import (
        VLM_JPEG_QUALITY_GROUNDED,
        _is_image_path,
    )

    page_imgs: list[tuple[str, int, int]] = []

    def _emit(img: Image.Image) -> None:
        img = img.convert("RGB")
        img.thumbnail((max_image_dim, max_image_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=VLM_JPEG_QUALITY_GROUNDED)
        page_imgs.append(
            (base64.b64encode(buf.getvalue()).decode(), img.width, img.height)
        )

    if _is_image_path(path):
        with Image.open(path) as src:
            for frame in ImageSequence.Iterator(src):
                _emit(frame.copy())
    else:
        doc = fitz.open(path)
        try:
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                # Performance: avoid JPEG encode/decode before _emit writes the
                # final thumbnail JPEG. Direct pixmap conversion saves ~63-75ms/page.
                _emit(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        finally:
            doc.close()

    return page_imgs


__all__ = ["_rasterize_to_jpeg_pages"]
