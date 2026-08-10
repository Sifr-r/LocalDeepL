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
        assert sample == (255, 255, 255) or sample[0] >= 250


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
