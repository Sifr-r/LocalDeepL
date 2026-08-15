"""Unit tests for the whitespace recall booster (core/text_recall.py)."""

from __future__ import annotations

import sys

import pytest
from PIL import Image, ImageDraw

from omniscribe.core.text_recall import (
    WhitespaceRecallBooster,
    WhitespaceRecallOptions,
    _overlaps_surya,
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


def test_disabled_options_return_no_boxes() -> None:
    img = _line_page()
    booster = WhitespaceRecallBooster(WhitespaceRecallOptions(enabled=False))
    assert booster.supplement(img, []) == []


def test_missing_cv2_is_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    # sys.modules["cv2"] = None makes `import cv2` raise ImportError.
    monkeypatch.setitem(sys.modules, "cv2", None)
    img = _line_page()
    assert WhitespaceRecallBooster().supplement(img, []) == []


class TestWhitespaceRecallOptionsFromEnv:
    def test_default_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_WHITESPACE_RECALL", raising=False)
        assert WhitespaceRecallOptions.from_env().enabled is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", " Off "])
    def test_disable_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", value)
        assert WhitespaceRecallOptions.from_env().enabled is False

    def test_unrecognized_value_stays_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", "banana")
        assert WhitespaceRecallOptions.from_env().enabled is True
