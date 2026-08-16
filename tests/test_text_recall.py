"""Unit tests for the whitespace recall booster (core/text_recall.py)."""

from __future__ import annotations

import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw

from omniscribe.core.text_recall import (
    WhitespaceRecallBooster,
    WhitespaceRecallOptions,
    _overlaps_surya,
    _straddles_surya,
)


def _line_page() -> Image.Image:
    """White 800x1000 page with three dashed black text-like lines.

    Dashes (24px on, 8px off; 16px tall) mimic glyph ink density so the
    candidate passes the density filter while staying clearly line-like.
    Line tops are at y = 100, 200, 300.
    """
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in (100, 200, 300):
        for x in range(80, 720, 32):
            draw.rectangle([x, y, x + 24, y + 16], fill="black")
    return img


def test_recovers_line_missed_by_surya() -> None:
    img = _line_page()
    # Surya covers lines 1 and 2 but misses line 3 (ink at y=300..316).
    surya = [(0.08, 0.095, 0.92, 0.128), (0.08, 0.195, 0.92, 0.228)]
    extra = WhitespaceRecallBooster().supplement(img, surya)
    assert len(extra) == 1
    x0, y0, x1, y1 = extra[0]
    assert y0 < 0.31 < y1
    assert x0 < 0.15 and x1 > 0.85


def test_rules_only_page_yields_no_boxes() -> None:
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in (150, 400, 650):
        draw.rectangle([40, y, 760, y + 2], fill="black")
    assert WhitespaceRecallBooster().supplement(img, []) == []


def test_blank_page_yields_no_boxes() -> None:
    img = Image.new("RGB", (800, 1000), "white")
    assert WhitespaceRecallBooster().supplement(img, []) == []


def test_zero_by_zero_image_yields_no_boxes() -> None:
    # eng-new: a degenerate raster must not raise; ``gray.size == 0``
    # short-circuits before any cv2 stats run.
    img = Image.new("RGB", (0, 0))
    assert WhitespaceRecallBooster().supplement(img, []) == []


# Isolated filter-gate fixtures (eng-new). Page geometry is 800x1000 so the
# dilation kernel lands at kw=16, kh=6 (components inflate by kw-1 / kh-1);
# surya_boxes=[] selects the fallback height band [6px, 60px]. Each fixture
# is sized so exactly one gate fires.


def test_aspect_gate_rejects_tall_narrow_component() -> None:
    # Vertical dash column: 6 six-by-five dashes on a 7px pitch merge into
    # one ~21x49px component â€” wide enough for the height/area/density
    # gates, too narrow for the 2:1 aspect floor.
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(400, 440, 7):
        draw.rectangle([400, y, 405, y + 4], fill="black")
    assert WhitespaceRecallBooster().supplement(img, []) == []


def test_area_gate_rejects_wide_tall_component() -> None:
    # A 15-row dashed block (~735x315px post-dilation) passes aspect, the
    # 2.5x height cap (median 0.3 -> cap 0.75), and density, but its ~0.29
    # normalized area crosses the 0.25 ceiling.
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(200, 500, 21):
        for x in range(40, 760, 32):
            draw.rectangle([x, y, x + 24, y + 16], fill="black")
    surya = [(0.05, 0.6, 0.95, 0.9)]  # below the block: no dedup overlap
    assert WhitespaceRecallBooster().supplement(img, surya) == []


def test_max_density_gate_rejects_solid_blob() -> None:
    # A solid 600x40 bar: the pre-dilation mask fills ~87% of the
    # post-dilation bbox, above the 0.75 text-ink ceiling; aspect, height,
    # and area all pass.
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 400, 700, 440], fill="black")
    assert WhitespaceRecallBooster().supplement(img, []) == []


def test_candidate_inside_surya_box_is_dropped() -> None:
    img = _line_page()
    surya = [(0.05, 0.28, 0.95, 0.36)]  # fully covers line 3
    assert WhitespaceRecallBooster().supplement(img, surya) == []


def test_overlaps_surya_iou_branch() -> None:
    candidate = (0.1, 0.1, 0.9, 0.14)
    # Same-size box shifted down: containment ~0.48 stays below the 0.5
    # threshold while IoU ~0.31 crosses the 0.3 threshold.
    assert _overlaps_surya(candidate, [(0.1, 0.121, 0.9, 0.161)]) is True
    # No intersection at all: neither branch fires.
    assert _overlaps_surya(candidate, [(0.1, 0.2, 0.9, 0.24)]) is False


