"""Tests for :mod:`omniscribe.core.handwriting_preprocessor`."""

from __future__ import annotations

import numpy as np

from omniscribe.core.handwriting_preprocessor import (
    HandwritingOptions,
    estimate_stroke_width,
    is_handwritten_page,
    normalize_stroke_width,
    sauvola_binarize,
)


def test_sauvola_binarize_produces_binary_image():
    img = np.full((100, 100), 200, dtype=np.uint8)
    img[20:40, 20:80] = 30
    out = sauvola_binarize(img, window=15)
    assert set(np.unique(out).tolist()).issubset({0, 255})
    # The dark region should mostly be black in the output
    assert out[25, 50] == 0


def test_estimate_stroke_width_runs():
    # Solid bar, 10px wide
    binary = np.full((50, 50), 255, dtype=np.uint8)
    binary[20:30, 10:40] = 0
    sw = estimate_stroke_width(binary)
    # The distance transform should report a value > 0
    assert sw > 0


def test_normalize_stroke_width_idempotent():
    binary = np.full((50, 50), 255, dtype=np.uint8)
    binary[20:30, 10:40] = 0
    out = normalize_stroke_width(binary, target=4.0)
    # Same shape, still binary
    assert out.shape == binary.shape
    assert set(np.unique(out).tolist()).issubset({0, 255})


def test_is_handwritten_page_dense_text_returns_something():
    # Build a synthetic "handwriting-like" image: low ink density, irregular
    rng = np.random.default_rng(42)
    img = np.full((200, 200), 255, dtype=np.uint8)
    # Add some random sparse dark pixels
    coords = rng.integers(0, 200, size=(200, 2))
    for x, y in coords:
        img[y, x] = 0
    b64 = _arr_to_b64(img)
    # We only care that this doesn't crash; result may be True or False.
    result = is_handwritten_page(b64)
    assert isinstance(result, bool)


def test_sauvola_binarize_matches_pre_hoist_formulation():
    """§1.6 regression: hoisting the ``astype(np.float32)`` cast is semantics-preserving.

    The optimization rebinds ``gray_f32 = gray.astype(np.float32)`` once and
    reuses it across the mean / sqmean / threshold-comparison sites, eliminating
    two redundant float-buffer allocations per page. Assert byte-for-byte
    equivalence with the pre-hoist formulation on a deterministic input so a
    future change to the cast site cannot silently alter the threshold.
    """
    import cv2

    from omniscribe.core.handwriting_preprocessor import sauvola_binarize

    rng = np.random.default_rng(2026)
    gray = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    window = 15
    k = 0.2
    r = 128.0

    # Pre-hoist formulation (three separate astype calls).
    mean_old = cv2.boxFilter(gray.astype(np.float32), ddepth=-1, ksize=(window, window))
    sqmean_old = cv2.boxFilter(
        (gray.astype(np.float32)) ** 2, ddepth=-1, ksize=(window, window)
    )
    var_old = np.maximum(sqmean_old - mean_old * mean_old, 0.0)
    std_old = np.sqrt(var_old)
    threshold_old = mean_old * (1.0 + k * (std_old / r - 1.0))
    expected = np.where(gray.astype(np.float32) < threshold_old, 0.0, 255.0).astype(
        np.uint8
    )

    # Hoisted formulation (one astype call, reused).
    actual = sauvola_binarize(gray, window=window, k=k, r=r)

    assert actual.shape == expected.shape
    assert actual.dtype == np.uint8
    # The two formulations must be byte-identical on this deterministic input.
    assert np.array_equal(actual, expected)


def test_handwriting_options_is_noop():
    # An instance with every transformation flag disabled is a no-op.
    assert HandwritingOptions(
        enabled=False,
        binarize=False,
        normalize_stroke_width=False,
        normalize_slant=False,
    ).is_noop()
    # Any flag set means we will do work.
    assert not HandwritingOptions(enabled=True).is_noop()
    assert not HandwritingOptions(binarize=True).is_noop()


def _arr_to_b64(arr: np.ndarray) -> str:
    import base64

    import cv2

    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")
