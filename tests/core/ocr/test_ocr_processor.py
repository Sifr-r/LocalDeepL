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

from omniscribe.core.ocr.processor import OCRProcessor


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
    from omniscribe.core.pdf import embedder, embedder_helpers

    class _StubFont:
        buffer = b"fake-font-buffer"

        def has_glyph(self, cp: int) -> bool:
            return cp in embedder_helpers._PROBE_CODEPOINTS

    with caplog.at_level(logging.WARNING, logger=embedder.logger.name):
        with patch.object(
            embedder.fitz, "open", side_effect=RuntimeError("simulated probe failure")
        ):
            result = embedder_helpers._font_preserves_codepoints(_StubFont())  # type: ignore[arg-type]

    assert result is True, "font probe fallback should return True on probe failure"
    assert any(
        "font" in rec.message.lower() and "probe" in rec.message.lower()
        for rec in caplog.records
    ), (
        "expected a warning mentioning the font probe, "
        f"got {[r.message for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# F1.9 — instance-level env settings (re-homed from test_audit_medium_d1.py)
# ---------------------------------------------------------------------------


class TestInstanceLevelSettings:
    """F1.9 audit fix: ``OCRProcessor.__init__`` resolves the audit-H3
    knobs from ``RuntimeSettings`` at instance construction, not at
    module import. A fresh ``OCRProcessor()`` after an env change
    must see the new value.
    """

    def test_instance_attrs_resolved_from_settings(self) -> None:
        # ``__new__`` skips ``__init__`` so the F1.9 fallback ``__getattr__``
        # returns the class-level defaults. We exercise both paths here:
        # the class-level constants are the safe fallback, and the
        # instance-level values override them.
        proc = OCRProcessor(api_base="http://test.local/v1", api_key="x", model="mock")
        # Per-instance fields exist and are the same type as the
        # class-level defaults.
        assert isinstance(proc.page_timeout_s, float)
        assert isinstance(proc.crop_timeout_s, float)
        assert isinstance(proc.max_retries, int)
        assert isinstance(proc.retry_base_delay_s, float)
        assert isinstance(proc.page_max_tokens, int)
        assert isinstance(proc.crop_max_tokens, int)

    def test_instance_attrs_default_to_class_constants(self) -> None:
        """``__getattr__`` falls back to the class-level constants when
        the instance was built without ``__init__`` (e.g. via
        ``OCRProcessor.__new__``). This is the legacy test path and
        must keep working.
        """
        proc = OCRProcessor.__new__(OCRProcessor)  # skip real init
        assert proc.crop_timeout_s == OCRProcessor.CROP_TIMEOUT_S
        assert proc.page_timeout_s == OCRProcessor.PAGE_TIMEOUT_S
        assert proc.max_retries == OCRProcessor.MAX_RETRIES
        assert proc.crop_max_tokens == OCRProcessor.CROP_MAX_TOKENS


# ---------------------------------------------------------------------------
# F1.13 — Tesseract error counter (re-homed from test_audit_medium_d1.py)
# ---------------------------------------------------------------------------


class TestTesseractErrorCounter:
    """F1.13 audit fix: ``OCRProcessor.tesseract_error_count`` is
    incremented on every Tesseract fallback failure so the API layer
    can surface a stuck dual-engine path in the job-completion
    summary without log scraping.
    """

    def test_initial_counter_is_zero(self) -> None:
        proc = OCRProcessor(api_base="http://test.local/v1", api_key="x", model="mock")
        assert proc.tesseract_error_count == 0

    def test_counter_increments_on_tesseract_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tesseract failure (TesseractError / RuntimeError) must
        increment the counter; a successful call must not.
        """
        # Skip the test entirely when pytesseract is not installed
        # (it's a soft dep — the dual-engine path is best-effort).
        pytest.importorskip("pytesseract")
        proc = OCRProcessor(api_base="http://test.local/v1", api_key="x", model="mock")

        # First call: simulate a tesseract failure.
        import pytesseract

        def raise_tesseract(*args, **kwargs):
            raise pytesseract.TesseractError(1, "tesseract boom")

        monkeypatch.setattr(pytesseract, "image_to_string", raise_tesseract)
        result = proc._get_tesseract_draft("aW1hZ2U=")
        assert result == ""
        assert proc.tesseract_error_count == 1

        # Second call: same failure, counter increments again.
        result = proc._get_tesseract_draft("aW1hZ2U=")
        assert result == ""
        assert proc.tesseract_error_count == 2

        # Third call: a successful tesseract. Counter must NOT increment.
        monkeypatch.setattr(
            pytesseract, "image_to_string", lambda *a, **kw: "  recovered text  "
        )
        result = proc._get_tesseract_draft("aW1hZ2U=")
        assert result == "recovered text"
        assert proc.tesseract_error_count == 2
