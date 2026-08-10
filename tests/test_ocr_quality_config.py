"""Tests for :class:`omniscribe.core.ocr_quality.config.OCrQualitySettings`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from omniscribe.core.ocr_quality.config import OCrQualitySettings


class TestDefaults:
    def test_phase1_all_submodules_off(self):
        s = OCrQualitySettings()
        assert s.watermark_enabled is False
        assert s.script_detect_enabled is False
        assert s.hallucination_enabled is False
        assert s.hallucination_cross_check is False
        assert s.calibration_enabled is False

    def test_rollout_flags_default_false(self):
        s = OCrQualitySettings()
        assert s.phase2_default is False
        assert s.phase3_default is False

    def test_threshold_defaults(self):
        s = OCrQualitySettings()
        assert s.watermark_aggressiveness == 0.5
        assert s.trust_flag_threshold == 0.5
        assert s.hallucination_cross_check_threshold == 0.4
        assert s.hallucination_repetition_window == 6


class TestToggles:
    def test_toggling_each_flag_persists(self):
        s = OCrQualitySettings(
            watermark_enabled=True,
            script_detect_enabled=True,
            hallucination_enabled=True,
            calibration_enabled=True,
        )
        assert s.watermark_enabled is True
        assert s.script_detect_enabled is True
        assert s.hallucination_enabled is True
        assert s.calibration_enabled is True

    def test_cross_check_independent_of_hallucination(self):
        s = OCrQualitySettings(hallucination_cross_check=True)
        assert s.hallucination_enabled is False
        assert s.hallucination_cross_check is True


class TestValidation:
    def test_rejects_extra_field(self):
        with pytest.raises(ValidationError):
            OCrQualitySettings(unknown_field=True)  # type: ignore[call-arg]

    def test_aggressiveness_out_of_range_low(self):
        with pytest.raises(ValidationError):
            OCrQualitySettings(watermark_aggressiveness=-0.1)

    def test_aggressiveness_out_of_range_high(self):
        with pytest.raises(ValidationError):
            OCrQualitySettings(watermark_aggressiveness=1.1)

    def test_threshold_out_of_range_high(self):
        with pytest.raises(ValidationError):
            OCrQualitySettings(trust_flag_threshold=2.0)

    def test_repetition_window_too_small(self):
        with pytest.raises(ValidationError):
            OCrQualitySettings(hallucination_repetition_window=1)


class TestAnySubmoduleEnabled:
    def test_default_returns_false(self):
        assert OCrQualitySettings().any_submodule_enabled() is False

    def test_watermark_only_returns_true(self):
        assert (
            OCrQualitySettings(watermark_enabled=True).any_submodule_enabled()
            is True
        )

    def test_calibration_only_returns_true(self):
        assert (
            OCrQualitySettings(calibration_enabled=True).any_submodule_enabled()
            is True
        )

    def test_cross_check_alone_returns_false(self):
        # cross_check=True requires hallucination_enabled to do anything;
        # the orchestrator guards that separately.
        assert (
            OCrQualitySettings(hallucination_cross_check=True).any_submodule_enabled()
            is False
        )
