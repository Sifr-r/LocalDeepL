"""Pure-numpy Platt scaling fit for the OCR quality trust layer.

Given ``(raw_confidence, target_probability)`` pairs, fits a 2-parameter
logistic ``sigmoid(a * raw + b)`` so the calibrated output matches the
target probability. Used by ``scripts/calibrate_model.py`` to produce
the per-model JSON calibration files that
:mod:`omniscribe.core.ocr_quality.calibration` consumes at OCR time.

The fit is intentionally dependency-free — ``numpy`` is the only
runtime dependency, and the optimiser is bounded gradient descent with
backtracking line-search. That is enough for our scale (≤ a few
thousand labelled pages per model) and avoids pulling ``scipy`` /
``sklearn`` into the trust-layer's runtime surface.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def sigmoid(z: float) -> float:
    """Numerically stable logistic sigmoid.

    Mirrors the implementation in :mod:`calibration` so the fitter and
    the runtime agree to floating-point precision on shared inputs.
    """
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass(frozen=True)
class CalibrationFitResult:
    """Result of a Platt scaling fit.

    Returned by :func:`fit_platt` when ``return_result=True``. The
    tuple form ``(a, b)`` is the default — callers that only need the
    parameters do not pay for the diagnostic fields.
    """

    a: float
    b: float
    iterations: int
    final_loss: float


def fit_platt(
    raw: Sequence[float],
    targets: Sequence[float],
    *,
    max_iter: int = 200,
    learning_rate: float = 0.1,
    tol: float = 1e-7,
    return_result: bool = False,
) -> tuple[float, float] | CalibrationFitResult:
    """Fit ``sigmoid(a * raw + b)`` to ``(raw, targets)``.

    Minimises binary cross-entropy

        L(a, b) = -mean( target * log(p) + (1 - target) * log(1 - p) )

    where ``p = sigmoid(a * raw + b)``. The default optimiser is bounded
    gradient descent with backtracking line-search; it terminates when
    the loss stops improving by ``tol`` or after ``max_iter`` steps,
    whichever comes first.

    Parameters
    ----------
    raw:
        Raw VLM confidences in ``[0, 1]``.
    targets:
        Target probabilities in ``[0, 1]`` (typically derived from a
        discrete quality score via :func:`scripts.calibrate_model`).
    max_iter:
        Hard upper bound on iterations.
    learning_rate:
        Initial step size; the line-search shrinks it on demand.
    tol:
        Early-stop when the absolute loss change between iterations is
        below this threshold.
    return_result:
        When ``True``, return a :class:`CalibrationFitResult` carrying
        the iteration count and final loss; otherwise return the plain
        ``(a, b)`` tuple.

    Returns
    -------
    tuple[float, float] | CalibrationFitResult
        Fitted parameters ``(a, b)``. Always finite — degenerate inputs
        return the identity-initialisation ``(1.0, 0.0)``.
    """
    a, b = 1.0, 0.0
    identity = CalibrationFitResult(a=1.0, b=0.0, iterations=0, final_loss=0.0)
    if return_result:
        identity_return: tuple[float, float] | CalibrationFitResult = identity
    else:
        identity_return = (1.0, 0.0)

    if len(raw) == 0 or len(targets) == 0:
        return identity_return
    if len(raw) != len(targets):
        raise ValueError(
            f"fit_platt: raw and targets must have the same length "
            f"(got {len(raw)} vs {len(targets)})"
        )

    raw_arr = np.asarray(raw, dtype=np.float64)
    tgt_arr = np.asarray(targets, dtype=np.float64)
    # Clamp to ``[eps, 1 - eps]`` so log() stays finite at the extremes.
    eps = 1e-6
    tgt_arr = np.clip(tgt_arr, eps, 1.0 - eps)

    def _loss(a_cur: float, b_cur: float) -> float:
        z = a_cur * raw_arr + b_cur
        p = _sigmoid_array(z)
        return float(-np.mean(tgt_arr * np.log(p) + (1 - tgt_arr) * np.log(1 - p)))

    def _grad(a_cur: float, b_cur: float) -> tuple[float, float]:
        z = a_cur * raw_arr + b_cur
        p = _sigmoid_array(z)
        diff = p - tgt_arr
        return float(np.mean(diff * raw_arr)), float(np.mean(diff))

    last_loss = _loss(a, b)
    iters = 0
    step = learning_rate
    for iters in range(1, max_iter + 1):
        grad_a, grad_b = _grad(a, b)
        # Backtracking line-search. Halve the step until the loss
        # actually improves; bound at 256 halvings so we don't loop
        # forever when the gradient is already zero.
        cand_a = a - step * grad_a
        cand_b = b - step * grad_b
        shrink = 0
        while shrink < 256:
            cand_loss = _loss(cand_a, cand_b)
            if cand_loss < last_loss - tol:
                break
            step *= 0.5
            cand_a = a - step * grad_a
            cand_b = b - step * grad_b
            shrink += 1
        if shrink >= 256:
            # No improvement possible at this gradient — stop.
            break
        a, b = cand_a, cand_b
        # ``cand_loss < last_loss - tol`` is the loop's exit predicate;
        # recompute the last loss to track early stopping.
        last_loss = _loss(a, b)
        if not math.isfinite(a) or not math.isfinite(b):
            # Defensive — the line-search should prevent this, but a
            # pathological dataset could still produce NaN. Fall back
            # to identity rather than crashing.
            a, b = 1.0, 0.0
            last_loss = _loss(a, b)
            iters += 1
            break

    if return_result:
        return CalibrationFitResult(
            a=float(a), b=float(b), iterations=iters, final_loss=last_loss
        )
    return float(a), float(b)


def _sigmoid_array(z: np.ndarray) -> np.ndarray:
    """Vectorised numerically-stable sigmoid."""
    pos = z >= 0
    out = np.empty_like(z, dtype=np.float64)
    # Positive branch: ``1 / (1 + exp(-z))``
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    # Negative branch: ``exp(z) / (1 + exp(z))`` — both terms share
    # ``exp(z)`` so we only evaluate it once.
    neg = ~pos
    ez = np.exp(z[neg])
    out[neg] = ez / (1.0 + ez)
    return out


__all__ = ["CalibrationFitResult", "fit_platt", "sigmoid"]
