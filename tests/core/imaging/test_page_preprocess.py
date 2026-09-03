"""Unit tests for :mod:`omniscribe.core.imaging.page_preprocess`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import cast

import numpy as np
import pytest
from PIL import Image, ImageDraw

from omniscribe.core.imaging.page_preprocess import (
    CompositePagePreprocessor,
    LocalPagePreprocessor,
    PagePreprocessingOptions,
    PagePreprocessingResult,
    _correct_orientation,
    _deskew,
    _normalize_contrast,
    _trim_border,
)
from omniscribe.core.imaging.utils import decode_base64_image, encode_image_base64


def _create_test_image_b64(
    width: int = 120,
    height: int = 80,
    color: tuple[int, int, int] = (255, 255, 255),
) -> str:
    """Helper creating a plain RGB image as base64 PNG."""
    img = Image.new("RGB", (width, height), color=color)
    return encode_image_base64(img)


# ==============================================================================
# PagePreprocessingOptions & PagePreprocessingResult tests
# ==============================================================================


def test_page_preprocessing_options_defaults():
    options = PagePreprocessingOptions()
    assert options.enabled is False
    assert options.orientation_detection is False
    assert options.deskew is False
    assert options.denoise is False
    assert options.normalize_contrast is False
    assert options.crop_cleanup is False


def test_page_preprocessing_options_custom_and_immutability():
    options = PagePreprocessingOptions(
        enabled=True,
        orientation_detection=True,
        deskew=True,
        denoise=False,
        normalize_contrast=True,
        crop_cleanup=True,
    )
    assert options.enabled is True
    assert options.orientation_detection is True
    assert options.deskew is True
    assert options.denoise is False
    assert options.normalize_contrast is True
    assert options.crop_cleanup is True

    with pytest.raises(FrozenInstanceError):
        options.enabled = False  # type: ignore[misc]


def test_page_preprocessing_result_structure():
    result_default = PagePreprocessingResult(images={0: "img_0"})
    assert result_default.images == {0: "img_0"}
    assert result_default.metadata == {}

    custom_meta: dict[int, dict[str, object]] = {0: {"key": "val"}}
    result_custom = PagePreprocessingResult(images={0: "img_0"}, metadata=custom_meta)
    assert result_custom.images == {0: "img_0"}
    assert result_custom.metadata == {0: {"key": "val"}}


# ==============================================================================
# CompositePagePreprocessor tests
# ==============================================================================


class _DummyPreprocessor:
    """Mock preprocessor for verifying pipeline composition and metadata merging."""

    def __init__(self, step_name: str, suffix: str = ""):
        self.step_name = step_name
        self.suffix = suffix

    def preprocess(
        self,
        images: Mapping[int, str],
        options: PagePreprocessingOptions,
    ) -> PagePreprocessingResult:
        updated_images = {k: f"{v}_{self.suffix}" for k, v in images.items()}
        metadata = {
            k: {self.step_name: True, f"{self.step_name}_tag": self.suffix}
            for k in images
        }
        return PagePreprocessingResult(images=updated_images, metadata=metadata)


def test_composite_preprocessor_empty_list():
    composite = CompositePagePreprocessor([])
    images = {0: "page_0_data", 1: "page_1_data"}
    options = PagePreprocessingOptions(enabled=True)

    result = composite.preprocess(images, options)

    assert result.images == images
    # Every input page receives an initial empty dict in metadata
    assert result.metadata == {0: {}, 1: {}}


def test_composite_preprocessor_chains_multiple_stages():
    p1 = _DummyPreprocessor(step_name="step1", suffix="p1")
    p2 = _DummyPreprocessor(step_name="step2", suffix="p2")
    composite = CompositePagePreprocessor([p1, p2])

    images = {0: "raw0", 1: "raw1"}
    options = PagePreprocessingOptions(enabled=True)

    result = composite.preprocess(images, options)

    assert result.images == {0: "raw0_p1_p2", 1: "raw1_p1_p2"}
    assert result.metadata[0] == {
        "step1": True,
        "step1_tag": "p1",
        "step2": True,
        "step2_tag": "p2",
    }
    assert result.metadata[1] == {
        "step1": True,
        "step1_tag": "p1",
        "step2": True,
        "step2_tag": "p2",
    }


# ==============================================================================
# Functional Transformation Tests: Orientation, Deskew, Contrast, Crop Cleanup
# ==============================================================================


def test_composite_with_local_preprocessor_disabled():
    preprocessor = CompositePagePreprocessor([LocalPagePreprocessor()])
    b64 = _create_test_image_b64(100, 100)
    images = {0: b64}
    options = PagePreprocessingOptions(enabled=False, orientation_detection=True)

    result = preprocessor.preprocess(images, options)

    assert result.images[0] == b64
    assert result.metadata[0] == {}


def test_orientation_detection_with_exif():
    # Construct an image with EXIF orientation tag 6 (270 deg rotation / 90 CW)
    img = Image.new("RGB", (120, 60), color=(240, 240, 240))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: Rotate 90 CW (exif_transpose swaps width/height)
    img._getexif = lambda: exif  # type: ignore[attr-defined]

    corrected, meta = _correct_orientation(img)
    assert meta["method"] == "exif_transpose"
    assert meta["rotated"] is True
    assert corrected.size == (60, 120)


def test_orientation_detection_without_rotation():
    img = Image.new("RGB", (100, 50), color=(250, 250, 250))
    corrected, meta = _correct_orientation(img)
    assert meta["method"] == "exif_transpose"
    assert meta["rotated"] is False
    assert corrected.size == (100, 50)


def test_crop_cleanup_border_trimming():
    # 200x200 white canvas with a 100x80 black box in the middle:
    # offset_x = 40, offset_y = 50, max_x = 140, max_y = 130
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 50, 139, 129], fill=(0, 0, 0))

    cropped, meta = _trim_border(img)
    assert meta["trimmed"] is True
    assert meta["crop_width"] == 100
    assert meta["crop_height"] == 80
    assert meta["offset"] == [40, 50]
    assert meta["original_width"] == 200
    assert meta["original_height"] == 200
    assert cropped.size == (100, 80)


def test_crop_cleanup_no_trimming_needed():
    # Full black canvas (no white borders to trim)
    img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    cropped, meta = _trim_border(img)
    assert meta["trimmed"] is False
    assert cropped.size == (100, 100)

    # Completely white canvas (inverted bbox is None)
    blank = Image.new("RGB", (100, 100), color=(255, 255, 255))
    cropped_blank, meta_blank = _trim_border(blank)
    assert meta_blank["trimmed"] is False
    assert cropped_blank.size == (100, 100)


def test_contrast_normalization():
    # Array with low-contrast gray levels
    low_contrast = np.full((128, 128, 3), 128, dtype=np.uint8)
    low_contrast[40:80, 40:80] = 135

    normalized = _normalize_contrast(low_contrast)
    assert normalized.shape == low_contrast.shape
    assert normalized.dtype == np.uint8
    # Contrast normalization modifies pixel distributions
    assert not np.array_equal(normalized, low_contrast)


def test_deskew_tilted_content():
    # Create an image with a rotated black bar on a white background
    img = Image.new("RGB", (250, 250), color=(255, 255, 255))
    bar = Image.new("RGB", (160, 30), color=(0, 0, 0))
    rotated_bar = bar.rotate(15, expand=True, fillcolor=(255, 255, 255))
    img.paste(rotated_bar, (40, 40))

    arr = np.array(img)
    deskewed, angle = _deskew(arr)

    assert deskewed.shape == arr.shape
    assert isinstance(angle, float)
    assert abs(angle) > 0.1


def test_deskew_blank_or_few_points_returns_zero_angle():
    white_canvas = np.full((100, 100, 3), 255, dtype=np.uint8)
    deskewed, angle = _deskew(white_canvas)
    assert angle == 0.0
    assert np.array_equal(deskewed, white_canvas)


def test_composite_with_local_preprocessor_end_to_end():
    # End-to-end integration through CompositePagePreprocessor
    composite = CompositePagePreprocessor([LocalPagePreprocessor()])

    # Canvas with white margin and center content
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, 170, 170], fill=(50, 50, 50))
    b64 = encode_image_base64(img)

    options = PagePreprocessingOptions(
        enabled=True,
        crop_cleanup=True,
        normalize_contrast=True,
        denoise=True,
        deskew=True,
        orientation_detection=True,
    )

    result = composite.preprocess({0: b64}, options)

    assert 0 in result.images
    meta = result.metadata[0]
    assert meta["enabled"] is True
    operations = cast(list[str], meta["operations"])
    assert "orientation_detection" in operations
    assert "crop_cleanup" in operations
    assert "normalize_contrast" in operations
    assert "denoise" in operations
    assert "deskew" in operations

    # Confirm decoded output is a valid PIL Image
    decoded = decode_base64_image(result.images[0])
    assert decoded.width > 0
    assert decoded.height > 0
