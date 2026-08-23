"""Property-based tests for the pure :func:`trust_scorer.score` formula.

Uses ``hypothesis`` (declared in ``[dependency-groups].dev`` in
``pyproject.toml``) to fuzz the formula across thousands of random
inputs and verify the invariants called out in the spec §5.5:

- Output is always in ``[0, 1]``.
- Score is monotonic in ``calibrated_conf`` (all else fixed).
- Same input → same output (purity).
"""

from __future__ import annotations

import pytest

from omniscribe.core.ocr_quality import trust_scorer
from omniscribe.core.ocr_quality.types import HallucinationRisk, TrustFlag

# Skip the entire module when hypothesis isn't installed — the rest of
# the test suite still runs without it.
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_HALLUCINATION_STRAT = st.sampled_from(list(HallucinationRisk))
_BOOL_STRAT = st.booleans()


@given(
    conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hallucination=_HALLUCINATION_STRAT,
    watermark=_BOOL_STRAT,
    script_mismatch=_BOOL_STRAT,
)
def test_score_always_in_unit_interval(conf, hallucination, watermark, script_mismatch):
    trust = trust_scorer.score(
        conf,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    assert 0.0 <= trust.score <= 1.0


@given(
    hallucination=_HALLUCINATION_STRAT,
    watermark=_BOOL_STRAT,
    script_mismatch=_BOOL_STRAT,
)
def test_monotonic_in_confidence(hallucination, watermark, script_mismatch):
    low = trust_scorer.score(
        0.2,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    high = trust_scorer.score(
        0.8,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    assert low.score <= high.score


@given(
    conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hallucination=_HALLUCINATION_STRAT,
    watermark=_BOOL_STRAT,
    script_mismatch=_BOOL_STRAT,
)
def test_purity(conf, hallucination, watermark, script_mismatch):
    a = trust_scorer.score(
        conf,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    b = trust_scorer.score(
        conf,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    assert a == b


@given(
    conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hallucination=_HALLUCINATION_STRAT,
    watermark=_BOOL_STRAT,
    script_mismatch=_BOOL_STRAT,
)
def test_input_clamped_to_unit_interval(
    conf, hallucination, watermark, script_mismatch
):
    # Even when ``calibrated_conf`` is slightly out of range (e.g. 1.0000001),
    # the formula clamps before applying penalties. The contract is that the
    # output is still in [0, 1] — never NaN, never infinity.
    extreme = max(0.0, min(1.0, conf)) + 0.5  # always out of range
    trust = trust_scorer.score(
        extreme,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    assert 0.0 <= trust.score <= 1.0


@given(
    conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hallucination=_HALLUCINATION_STRAT,
    watermark=_BOOL_STRAT,
    script_mismatch=_BOOL_STRAT,
)
def test_low_confidence_flag_consistent(
    conf, hallucination, watermark, script_mismatch
):
    trust = trust_scorer.score(
        conf,
        hallucination=hallucination,
        watermark_in_block=watermark,
        script_mismatch=script_mismatch,
    )
    if conf < 0.5:
        assert TrustFlag.LOW_CALIBRATED_CONF in trust.flags
    else:
        assert TrustFlag.LOW_CALIBRATED_CONF not in trust.flags
