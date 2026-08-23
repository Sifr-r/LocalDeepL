"""
Phase 2 — backend trust summary exposed via ``X-Document-Trust`` response header.

The frontend TrustPanel (Phase 2.18b) reads this header and renders a
read-only distribution histogram + flagged-block count. The header is
emitted only when at least one block carries a ``trust_score``; otherwise
it is omitted entirely (so the panel stays hidden when the trust layer
is off — matching the ``extra="forbid"`` / no-orchestrator default).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from omniscribe.api.services.ocr.response import (
    _document_trust_summary,
    _trust_header_from_pipeline,
)
from omniscribe.core.document import DocumentBlock, DocumentPage, DocumentResult


def _pipeline_with_blocks(blocks: list[DocumentBlock]) -> object:
    """Build a minimal pipeline-shaped object exposing ``last_document_result``."""
    document = DocumentResult(
        source_path="dummy",
        pages=[DocumentPage(page_index=0, blocks=blocks)],
    )

    class _StubPipeline:
        last_document_result = document

    return _StubPipeline()


def test_summary_is_none_when_no_blocks_have_trust_score():
    pipeline = _pipeline_with_blocks(
        [
            DocumentBlock(bbox=[0, 0, 1, 1], text="hello"),
            DocumentBlock(bbox=[0, 0, 1, 1], text="world"),
        ]
    )
    assert _document_trust_summary(pipeline) is None
    assert _trust_header_from_pipeline(pipeline) is None


def test_summary_aggregates_trust_score_distribution_and_flag_counts():
    pipeline = _pipeline_with_blocks(
        [
            DocumentBlock(
                bbox=[0, 0, 1, 1], text="ok", trust_score=0.95, trust_flags=()
            ),
            DocumentBlock(
                bbox=[0, 0, 1, 1], text="ok", trust_score=0.85, trust_flags=()
            ),
            DocumentBlock(
                bbox=[0, 0, 1, 1],
                text="suspect",
                trust_score=0.55,
                trust_flags=("HALLUCINATION_RISK",),
            ),
            DocumentBlock(
                bbox=[0, 0, 1, 1],
                text="watermarked",
                trust_score=0.15,
                trust_flags=("HALLUCINATION_RISK", "WATERMARK_HIT"),
            ),
        ]
    )
    summary = _document_trust_summary(pipeline)
    assert summary is not None
    assert summary["block_count"] == 4
    assert summary["scored_count"] == 4
    assert summary["flagged_count"] == 2  # the two with non-empty flags
    assert 0.6 < summary["average"] < 0.7  # (0.95 + 0.85 + 0.55 + 0.15) / 4 ≈ 0.625
    histogram = summary["histogram"]
    assert histogram["0.0-0.2"] == 1
    assert histogram["0.4-0.6"] == 1
    assert histogram["0.8-1"] == 2
    assert summary["flag_counts"]["HALLUCINATION_RISK"] == 2
    assert summary["flag_counts"]["WATERMARK_HIT"] == 1


def test_header_is_compact_json_and_round_trips():
    pipeline = _pipeline_with_blocks(
        [
            DocumentBlock(
                bbox=[0, 0, 1, 1],
                text="x",
                trust_score=0.42,
                trust_flags=("SCRIPT_MISMATCH",),
            )
        ]
    )
    header = _trust_header_from_pipeline(pipeline)
    assert header is not None
    decoded = json.loads(header)
    assert decoded["scored_count"] == 1
    assert decoded["flagged_count"] == 1
    assert decoded["flag_counts"]["SCRIPT_MISMATCH"] == 1


def test_summary_skips_blocks_with_none_trust_score_but_counts_them_in_total():
    pipeline = _pipeline_with_blocks(
        [
            DocumentBlock(bbox=[0, 0, 1, 1], text="a"),  # no trust_score
            DocumentBlock(
                bbox=[0, 0, 1, 1],
                text="b",
                trust_score=0.75,
                trust_flags=(),
            ),
        ]
    )
    summary = _document_trust_summary(pipeline)
    assert summary is not None
    assert summary["block_count"] == 2  # both counted
    assert summary["scored_count"] == 1  # only one has a score
    assert summary["average"] == 0.75


def test_summary_is_none_when_pipeline_has_no_document_result():
    class _EmptyPipeline:
        last_document_result = None

    assert _document_trust_summary(_EmptyPipeline()) is None
    assert _trust_header_from_pipeline(_EmptyPipeline()) is None
