"""Pure trust-scoring formula.

Single function, no I/O, no logging. Lives apart from the orchestrator
so it can be unit-tested with property-based testing and reused by
Web UI previews / evaluation scripts.

Formula (spec §5.5)::

    trust = conf
          * (1 - 0.5 * hallucination_value)
          * (1 - 0.3 * watermark_in_block)
          * (1 - 0.2 * script_mismatch)

Result is clamped to ``[0, 1]``. Same input → same output (pure).
"""

from __future__ import annotations

from .types import BlockTrust, HallucinationRisk, TrustFlag, hallucination_risk_value

# Penalty weights — exported so tests can verify they match the spec.
_WATERMARK_PENALTY = 0.3
_SCRIPT_PENALTY = 0.2
_HALLUCINATION_SCALE = 0.5


def score(
    calibrated_conf: float,
    *,
    hallucination: HallucinationRisk = HallucinationRisk.NONE,
    watermark_in_block: bool = False,
    script_mismatch: bool = False,
) -> BlockTrust:
    """Return a :class:`BlockTrust` for the given signals.

    Parameters
    ----------
    calibrated_conf:
        VLM confidence in ``[0, 1]`` after Platt calibration. Inputs
        outside the range are clamped.
    hallucination:
        Heuristic / cross-check verdict.
    watermark_in_block:
        True when a watermark hit overlaps the block's bbox.
    script_mismatch:
        True when the block's detected script differs from the page's
        dominant script.
    """
    conf = max(0.0, min(1.0, calibrated_conf))
    flags: list[TrustFlag] = []
    explanations: list[str] = []

    h_value = hallucination_risk_value(hallucination)
    if h_value > 0:
        flags.append(TrustFlag.HALLUCINATION_RISK)
        explanations.append(
            f"hallucination risk={hallucination.value} (penalty={_HALLUCINATION_SCALE * h_value:.2f})"
        )

    if watermark_in_block:
        flags.append(TrustFlag.WATERMARK_HIT)
        explanations.append(
            f"watermark overlaps block (penalty={_WATERMARK_PENALTY:.2f})"
        )

    if script_mismatch:
        flags.append(TrustFlag.SCRIPT_MISMATCH)
        explanations.append(
            f"script differs from page dominant (penalty={_SCRIPT_PENALTY:.2f})"
        )

    trust = conf * (1.0 - _HALLUCINATION_SCALE * h_value)
    if watermark_in_block:
        trust *= 1.0 - _WATERMARK_PENALTY
    if script_mismatch:
        trust *= 1.0 - _SCRIPT_PENALTY
    trust = max(0.0, min(1.0, trust))

    if conf < 0.5 and TrustFlag.LOW_CALIBRATED_CONF not in flags:
        flags.append(TrustFlag.LOW_CALIBRATED_CONF)
        explanations.append(f"calibrated confidence {conf:.2f} below 0.5")

    # Deduplicate while preserving order for stable JSON / UI rendering.
    seen: set[TrustFlag] = set()
    ordered_flags: list[TrustFlag] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            ordered_flags.append(flag)

    return BlockTrust(
        score=trust,
        flags=tuple(ordered_flags),
        explanations=tuple(explanations),
    )


__all__ = ["score"]
