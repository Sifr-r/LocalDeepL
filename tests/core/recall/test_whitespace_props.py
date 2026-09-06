"""Property-based tests for whitespace recall in :mod:`omniscribe.core.recall.whitespace`."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from omniscribe.core.document import BBox
from omniscribe.core.recall.whitespace import (
    _MAX_RECALL_BOXES_PER_PAGE,
    WhitespaceRecallBooster,
    WhitespaceRecallOptions,
    _clamp,
    _overlaps_surya,
    _straddles_surya,
)

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_norm_coord = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)


@st.composite
def bbox_strategy(draw: st.DrawFn) -> BBox:
    c1, c2 = draw(_norm_coord), draw(_norm_coord)
    c3, c4 = draw(_norm_coord), draw(_norm_coord)
    x0, x1 = min(c1, c2), max(c1, c2)
    y0, y1 = min(c3, c4), max(c3, c4)
    return (x0, y0, x1, y1)


_surya_boxes_strat = st.lists(bbox_strategy(), max_size=10)


@settings(max_examples=100, deadline=None)
@given(
    val=st.integers(min_value=-1000, max_value=1000),
    b1=st.integers(min_value=-500, max_value=500),
    b2=st.integers(min_value=-500, max_value=500),
)
def test_clamp_invariants(val: int, b1: int, b2: int) -> None:
    """_clamp always returns a value within [lo, hi]."""
    lo, hi = min(b1, b2), max(b1, b2)
    clamped = _clamp(val, (lo, hi))
    assert lo <= clamped <= hi
    if lo <= val <= hi:
        assert clamped == val


@settings(max_examples=100, deadline=None)
@given(box=bbox_strategy())
def test_overlaps_surya_self_detection(box: BBox) -> None:
    """A candidate with non-trivial area identical to a Surya box is detected as overlapping."""
    x0, y0, x1, y1 = box
    if (x1 - x0) > 1e-4 and (y1 - y0) > 1e-4:
        assert _overlaps_surya(box, [box]) is True


@settings(max_examples=100, deadline=None)
@given(candidate=bbox_strategy(), surya_boxes=_surya_boxes_strat)
def test_overlaps_and_straddles_return_bool(
    candidate: BBox, surya_boxes: list[BBox]
) -> None:
    """Overlap and straddle predicates always return a boolean without error."""
    assert isinstance(_overlaps_surya(candidate, surya_boxes), bool)
    assert isinstance(_straddles_surya(candidate, surya_boxes), bool)


@settings(max_examples=100, deadline=None)
@given(
    width=st.integers(min_value=60, max_value=300),
    height=st.integers(min_value=60, max_value=300),
    bg_color=st.integers(min_value=200, max_value=255),
    line_y=st.integers(min_value=20, max_value=40),
    surya_boxes=_surya_boxes_strat,
)
def test_candidate_boxes_normalized_coordinates(
    width: int,
    height: int,
    bg_color: int,
    line_y: int,
    surya_boxes: list[BBox],
) -> None:
    """Candidate boxes must have normalized coordinates in [0.0, 1.0] with x0 <= x1, y0 <= y1."""
    img = Image.new("RGB", (width, height), color=(bg_color, bg_color, bg_color))
    draw = ImageDraw.Draw(img)

    # Draw synthetic text-like lines (dark horizontal bars)
    actual_line_y = min(line_y, height - 20)
    draw.rectangle(
        [10, actual_line_y, width - 10, actual_line_y + 12], fill=(10, 10, 10)
    )

    booster = WhitespaceRecallBooster()
    candidates = booster.supplement(img, surya_boxes)

    assert len(candidates) <= _MAX_RECALL_BOXES_PER_PAGE
    assert booster.candidates_dropped >= 0

    for x0, y0, x1, y1 in candidates:
        assert 0.0 <= x0 <= 1.0, f"x0 out of bounds: {x0}"
        assert 0.0 <= y0 <= 1.0, f"y0 out of bounds: {y0}"
        assert 0.0 <= x1 <= 1.0, f"x1 out of bounds: {x1}"
        assert 0.0 <= y1 <= 1.0, f"y1 out of bounds: {y1}"
        assert x0 <= x1, f"x0 > x1: {x0} > {x1}"
        assert y0 <= y1, f"y0 > y1: {y0} > {y1}"

        # No candidate should overlap or straddle existing Surya boxes
        assert not _overlaps_surya((x0, y0, x1, y1), surya_boxes)
        assert not _straddles_surya((x0, y0, x1, y1), surya_boxes)


@settings(max_examples=100, deadline=None)
@given(
    width=st.integers(min_value=50, max_value=200),
    height=st.integers(min_value=50, max_value=200),
    surya_boxes=_surya_boxes_strat,
)
def test_disabled_booster_returns_empty(
    width: int, height: int, surya_boxes: list[BBox]
) -> None:
    """When booster is disabled, supplement always returns an empty list."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    booster = WhitespaceRecallBooster(options=WhitespaceRecallOptions(enabled=False))
    assert booster.enabled is False
    assert booster.supplement(img, surya_boxes) == []