def test_straddle_guard_rejects_gutter_crossing_candidate() -> None:
    # Wide candidate spanning two column boxes, overlapping each ~25%.
    candidate = (0.1, 0.1, 0.9, 0.15)
    columns = [(0.1, 0.08, 0.45, 0.5), (0.55, 0.08, 0.9, 0.5)]
    assert _straddles_surya(candidate, columns) is True
    # Same candidate beside a single column: no straddle.
    assert _straddles_surya(candidate, [(0.1, 0.08, 0.45, 0.5)]) is False
    # Touches two boxes but each overlap is negligible: not a straddle.
    assert (
        _straddles_surya(candidate, [(0.09, 0.1, 0.11, 0.15), (0.89, 0.1, 0.91, 0.15)])
        is False
    )


def test_gutter_straddle_candidate_dropped_end_to_end() -> None:
    # Two text columns with a tight gutter; dilation can bridge the gap
    # into one wide component spanning both columns. Surya sees both
    # columns, so the bridging candidate must be rejected, not emitted.
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in (200, 260):
        for col_x0 in (60, 420):
            for x in range(col_x0, col_x0 + 300, 32):
                draw.rectangle([x, y, x + 26, y + 16], fill="black")
    surya = [(0.07, 0.19, 0.46, 0.29), (0.52, 0.19, 0.91, 0.29)]
    extra = WhitespaceRecallBooster().supplement(img, surya)
    assert all(not (x0 < 0.5 < x1) for x0, _y0, x1, _y1 in extra)


def test_photo_region_does_not_become_box() -> None:
    # Solid dark rectangle standing in for a photographic region: Otsu
    # binarizes it into a dense component that must not pass the filters
    # (density ~1.0 far exceeds the 0.75 ceiling).
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 400, 700, 600], fill=(30, 30, 30))
    extra = WhitespaceRecallBooster().supplement(img, [])
    assert all(not (y0 < 0.5 < y1 and x0 < 0.5 < x1) for x0, y0, x1, y1 in extra)


def test_dark_inverted_page_yields_no_boxes() -> None:
    # Black background with light "text": Otsu-invert's whitespace model
    # breaks (foreground fraction > 0.5), so the page is skipped wholesale.
    img = Image.new("RGB", (800, 1000), "black")
    draw = ImageDraw.Draw(img)
    for y in (100, 200, 300):
        for x in range(80, 720, 32):
            draw.rectangle([x, y, x + 24, y + 16], fill="white")
    assert WhitespaceRecallBooster().supplement(img, []) == []


def test_per_page_cap_bounds_output() -> None:
    # 14 well-separated dashed lines: every one passes the filters, so the
    # per-page cap (10) must trim the output.
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(40, 950, 64):
        for x in range(80, 720, 32):
            draw.rectangle([x, y, x + 24, y + 16], fill="black")
    extra = WhitespaceRecallBooster().supplement(img, [])
    assert 0 < len(extra) <= 10


def test_zero_height_surya_boxes_do_not_disable_height_floor() -> None:
    # Page with the usual three 16px-tall dashed lines plus a 6px-tall
    # noise line at y=500 (dilation grows it to ~12px, below the ~15px
    # median height floor but above the 10px pixel floor). If degenerate
    # zero-height boxes dragged the median to zero, the noise line would
    # slip through.
    img = _line_page()
    draw = ImageDraw.Draw(img)
    for x in range(80, 720, 32):
        draw.rectangle([x, 500, x + 24, 506], fill="black")
    surya = [
        (0.1, 0.05, 0.9, 0.05),  # degenerate zero-height boxes (majority)
        (0.1, 0.4, 0.9, 0.4),
        (0.1, 0.7, 0.9, 0.7),
        (0.08, 0.095, 0.92, 0.128),  # covers line 1
        (0.08, 0.195, 0.92, 0.228),  # covers line 2
    ]
    extra = WhitespaceRecallBooster().supplement(img, surya)
    assert len(extra) == 1  # only line 3; noise line stays filtered
    _x0, y0, _x1, y1 = extra[0]
    assert y0 < 0.31 < y1


def test_all_zero_height_surya_boxes_fall_back() -> None:
    img = _line_page()
    surya = [(0.1, 0.5, 0.9, 0.5), (0.1, 0.6, 0.9, 0.6)]
    # Falls back to the absolute min height; must not raise.
    extra = WhitespaceRecallBooster().supplement(img, surya)
    assert all(y1 - y0 > 0 for _x0, y0, _x1, y1 in extra)


def test_disabled_options_return_no_boxes() -> None:
    img = _line_page()
    booster = WhitespaceRecallBooster(WhitespaceRecallOptions(enabled=False))
    assert booster.supplement(img, []) == []


