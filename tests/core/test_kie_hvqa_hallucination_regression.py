"""Dataset-driven regression test for the OCR quality hallucination guard.

Marked ``slow_dataset`` so the fast ``pytest`` tier skips it by default
— only the nightly workflow (which downloads the full KIE-HVQA
dataset) runs it.

Acceptance criterion (from the design §16 item 5):

    Hallucination guard achieves ≥80% per-region agreement with
    KIE-HVQA per-region reliability annotations.

The KIE-HVQA dataset (arXiv:2506.20168) provides pixel-level
reliability annotations: for each character in the OCR output, a
binary flag indicating whether it is visible in the source image or
hallucinated by the VLM. We compare our
:func:`omniscribe.core.ocr_quality.hallucination.evaluate` function
against these annotations:

- A block whose KIE-HVQA reliability is <50% (mostly hallucinated)
  should be classified as ``MEDIUM`` or ``HIGH`` hallucination risk
  by our guard.
- A block whose KIE-HVQA reliability is ≥50% (mostly visible) should
  be classified as ``NONE`` or ``LOW`` risk.

Per-region agreement is the fraction of regions where the two
classifications agree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

# ``omniscribe.core.ocr_quality.hallucination`` exposes the per-block
# evaluator. We map ``HIGH``/``MEDIUM`` → "hallucinated" and
# ``NONE``/``LOW`` → "visible" to compare against the KIE-HVQA
# annotations.
from omniscribe.core.ocr_quality.hallucination import evaluate
from omniscribe.core.ocr_quality.types import HallucinationRisk

DATASETS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "datasets"
MINI_FIXTURE = DATASETS_DIR / "kie_hvqa_mini.json"
FULL_FIXTURE = DATASETS_DIR / "kie_hvqa_full.json"

# Acceptance: ≥80% per-region agreement (design §16 item 5).
MIN_AGREEMENT = 0.80


pytestmark = pytest.mark.slow_dataset


def _records_or_skip(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        pytest.skip(f"dataset not present: {path} (run scripts/fetch_datasets.py)")
    return cast(list[dict[str, Any]], json.loads(path.read_text(encoding="utf-8")))


def _is_hallucinated(risk: HallucinationRisk) -> bool:
    """Map our 4-level risk to a binary hallucinated/visible label."""
    return risk in (HallucinationRisk.MEDIUM, HallucinationRisk.HIGH)


def _is_kie_hallucinated(record: dict[str, Any]) -> bool:
    """KIE-HVQA label: a region is hallucinated if its reliability is <0.5.

    The mini fixture encodes ``reliability`` as a list of 1s and 0s
    (per-character visible/hallucinated flags from the dataset).
    """
    reliability = record.get("reliability", [])
    if not reliability:
        # Empty reliability means "no annotation" — treat as visible.
        return False
    visible_fraction = sum(cast(list[float], reliability)) / len(reliability)
    return visible_fraction < 0.5


def _evaluate_block(record: dict[str, Any]) -> HallucinationRisk:
    """Run our heuristic evaluator on a KIE-HVQA-format block."""
    bbox = record.get("bbox")
    bbox_tuple = tuple(bbox) if bbox and len(bbox) == 4 else None
    return evaluate(record.get("text", ""), bbox_tuple)


class TestMiniFixtureSmoke:
    """The checked-in mini fixture must always pass the agreement test."""

    def test_mini_fixture_meets_agreement_threshold(self):
        records = _records_or_skip(MINI_FIXTURE)
        agreements = 0
        total = 0
        for record in records:
            if not record.get("text"):
                # Skip empty-text records (no reliable annotation).
                continue
            risk = _evaluate_block(record)
            predicted = _is_hallucinated(risk)
            actual = _is_kie_hallucinated(record)
            if predicted == actual:
                agreements += 1
            total += 1
        assert total > 0
        # On the mini fixture we only require that agreement is at
        # least ``MIN_AGREEMENT`` — the dataset is hand-curated to
        # exercise the heuristic signals.
        assert agreements / total >= MIN_AGREEMENT


class TestFullFixtureRegression:
    """Real KIE-HVQA fixture must clear the 80% agreement threshold."""

    def test_full_fixture_meets_agreement_threshold(self):
        records = _records_or_skip(FULL_FIXTURE)
        agreements = 0
        total = 0
        for record in records:
            if not record.get("text"):
                continue
            risk = _evaluate_block(record)
            predicted = _is_hallucinated(risk)
            actual = _is_kie_hallucinated(record)
            if predicted == actual:
                agreements += 1
            total += 1
        assert total > 0
        agreement_fraction = agreements / total
        assert agreement_fraction >= MIN_AGREEMENT, (
            f"per-region agreement {agreement_fraction:.2%} is below "
            f"{MIN_AGREEMENT:.0%} threshold"
        )


class TestFixturesAreValidJSON:
    """The mini fixture must parse as a JSON array of records."""

    def test_mini_fixture_is_json(self):
        data = json.loads(MINI_FIXTURE.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "text" in item
            assert "bbox" in item
            assert "reliability" in item
