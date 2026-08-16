"""Tests for the OCR processor fallback paths (P1 #3).

The three ``except Exception`` swallowing sites in
``core/ocr/processor.py`` (pytesseract fallback, adaptive-threshold
fallback) and ``core/pdf/embedder.py`` (font probe) used to return
safe defaults without logging. Operators had no visibility into
OCR quality degradation. This test asserts each site now logs a
warning before returning the safe default.
"""

from __future__ import annotations

import base64
import io
import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _png_1x1_base64() -> str:
    """Build a small but valid 32x32 PNG in-memory and return its base64 encoding.

    The previous hard-coded 1x1 fixture was a real PNG but its IDAT
    chunk was too short to survive a full ``Image.open(...).convert("L")``
    round-trip in newer Pillow versions. 32x32 RGB has enough data for
    every fallback path the test exercises.
    """
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=(128, 128, 128)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_tesseract_fallback_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When pytesseract.image_to_string raises, the fallback logs a warning."""
    from omniscribe.core.ocr import processor

    # Inject a fake pytesseract into sys.modules so the in-function
    # ``import pytesseract`` succeeds, then make image_to_string raise
    # an OSError (which is in the narrow except list).
    fake_pyt = types.ModuleType("pytesseract")
    fake_pyt.image_to_string = MagicMock(  # type: ignore[attr-defined]
        side_effect=OSError("simulated Tesseract failure")
    )

    with caplog.at_level(logging.WARNING, logger=processor.logger.name):
        with patch.dict(sys.modules, {"pytesseract": fake_pyt}):
            proc = processor.OCRProcessor()
            result = proc._get_tesseract_draft(_png_1x1_base64())

    assert result == "", "fallback should return empty string on pytesseract failure"
    assert any(
        "pytesseract" in rec.message.lower() or "tesseract" in rec.message.lower()
        for rec in caplog.records
    ), (
        "expected a warning mentioning the pytesseract fallback, "
        f"got {[r.message for r in caplog.records]}"
    )


def test_adaptive_threshold_fallback_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the adaptive-threshold PIL/numpy pipeline raises, the fallback logs a warning."""
    from omniscribe.core.ocr import processor

    original_base64 = _png_1x1_base64()

    # Patch ``PIL.Image.fromarray`` (a module-level attribute) to raise
    # ``ValueError``; the in-function ``from PIL import Image`` rebinds
    # ``Image`` to the same module, so the patch propagates and the
    # narrow except catches it.
    with caplog.at_level(logging.WARNING, logger=processor.logger.name):
        with patch(
            "PIL.Image.fromarray", side_effect=ValueError("simulated fromarray failure")
        ):
            proc = processor.OCRProcessor()
            result = proc._apply_adaptive_threshold(original_base64)

    assert result == original_base64, (
        "fallback should return the original base64 on adaptive-threshold failure"
    )
    assert any(
        "adaptive" in rec.message.lower() or "threshold" in rec.message.lower()
        for rec in caplog.records
    ), (
        "expected a warning mentioning the adaptive threshold fallback, "
        f"got {[r.message for r in caplog.records]}"
    )


def test_embedder_font_probe_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the embedder font probe raises, it logs a warning instead of swallowing."""
    from omniscribe.core.pdf import embedder

    class _StubFont:
        buffer = b"fake-font-buffer"

        def has_glyph(self, cp: int) -> bool:
            return cp in embedder._PROBE_CODEPOINTS

    with caplog.at_level(logging.WARNING, logger=embedder.logger.name):
        with patch.object(
            embedder.fitz, "open", side_effect=RuntimeError("simulated probe failure")
        ):
            result = embedder._font_preserves_codepoints(_StubFont())

    assert result is True, "font probe fallback should return True on probe failure"
    assert any(
        "font" in rec.message.lower() and "probe" in rec.message.lower()
        for rec in caplog.records
    ), (
        "expected a warning mentioning the font probe, "
        f"got {[r.message for r in caplog.records]}"
    )
