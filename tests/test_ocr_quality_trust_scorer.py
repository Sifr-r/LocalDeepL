"""Tests for :mod:`omniscribe.core.ocr_quality.trust_scorer`."""

from __future__ import annotations

import pytest

from omniscribe.core.ocr_quality import trust_scorer
from omniscribe.core.ocr_quality.types import HallucinationRisk, TrustFlag


class TestNoFlags:
    def test_clean_block_matches_confidence(self):
        t = trust_scorer.score(0.8)
        assert t.score == pytest.approx(0.8)
        assert TrustFlag.HALLUCINATION_RISK not in t.flags
        assert TrustFlag.WATERMARK_HIT not in t.flags
        assert TrustFlag.SCRIPT_MISMATCH not in t.flags

    def test_low_confidence_adds_low_calibrated_flag(self):
        t = trust_scorer.score(0.3)
        assert TrustFlag.LOW_CALIBRATED_CONF in t.flags


class TestHallucinationPenalty:
    def test_high_risk_halves_score(self):
        t = trust_scorer.score(0.8, hallucination=HallucinationRisk.HIGH)
        assert t.score == pytest.approx(0.4)
        assert TrustFlag.HALLUCINATION_RISK in t.flags

    def test_medium_risk_drops_score_by_25pct(self):
        t = trust_scorer.score(0.8, hallucination=HallucinationRisk.MEDIUM)
        # 0.8 * (1 - 0.5*0.5) = 0.8 * 0.75 = 0.6
        assert t.score == pytest.approx(0.6)

    def test_low_risk_zero_penalty(self):
        t = trust_scorer.score(0.8, hallucination=HallucinationRisk.LOW)
        assert t.score == pytest.approx(0.8)

    def test_none_risk_zero_penalty(self):
        t = trust_scorer.score(0.8, hallucination=HallucinationRisk.NONE)
        assert t.score == pytest.approx(0.8)


class TestWatermarkAndScript:
    def test_watermark_in_block(self):
        t = trust_scorer.score(0.8, watermark_in_block=True)
        # 0.8 * (1 - 0.3) = 0.56
        assert t.score == pytest.approx(0.56)
        assert TrustFlag.WATERMARK_HIT in t.flags

    def test_script_mismatch(self):
        t = trust_scorer.score(0.8, script_mismatch=True)
        # 0.8 * (1 - 0.2) = 0.64
        assert t.score == pytest.approx(0.64)
        assert TrustFlag.SCRIPT_MISMATCH in t.flags

    def test_all_flags_compound(self):
        t = trust_scorer.score(
            0.8,
            hallucination=HallucinationRisk.HIGH,
            watermark_in_block=True,
            script_mismatch=True,
        )
        # 0.8 * 0.5 * 0.7 * 0.8 = 0.224
        assert t.score == pytest.approx(0.224)
        assert TrustFlag.HALLUCINATION_RISK in t.flags
        assert TrustFlag.WATERMARK_HIT in t.flags
        assert TrustFlag.SCRIPT_MISMATCH in t.flags


class TestInvariants:
    def test_purity(self):
        a = trust_scorer.score(0.5, hallucination=HallucinationRisk.MEDIUM)
        b = trust_scorer.score(0.5, hallucination=HallucinationRisk.MEDIUM)
        assert a == b

    def test_score_clamped_to_unit_interval(self):
        # Very high hallucination + watermark + mismatch + low conf still in [0, 1].
        t = trust_scorer.score(
            1.0,
            hallucination=HallucinationRisk.HIGH,
            watermark_in_block=True,
            script_mismatch=True,
        )
        assert 0.0 <= t.score <= 1.0

    def test_monotonic_in_confidence(self):
        low = trust_scorer.score(0.2)
        mid = trust_scorer.score(0.5)
        high = trust_scorer.score(0.8)
        assert low.score < mid.score < high.score

    def test_flags_dedup(self):
        t = trust_scorer.score(0.3)  # below 0.5 → LOW_CALIBRATED_CONF
        # LOW_CALIBRATED_CONF must appear exactly once.
        assert list(t.flags).count(TrustFlag.LOW_CALIBRATED_CONF) == 1
