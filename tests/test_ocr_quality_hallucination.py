"""Tests for :mod:`omniscribe.core.ocr_quality.hallucination`."""

from __future__ import annotations

from omniscribe.core.ocr_quality import hallucination
from omniscribe.core.ocr_quality.types import HallucinationRisk


class TestCleanText:
    def test_empty(self):
        assert hallucination.evaluate("", None) is HallucinationRisk.NONE

    def test_whitespace_only(self):
        assert hallucination.evaluate("   \n\t  ", None) is HallucinationRisk.NONE

    def test_clean_sentence(self):
        risk = hallucination.evaluate(
            "This is a perfectly normal sentence with no issues.",
            (0.0, 0.0, 1.0, 0.05),
            page_size=(800, 1000),
        )
        assert risk is HallucinationRisk.NONE


class TestRepetition:
    def test_long_repetition_raises_to_medium_or_higher(self):
        text = "abcdab" * 20
        risk = hallucination.evaluate(text, None)
        assert risk in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}

    def test_short_repetition_below_window(self):
        text = "ababab"
        risk = hallucination.evaluate(text, None)
        assert risk is HallucinationRisk.NONE


class TestGiveupMarker:
    def test_known_marker(self):
        risk = hallucination.evaluate("foo \u25a2\u25a2\u25a2 bar", None)
        assert risk in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}

    def test_unreadable_marker(self):
        risk = hallucination.evaluate("Some text [unreadable] here", None)
        assert risk in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}


class TestLengthPlausibility:
    def test_one_char_huge_bbox(self):
        risk = hallucination.evaluate(
            "x",
            (0.0, 0.0, 1.0, 0.5),
            page_size=(1000, 1000),
            length_plausibility_min=0.0001,
        )
        assert risk in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}

    def test_reasonable_density(self):
        risk = hallucination.evaluate(
            "This is a sample paragraph with various words that look like "
            "normal OCR output. It contains enough characters to satisfy "
            "the length-vs-bbox density heuristic.",
            (0.0, 0.0, 0.5, 0.05),
            page_size=(1000, 1000),
        )
        assert risk is HallucinationRisk.NONE

    def test_off_origin_bbox_uses_width_height_not_origin_rectangle(self):
        # Audit P2-9 regression: the density check must measure
        # ``(x1-x0) * (y1-y0)``, not the rectangle from the page origin.
        # This box is 10% x 5% of the page but sits at (0.8, 0.8); the
        # old ``x1 * y1`` formula saw a 76%-of-page area and flagged it.
        risk = hallucination.evaluate(
            "Hello world, this is fine.",
            (0.8, 0.8, 0.9, 0.85),
            page_size=(1000, 1000),
        )
        assert risk is HallucinationRisk.NONE


class TestCrossCheck:
    def test_high_divergence_bumps_risk(self):
        def cross_fn(text, bbox):
            return "Z" * len(text)

        risk = hallucination.evaluate(
            "Hello world",
            (0.0, 0.0, 0.5, 0.05),
            cross_check=True,
            cross_check_fn=cross_fn,
        )
        assert risk in {
            HallucinationRisk.LOW,
            HallucinationRisk.MEDIUM,
            HallucinationRisk.HIGH,
        }

    def test_identical_cross_check_does_not_bump(self):
        def cross_fn(text, bbox):
            return text

        risk = hallucination.evaluate(
            "Hello world",
            (0.0, 0.0, 0.5, 0.05),
            cross_check=True,
            cross_check_fn=cross_fn,
        )
        assert risk is HallucinationRisk.NONE

    def test_cross_check_exception_returns_low(self):
        def cross_fn(text, bbox):
            raise RuntimeError("vlm timeout")

        risk = hallucination.evaluate(
            "Hello world",
            (0.0, 0.0, 0.5, 0.05),
            cross_check=True,
            cross_check_fn=cross_fn,
        )
        assert risk is HallucinationRisk.LOW

    def test_cross_check_disabled_ignores_fn(self):
        def cross_fn(text, bbox):
            raise RuntimeError("should not be called")

        risk = hallucination.evaluate(
            "Hello world",
            (0.0, 0.0, 0.5, 0.05),
            cross_check=False,
            cross_check_fn=cross_fn,
        )
        assert risk is HallucinationRisk.NONE


class TestEvaluateMany:
    def test_batch(self):
        items = [
            ("Hello", (0.0, 0.0, 0.5, 0.05)),
            ("", None),
            ("\u25a2\u25a2\u25a2", None),
        ]
        results = hallucination.evaluate_many(items, page_size=(800, 800))
        assert len(results) == 3
        assert results[0] is HallucinationRisk.NONE
        assert results[1] is HallucinationRisk.NONE
        assert results[2] in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}