def test_candidates_dropped_counter_tracks_filtered_components() -> None:
    # T2: the engine's INFO run summary reads this counter as a delta.
    booster = WhitespaceRecallBooster()
    assert booster.candidates_dropped == 0

    img = _line_page()
    # Three line components: line 3 is recovered, lines 1-2 are dedup-
    # dropped against the covering Surya boxes.
    surya = [(0.08, 0.095, 0.92, 0.128), (0.08, 0.195, 0.92, 0.228)]
    extra = booster.supplement(img, surya)
    assert len(extra) == 1
    assert booster.candidates_dropped == 2

    # Accumulates across calls: three hairline-rule components, all
    # rejected by the filters.
    rules = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(rules)
    for y in (150, 400, 650):
        draw.rectangle([40, y, 760, y + 2], fill="black")
    assert booster.supplement(rules, []) == []
    assert booster.candidates_dropped == 5


def test_disabled_booster_leaves_counter_at_zero() -> None:
    booster = WhitespaceRecallBooster(WhitespaceRecallOptions(enabled=False))
    assert booster.supplement(_line_page(), []) == []
    assert booster.candidates_dropped == 0


def test_missing_cv2_is_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    # sys.modules["cv2"] = None makes `import cv2` raise ImportError.
    monkeypatch.setitem(sys.modules, "cv2", None)
    img = _line_page()
    assert WhitespaceRecallBooster().supplement(img, []) == []


class TestWhitespaceRecallOptionsFromEnv:
    def test_default_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_WHITESPACE_RECALL", raising=False)
        assert WhitespaceRecallOptions.from_env().enabled is True

    @pytest.mark.parametrize(
        "value",
        [
            "0",
            "false",
            "no",
            "off",
            "n",
            "disabled",
            "FALSE",
            " Off ",
            "N",
            " Disabled ",
        ],
    )
    def test_disable_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", value)
        assert WhitespaceRecallOptions.from_env().enabled is False

    def test_unrecognized_value_stays_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", "banana")
        assert WhitespaceRecallOptions.from_env().enabled is True


def test_photo_edge_page_returns_image_with_expected_shape() -> None:
    """Pins the synthetic helper's output shape and line position.

    The helper is consumed by ``test_photo_edge_passes_filters_as_known_limitation``
    in this file. This test pins the helper's contract independently so a
    regression in the helper is identifiable separately from a regression in
    the booster.
    """
    img = _photo_edge_page(
        line_height_px=14,
        line_width_px=800,
        density=0.40,
    )
    assert img.size == (1000, 1400)
    # White background check: top-left pixel must be near-white.
    assert img.getpixel((10, 10))[0] > 240
    # The line sits at y = 0.5 * 1400 = 700. Inside the line region the
    # pixel must be darker than the background. The pre-dilation density
    # is 0.40, so on average 60% of pixels in the line are white and 40%
    # are dark — sampling the center of the line should find a dark pixel
    # at least once across 5 samples.
    samples = [img.getpixel((200 + i * 100, 700)) for i in range(5)]
    assert any(px[0] < 100 for px in samples), (
        f"no dark pixel found in line region (samples={samples})"
    )


def _photo_edge_page(
    *,
    line_y_frac: float = 0.5,
    line_height_px: int,
    line_width_px: int,
    density: float,
    page_w: int = 1000,
    page_h: int = 1400,
) -> Image.Image:
    """Return a white ``Image`` with one horizontal line at ``y = line_y_frac * page_h``.

    The line has the given pixel height, width, and ink ``density``. The
    density is the *pre-dilation* ink fraction inside the line rect, which
    maps directly to the booster's ``_MIN_INK_DENSITY`` / ``_MAX_INK_DENSITY``
    checks at ``src/omniscribe/core/text_recall.py:51-52``. Dilation in the
    booster will inflate connectivity but the density check uses the
    pre-dilation mask, so the asserted density must be the pre-dilation value.

    The RNG is seeded deterministically from ``(line_height_px, density,
    line_width_px)`` so the same parameters always produce the same image —
    the test is reproducible and a regression in this helper is traceable.

    Consumed by ``test_photo_edge_passes_filters_as_known_limitation`` to
    produce a line-shape that exercises the booster's height + density
    filters without needing a real photo or scanned page.
    """
    seed = int(line_height_px * 1_000_000 + int(density * 1000) * 1000 + line_width_px)
    rng = np.random.default_rng(seed)

    img = Image.new("RGB", (page_w, page_h), (255, 255, 255))
    arr = np.array(img)

    y_start = int(line_y_frac * page_h) - line_height_px // 2
    y_end = y_start + line_height_px
    x_start = (page_w - line_width_px) // 2
    x_end = x_start + line_width_px

    # Build the line as a random mask with the requested ink density.
    line_pixels = arr[y_start:y_end, x_start:x_end]
    mask_shape = line_pixels.shape[:2]
    keep = rng.random(mask_shape) < density
    # Ink pixels are dark; background pixels stay white.
    line_pixels[keep] = (0, 0, 0)
    line_pixels[~keep] = (255, 255, 255)
    arr[y_start:y_end, x_start:x_end] = line_pixels

    return Image.fromarray(arr)

