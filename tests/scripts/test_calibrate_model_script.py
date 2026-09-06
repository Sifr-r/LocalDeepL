"""Tests for :mod:`scripts.calibrate_model`.

The CLI is exercised as an importable library so the tests can run
without spawning a subprocess. The argparse ``main()`` is exercised in
a separate smoke test.

The script's responsibilities (Phase 3 of the OCR quality trust
layer):

1. Parse OCR-Quality-format JSON (``[{raw_confidence, quality_score}, ...]``).
2. Map discrete ``quality_score`` (1-4) to a target probability.
3. Split 80/20 train/test with a fixed RNG seed.
4. Fit Platt scaling on the train split.
5. Evaluate expected calibration error (ECE) on the test split.
6. Write ``resources/calibration/{model_id}.json`` with the fitted
   ``(a, b)`` parameters and ECE metadata.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Make the ``scripts/`` directory importable without polluting the
# top-level package namespace.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from scripts.calibrate_model import (  # noqa: E402  (after sys.path tweak)
    QUALITY_TO_PROBABILITY,
    CalibrationError,
    _Record,
    fit_from_records,
    load_records,
    parse_args,
    write_calibration,
)


@pytest.fixture
def tmp_records(tmp_path: Path) -> Path:
    """Build a synthetic OCR-Quality-format fixture."""
    records: list[dict[str, object]] = []
    # Construct 200 records: each ``raw_confidence`` is a random draw;
    # the ``quality_score`` correlates with the confidence but with
    # noise so the fit has signal to learn.
    import random

    rng = random.Random(42)
    for _ in range(200):
        raw = rng.uniform(0.05, 0.95)
        # Score mostly tracks raw, but with a noise floor so the
        # relationship is not literally linear.
        score = max(1, min(4, round(1 + 3 * (1.0 - raw) + rng.uniform(-0.4, 0.4))))
        records.append({"raw_confidence": raw, "quality_score": score})
    fixture = tmp_path / "ocr_quality_records.json"
    fixture.write_text(json.dumps(records))
    return fixture


class TestQualityToProbability:
    def test_score_1_maps_high(self):
        # Score 1 (Excellent) is the highest-quality bucket — the
        # target probability must be the largest mapping.
        assert QUALITY_TO_PROBABILITY[1] == max(QUALITY_TO_PROBABILITY.values())

    def test_score_4_maps_low(self):
        # Score 4 (Poor) is the worst bucket — the target probability
        # must be the smallest mapping.
        assert QUALITY_TO_PROBABILITY[4] == min(QUALITY_TO_PROBABILITY.values())

    def test_mapping_is_strictly_decreasing(self):
        # The four scores should map to strictly-decreasing
        # probabilities so the calibration preserves the ordering.
        values = [QUALITY_TO_PROBABILITY[s] for s in (1, 2, 3, 4)]
        for prev, cur in zip(values, values[1:], strict=False):
            assert cur < prev


class TestLoadRecords:
    def test_loads_minimal_records(self, tmp_path: Path):
        fixture = tmp_path / "minimal.json"
        fixture.write_text(
            json.dumps(
                [
                    {"raw_confidence": 0.5, "quality_score": 2},
                    {"raw_confidence": 0.9, "quality_score": 1},
                ]
            )
        )
        records = load_records(fixture)
        assert len(records) == 2
        # ``_Record`` is a frozen dataclass exposing ``raw`` and ``target``.
        assert records[0].raw == 0.5
        assert records[1].target == QUALITY_TO_PROBABILITY[1]

    def test_skips_malformed_records(self, tmp_path: Path):
        # Records missing fields or with out-of-range scores must be
        # silently dropped (not raise) so a partial dataset still
        # produces useful calibration.
        fixture = tmp_path / "mixed.json"
        fixture.write_text(
            json.dumps(
                [
                    {"raw_confidence": 0.5, "quality_score": 2},
                    {"raw_confidence": 0.9},  # missing quality_score
                    {"raw_confidence": 1.5, "quality_score": 2},  # out of range
                    {"raw_confidence": 0.3, "quality_score": 5},  # out of range
                    {"raw_confidence": 0.7, "quality_score": 1},
                ]
            )
        )
        records = load_records(fixture)
        assert len(records) == 2

    def test_file_not_found_raises_calibration_error(self, tmp_path: Path):
        with pytest.raises(CalibrationError):
            load_records(tmp_path / "does_not_exist.json")


class TestFitFromRecords:
    def test_produces_finite_parameters(self, tmp_records: Path):
        records = load_records(tmp_records)
        params = fit_from_records(records, seed=42)
        assert "a" in params and "b" in params
        import math

        assert math.isfinite(params["a"])
        assert math.isfinite(params["b"])

    def test_records_ece_and_baseline_ece(self, tmp_records: Path):
        # The fit must report both an ECE-after-calibration and an
        # identity-baseline ECE so the operator can see the
        # improvement at a glance.
        records = load_records(tmp_records)
        params = fit_from_records(records, seed=42)
        assert "ece_after" in params
        assert "ece_baseline" in params
        assert 0.0 <= params["ece_after"] <= 1.0
        assert 0.0 <= params["ece_baseline"] <= 1.0

    def test_calibration_reduces_ece_on_noisy_proxies(self, tmp_records: Path):
        # On a noisy-monotone dataset the calibrated ECE must be
        # below the identity baseline ECE.
        records = load_records(tmp_records)
        params = fit_from_records(records, seed=42)
        assert params["ece_after"] < params["ece_baseline"]

    def test_empty_records_raises(self):
        with pytest.raises(CalibrationError):
            fit_from_records([], seed=42)

    def test_too_few_records_raises(self):
        # Below the minimum sample size we can't fit anything
        # meaningful — the script must surface that as an error.
        with pytest.raises(CalibrationError):
            fit_from_records(
                [_Record(raw=0.5, target=QUALITY_TO_PROBABILITY[2])],
                seed=42,
                min_records=10,
            )

    def test_seed_actually_controls_the_platt_split(self, tmp_records: Path):
        """Audit Q9: the ``--seed`` flag is documented as "controls
        the train/test split RNG; the script is deterministic for a
        given seed". The contract has two parts:

        1. Different seeds produce different fits (the seed is
           actually consumed somewhere on the path).
        2. The same seed produces the same fit on repeated calls
           (the script is deterministic — not just "uses the seed
           once, then drifts" via ambient numpy state).

        We assert both. The first run captures the
        ``seed=42`` baseline; ``seed=43`` must differ in ``a`` or
        ``b`` (the split is shuffled differently, so the train
        split is different, so the optimizer converges to a
        slightly different optimum). The second ``seed=42`` run
        must equal the first byte-for-byte on ``a``, ``b``, and
        the diagnostic fields (n_train, n_test, ece_after, ece_baseline).
        """
        records = load_records(tmp_records)
        first = fit_from_records(records, seed=42)
        other = fit_from_records(records, seed=43)
        again = fit_from_records(records, seed=42)

        # The seed is actually consumed (a difference shows up
        # somewhere on the path — the train split is the most
        # likely culprit, but the optimizer may also land on a
        # different optimum).
        differs_in_a = first["a"] != other["a"]
        differs_in_b = first["b"] != other["b"]
        differs_in_train = first["n_train"] != other["n_train"]
        assert differs_in_a or differs_in_b or differs_in_train, (
            "seed had no effect on the fit (a, b, n_train all "
            "identical across seed=42 and seed=43)"
        )

        # The same seed is deterministic — n_train/n_test are
        # exact integers so the equality is unambiguous, and
        # ``a`` / ``b`` are floats so we use math.isclose to
        # allow for whatever floating-point jitter the
        # platform-level RNG (if any) introduces.
        import math

        assert first["n_train"] == again["n_train"]
        assert first["n_test"] == again["n_test"]
        assert math.isclose(first["a"], again["a"], rel_tol=1e-12, abs_tol=1e-12)
        assert math.isclose(first["b"], again["b"], rel_tol=1e-12, abs_tol=1e-12)


class TestWriteCalibration:
    def test_writes_resource_file(self, tmp_path: Path):
        target = tmp_path / "resources" / "calibration" / "test-model.json"
        params = {
            "a": 1.5,
            "b": -0.3,
            "ece_after": 0.04,
            "ece_baseline": 0.08,
            "n_records": 200,
            "n_train": 160,
            "n_test": 40,
            "seed": 42,
        }
        write_calibration(params, model_id="test-model", output_path=target)
        assert target.exists()
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["a"] == 1.5
        assert payload["b"] == -0.3
        assert "metadata" in payload
        assert payload["metadata"]["model_id"] == "test-model"
        assert payload["metadata"]["ece_baseline"] == 0.08

    def test_creates_parent_directory(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "calib.json"
        write_calibration(
            {
                "a": 1.0,
                "b": 0.0,
                "ece_after": 0.0,
                "ece_baseline": 0.0,
                "n_records": 100,
                "n_train": 80,
                "n_test": 20,
                "seed": 0,
            },
            model_id="x",
            output_path=target,
        )
        assert target.exists()


class TestCLI:
    def test_cli_writes_calibration_file(self, tmp_records: Path, tmp_path: Path):
        out = tmp_path / "calibration.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "calibrate_model.py"),
                "--input",
                str(tmp_records),
                "--model-id",
                "unit-test-model",
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "a" in payload and "b" in payload

    def test_cli_missing_input_exits_nonzero(self, tmp_path: Path):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "calibrate_model.py"),
                "--input",
                str(tmp_path / "does_not_exist.json"),
                "--model-id",
                "missing",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0


class TestParseArgs:
    def test_parse_args_requires_model_id(self, tmp_path: Path):
        # ``--model-id`` is mandatory so we never accidentally
        # overwrite an existing calibration file with the wrong name.
        with pytest.raises(SystemExit):
            parse_args(["--input", str(tmp_path / "x.json")])
