"""Tests for :mod:`omniscribe.core.ocr_quality.calibration`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniscribe.core.ocr_quality import calibration


@pytest.fixture(autouse=True)
def _clear_cache():
    calibration.reset_cache()
    yield
    calibration.reset_cache()


class TestIdentity:
    def test_unknown_model_id_identity(self):
        # No calibration file for "unknown-model-xyz".
        out = calibration.calibrate(0.7, "unknown-model-xyz")
        assert 0.0 <= out <= 1.0
        # Identity is approximately the identity function.
        assert abs(out - 0.7) < 0.05

    def test_identity_file_midpoint(self):
        out = calibration.calibrate(0.5, "identity")
        # sigmoid(1*0.5 + 0) == 0.5 — identity calibration at midpoint.
        assert abs(out - 0.5) < 0.01

    def test_identity_file_endpoints(self):
        assert calibration.calibrate(0.0, "identity") < 0.05
        assert calibration.calibrate(1.0, "identity") > 0.95


class TestLinearScaling:
    def test_a2_monotonic_positive(self, tmp_path: Path, monkeypatch):
        # Replace the identity file with a steeper curve and re-use its slot.
        from omniscribe.core.ocr_quality import calibration as cal

        monkeypatch.setattr(cal, "_CALIBRATION_DIR", tmp_path)
        (tmp_path / "qwen_steep.json").write_text(json.dumps({"a": 2.0, "b": 0.0}))
        cal.reset_cache()
        # raw=0.5 → sigmoid(1.0) ≈ 0.731 > 0.5 (monotonic, scales upward).
        out = calibration.calibrate(0.5, "qwen_steep")
        assert out > 0.5

    def test_clamping(self, monkeypatch):
        from omniscribe.core.ocr_quality import calibration as cal

        monkeypatch.setattr(cal, "_CALIBRATION_DIR", Path("/nonexistent"))
        cal.reset_cache()
        out = calibration.calibrate(2.5, "absent-model")
        # Inputs outside [0, 1] are clamped first → identity output.
        assert out == 1.0


class TestCache:
    def test_repeated_calls_use_cache(self, monkeypatch, tmp_path: Path):
        from omniscribe.core.ocr_quality import calibration as cal

        target = tmp_path / "model.json"
        target.write_text(json.dumps({"a": 3.0, "b": -1.0}))
        monkeypatch.setattr(cal, "_CALIBRATION_DIR", tmp_path)
        cal.reset_cache()
        first = calibration.calibrate(0.5, "model")
        # Mutate the file; the cached params must still be used.
        target.write_text(json.dumps({"a": 99.0, "b": 99.0}))
        second = calibration.calibrate(0.5, "model")
        assert first == second
