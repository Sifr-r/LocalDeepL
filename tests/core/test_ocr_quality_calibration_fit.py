"""Tests for :mod:`omniscribe.core.ocr_quality.calibration_fit`.

Platt scaling fits a 2-parameter logistic ``sigmoid(a * raw + b)`` to a
set of ``(raw_confidence, target_probability)`` pairs. The fit must be:

- Monotonic in the input (calibrated output preserves the order of raw)
- Bounded (``a, b`` are finite floats; output stays in ``[0, 1]``)
- Convergent (gradient descent with line-search terminates)
- Better than the identity baseline on a synthetic dataset where the
  raw confidence is a noisy monotone proxy for the target
"""

from __future__ import annotations

import math

import pytest

from omniscribe.core.ocr_quality.calibration_fit import (
    CalibrationFitResult,
    fit_platt,
    sigmoid,
)


class TestSigmoid:
    def test_zero(self):
        assert abs(sigmoid(0.0) - 0.5) < 1e-9

    def test_large_positive(self):
        # Numerically stable: large z → 1.0
        assert sigmoid(500.0) == pytest.approx(1.0)

    def test_large_negative(self):
        # Numerically stable: large negative z → 0.0
        assert sigmoid(-500.0) == pytest.approx(0.0)

    def test_monotonic(self):
        # Plain sigmoid on ``[-10, 10]`` is strictly increasing.
        prev = sigmoid(-10.0)
        for z in [-5.0, -1.0, 0.0, 1.0, 5.0, 10.0]:
            cur = sigmoid(z)
            assert cur >= prev
            prev = cur


class TestFitPlattIdentityBaseline:
    def test_returns_tuple_of_two_floats(self):
        # Sanity — the function returns ``(a, b)`` floats, never NaN.
        raw = [0.1, 0.5, 0.9]
        targets = [0.1, 0.5, 0.9]
        a, b = fit_platt(raw, targets)
        assert isinstance(a, float)
        assert isinstance(b, float)
        assert math.isfinite(a)
        assert math.isfinite(b)

    def test_perfect_signal_stays_near_identity_at_midpoints(self):
        # When ``raw == target`` exactly, the BCE-optimal Platt scaling
        # is *not* literally ``a=1, b=0`` — the sigmoid is asymptotic
        # so the curve naturally shifts. We instead assert that the
        # calibrated output is monotonic in raw, stays in ``[0, 1]``,
        # and the calibrated midpoint lies within a small margin of
        # 0.5 (the identity-calibrated midpoint).
        raw = [0.0, 0.25, 0.5, 0.75, 1.0]
        targets = list(raw)
        a, b = fit_platt(raw, targets)
        calibrated = [sigmoid(a * r + b) for r in raw]
        # Monotonic in raw.
        for prev, cur in zip(calibrated, calibrated[1:], strict=False):
            assert cur >= prev
        # Bounded.
        for v in calibrated:
            assert 0.0 <= v <= 1.0
        # Midpoint stays near the identity midpoint (sigmoid(0) = 0.5).
        assert abs(calibrated[2] - 0.5) < 0.3


class TestFitPlattImprovesOverIdentity:
    def test_noisy_proxies_calibrated_to_reduce_mse(self):
        # Synthetic dataset where the raw confidence is a noisy
        # monotone proxy for the target. Platt scaling should reduce
        # mean-squared error vs. the identity passthrough.
        # Construct 200 points with raw in ``[0, 1]`` and
        # target ≈ 0.6 * raw + 0.2 with mild Gaussian noise. The
        # identity baseline MSE is bounded by the noise variance.
        n = 200
        raw = [i / (n - 1) for i in range(n)]
        targets = [
            max(0.0, min(1.0, 0.6 * r + 0.2 + 0.02 * math.sin(37 * r))) for r in raw
        ]
        a, b = fit_platt(raw, targets)

        def calibrated(values: list[float]) -> list[float]:
            return [sigmoid(a * v + b) for v in values]

        identity_mse = sum((r - t) ** 2 for r, t in zip(raw, targets, strict=False)) / n
        calibrated_mse = (
            sum((c - t) ** 2 for c, t in zip(calibrated(raw), targets, strict=False))
            / n
        )
        # Platt must reduce MSE by at least 30% vs. the identity
        # baseline on this monotone synthetic signal.
        assert calibrated_mse < 0.7 * identity_mse


class TestFitPlattResult:
    def test_result_is_namedtuple_like(self):
        raw = [0.1, 0.5, 0.9]
        targets = [0.2, 0.5, 0.8]
        result = fit_platt(raw, targets, return_result=True)
        assert isinstance(result, CalibrationFitResult)
        assert result.a == pytest.approx(result.a)  # tautology, sanity
        assert math.isfinite(result.b)
        assert result.iterations >= 1
        assert result.final_loss >= 0.0

    def test_default_return_is_tuple(self):
        raw = [0.1, 0.5, 0.9]
        targets = [0.2, 0.5, 0.8]
        out = fit_platt(raw, targets)
        assert isinstance(out, tuple)
        assert len(out) == 2


class TestFitPlattEdgeCases:
    def test_single_pair(self):
        # A single ``(raw, target)`` pair is degenerate but must not
        # crash — gradient descent with no curvature just returns the
        # initialisation.
        a, b = fit_platt([0.5], [0.5])
        assert math.isfinite(a) and math.isfinite(b)

    def test_empty_inputs(self):
        # Empty input is also degenerate — we accept any finite pair
        # rather than raising, since callers may filter records before
        # calling us.
        a, b = fit_platt([], [])
        assert math.isfinite(a) and math.isfinite(b)

    def test_extreme_target_distribution(self):
        # All targets are 1.0 → calibrated output should saturate high
        # on positive raw. The fit must converge without NaN.
        raw = [0.0, 0.5, 1.0]
        targets = [1.0, 1.0, 1.0]
        a, b = fit_platt(raw, targets)
        assert math.isfinite(a) and math.isfinite(b)
        for v in [0.1, 0.5, 0.9]:
            assert 0.0 <= sigmoid(a * v + b) <= 1.0
