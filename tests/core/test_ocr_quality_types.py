"""Tests for :mod:`omniscribe.core.ocr_quality.types`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from omniscribe.core.ocr_quality.types import (
    BlockTrust,
    HallucinationRisk,
    ScriptHint,
    TrustFlag,
    WatermarkHit,
    hallucination_risk_value,
)


class TestTrustFlag:
    def test_is_string_enum(self):
        assert isinstance(TrustFlag.HALLUCINATION_RISK, str)
        assert TrustFlag.HALLUCINATION_RISK.value == "hallucination_risk"

    def test_all_expected_members(self):
        expected = {
            "HALLUCINATION_RISK",
            "WATERMARK_HIT",
            "SCRIPT_MISMATCH",
            "LOW_CALIBRATED_CONF",
            "LENGTH_PLAUSIBILITY",
        }
        assert {f.name for f in TrustFlag} == expected


class TestHallucinationRisk:
    def test_risk_values(self):
        # Spec §5.3 — NONE/LOW carry zero penalty by design.
        assert hallucination_risk_value(HallucinationRisk.NONE) == 0.0
        assert hallucination_risk_value(HallucinationRisk.LOW) == 0.0
        assert hallucination_risk_value(HallucinationRisk.MEDIUM) == 0.5
        assert hallucination_risk_value(HallucinationRisk.HIGH) == 1.0


class TestWatermarkHit:
    def test_frozen(self):
        hit = WatermarkHit(bbox=None, confidence=0.5)
        with pytest.raises(FrozenInstanceError):
            hit.confidence = 0.9  # type: ignore[misc]

    def test_passthrough_has_no_bbox(self):
        hit = WatermarkHit(bbox=None, confidence=0.0)
        assert hit.bbox is None

    def test_hit_has_normalized_bbox(self):
        hit = WatermarkHit(bbox=(0.1, 0.2, 0.5, 0.6), confidence=0.9)
        assert hit.bbox == (0.1, 0.2, 0.5, 0.6)
        assert hit.confidence == 0.9


class TestScriptHint:
    def test_default_no_bbox(self):
        hint = ScriptHint(script="Latin", confidence=0.8)
        assert hint.bbox is None
        assert hint.script == "Latin"

    def test_with_block_bbox(self):
        hint = ScriptHint(script="CJK", confidence=0.7, bbox=(0.0, 0.0, 0.5, 0.5))
        assert hint.bbox == (0.0, 0.0, 0.5, 0.5)


class TestBlockTrust:
    def test_construction(self):
        trust = BlockTrust(
            score=0.7,
            flags=(TrustFlag.WATERMARK_HIT,),
            explanations=("watermark overlaps this block",),
        )
        assert trust.score == 0.7
        assert trust.flags == (TrustFlag.WATERMARK_HIT,)
        assert trust.explanations == ("watermark overlaps this block",)

    def test_frozen(self):
        trust = BlockTrust(score=0.5, flags=(), explanations=())
        with pytest.raises(FrozenInstanceError):
            trust.score = 0.9  # type: ignore[misc]

    def test_empty_flags(self):
        trust = BlockTrust(score=1.0, flags=(), explanations=())
        assert trust.flags == ()
        assert trust.score == 1.0
