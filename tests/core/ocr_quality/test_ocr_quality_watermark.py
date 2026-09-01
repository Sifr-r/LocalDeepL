"""Tests for :mod:`omniscribe.core.ocr_quality.watermark`."""

from __future__ import annotations

import pytest
from PIL import Image

from omniscribe.core.ocr_quality import watermark
from omniscribe.core.ocr_quality.types import WatermarkHit


def _white_image(size: tuple[int, int] = (200, 200)) -> Image.Image:
    return Image.new("RGB", size, (255, 255, 255))


def _watermarked_image(size: tuple[int, int] = (400, 400)) -> Image.Image:
    img = _white_image(size)
    # Diagonal light-gray stripe across the page.
    pixels = img.load()
    assert pixels is not None
    for y in range(40, 80):
        for x in range(size[0]):
            pixels[x, y] = (230, 230, 230)
    return img


class TestPassthrough:
    def test_none_image_returns_none(self):
        out, hit = watermark.detect(None)
        assert out is None
        assert hit is None

    def test_clean_white_image_returns_none_hit(self):
        out, hit = watermark.detect(_white_image())
        assert isinstance(out, Image.Image)
        assert hit is None

    def test_hint_overrides_detection(self):
        img = _white_image()
        hint = WatermarkHit(bbox=(0.0, 0.0, 0.5, 0.1), confidence=0.9)
        out, hit = watermark.detect(img, hint=hint)
        assert hit is hint
        assert out is not None

    def test_aggressiveness_zero_returns_unchanged(self):
        img = _watermarked_image()
        out, _hit = watermark.detect(img, aggressiveness=0.0)
        # Output must be the same image when aggressiveness == 0; hit may
        # still be detected but no mask is applied.
        assert out.tobytes() == img.tobytes()


class TestDetection:
    def test_synthetic_band_returns_hit(self):
        img = _watermarked_image()
        _, hit = watermark.detect(img, aggressiveness=0.0)
        assert hit is not None
        assert hit.bbox is not None

    def test_aggressiveness_one_applies_mask(self):
        img = _watermarked_image()
        out, _ = watermark.detect(img, aggressiveness=1.0)
        # The band region must be whitened in the output.
        pixel = out.load()
        assert pixel is not None
        sample = pixel[200, 50]
        assert sample == (255, 255, 255) or sample[0] >= 250  # type: ignore[index]


class TestErrorHandling:
    def test_huge_image_passes_through(self):
        # PIL refuses to allocate 20000x20000 in CI; we mock instead by
        # crafting a small image and monkeypatching the guard constant.
        from omniscribe.core.ocr_quality import watermark as wm

        original = wm._MAX_IMAGE_PIXELS
        wm._MAX_IMAGE_PIXELS = 1  # any image > 1 px trips the guard
        try:
            out, hit = wm.detect(_white_image())
            assert isinstance(out, Image.Image)
            assert hit is None
        finally:
            wm._MAX_IMAGE_PIXELS = original


@pytest.fixture(autouse=True)
def _suppress_logs(caplog):
    caplog.set_level("DEBUG")


# ---------------------------------------------------------------------------
# F1.11 — numpy-vectorised watermark detector
# (re-homed from test_audit_medium_d1.py)
# ---------------------------------------------------------------------------


class TestNumpyWatermarkVectorization:
    """F1.11 audit fix: ``_midgray_fraction`` is now vectorised with
    numpy when numpy is available, with a pure-Python fallback when
    it is not. Both paths must produce the same per-row fractions.
    """

    def test_numpy_path_matches_pure_python(self) -> None:
        """Run the same synthetic image through the numpy path (the
        default) and the explicit pure-Python fallback, and assert the
        per-row fractions are identical.
        """
        # 200x300 image: 200 rows, sample_step = max(1, 200//64) = 3,
        # sample_count = (200 + 3 - 1) // 3 = 67.
        img = Image.new("RGB", (200, 300), (255, 255, 255))
        # Draw a band in the watermark mid-gray range.
        pixels = img.load()
        assert pixels is not None
        for y in range(40, 60):
            for x in range(200):
                pixels[x, y] = (220, 220, 220)

        np_result = watermark._midgray_fraction(img)
        gray = img.convert("L")
        py_result = watermark._midgray_fraction_pure_python(
            gray, sample_step=3, sample_count=67, h=300
        )
        assert np_result == py_result

    def test_band_rows_have_high_fraction(self) -> None:
        """Sanity: rows in the band have a fraction close to 1.0;
        clean rows have a fraction close to 0.0."""
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        pixels = img.load()
        assert pixels is not None
        for y in range(40, 60):
            for x in range(200):
                pixels[x, y] = (220, 220, 220)
        fracs = watermark._midgray_fraction(img)
        # A clean row (e.g. y=0) has 0% mid-gray pixels.
        assert fracs[0] < 0.05
        # A band row (e.g. y=50) has near 100% mid-gray pixels.
        assert fracs[50] > 0.95

    def test_falls_back_when_numpy_unavailable(self, monkeypatch) -> None:
        """When numpy cannot be imported, ``_midgray_fraction`` falls
        back to the pure-Python implementation rather than raising.
        """
        # Simulate "numpy not installed" by making the import fail.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "numpy" or name.startswith("numpy."):
                raise ImportError("numpy is not available (test simulation)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        img = Image.new("RGB", (200, 100), (255, 255, 255))
        fracs = watermark._midgray_fraction(img)
        # Should not raise; should return valid fractions.
        assert len(fracs) == 100
        assert all(0.0 <= f <= 1.0 for f in fracs)
