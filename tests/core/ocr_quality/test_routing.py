"""Unit tests for :class:`omniscribe.core.ocr_quality.routing.QualityRoutingPolicy`."""

from __future__ import annotations

from typing import cast

from omniscribe.core.document import DocumentPage, DocumentResult
from omniscribe.core.ocr_quality.routing import (
    QualityRoutingOptions,
    QualityRoutingPolicy,
)


def test_quality_routing_options_defaults():
    options = QualityRoutingOptions()
    assert options.enabled is False

    custom = QualityRoutingOptions(enabled=True)
    assert custom.enabled is True


def test_apply_disabled_returns_unmodified_document():
    page = DocumentPage(
        page_index=0,
        metadata={"quality": {"findings": [{"code": "empty_page"}]}},
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    result = policy.apply(doc, QualityRoutingOptions(enabled=False))

    assert result is doc
    assert "routing" not in page.metadata


def test_apply_page_without_quality_metadata():
    page = DocumentPage(page_index=0, metadata={})
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    result = policy.apply(doc, QualityRoutingOptions(enabled=True))

    assert result is doc
    assert page.metadata["routing"] == {
        "enabled": True,
        "decision_count": 0,
        "decisions": [],
    }


def test_apply_page_with_non_dict_quality_metadata():
    page = DocumentPage(page_index=0, metadata={"quality": "not-a-dict"})
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    assert page.metadata["routing"] == {
        "enabled": True,
        "decision_count": 0,
        "decisions": [],
    }


def test_apply_empty_page_finding():
    page = DocumentPage(
        page_index=0,
        metadata={
            "quality": {
                "findings": [
                    {"code": "empty_page", "details": "No text detected on canvas"}
                ]
            }
        },
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    routing = cast(dict, page.metadata.get("routing"))
    assert routing is not None
    assert routing["enabled"] is True
    assert routing["decision_count"] == 1
    assert routing["decisions"] == [
        {
            "action": "retry_empty_page",
            "status": "recommended",
            "reason": "empty_page",
        }
    ]


def test_apply_sparse_text_finding():
    page = DocumentPage(
        page_index=0,
        metadata={
            "quality": {
                "findings": [
                    {"code": "sparse_text", "details": "Low word density on page"}
                ]
            }
        },
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    routing = cast(dict, page.metadata.get("routing"))
    assert routing is not None
    assert routing["decision_count"] == 1
    assert routing["decisions"] == [
        {
            "action": "switch_dense_mode",
            "status": "recommended",
            "reason": "sparse_text",
        }
    ]


def test_apply_empty_large_block_finding():
    page = DocumentPage(
        page_index=0,
        metadata={
            "quality": {
                "findings": [
                    {
                        "code": "empty_large_block",
                        "block_index": 4,
                        "details": "Block bbox area > 0.25 but zero characters extracted",
                    }
                ]
            }
        },
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    routing = cast(dict, page.metadata.get("routing"))
    assert routing is not None
    assert routing["decision_count"] == 1
    assert routing["decisions"] == [
        {
            "action": "retry_block_or_grounded",
            "status": "recommended",
            "reason": "empty_large_block",
            "block_index": 4,
        }
    ]


def test_apply_empty_large_block_finding_without_block_index():
    page = DocumentPage(
        page_index=0,
        metadata={
            "quality": {
                "findings": [
                    {
                        "code": "empty_large_block",
                    }
                ]
            }
        },
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    routing = cast(dict, page.metadata.get("routing"))
    assert routing is not None
    assert routing["decision_count"] == 1
    assert routing["decisions"] == [
        {
            "action": "retry_block_or_grounded",
            "status": "recommended",
            "reason": "empty_large_block",
            "block_index": None,
        }
    ]


def test_apply_multiple_findings_and_invalid_entries():
    page = DocumentPage(
        page_index=0,
        metadata={
            "quality": {
                "findings": [
                    "invalid-non-dict-finding",
                    {"code": "empty_page"},
                    {"code": "unrecognized_quality_finding"},
                    {"code": "sparse_text"},
                    None,
                    {"code": "empty_large_block", "block_index": 2},
                ]
            }
        },
    )
    doc = DocumentResult(pages=[page])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    routing = cast(dict, page.metadata.get("routing"))
    assert routing is not None
    assert routing["decision_count"] == 3
    assert routing["decisions"] == [
        {
            "action": "retry_empty_page",
            "status": "recommended",
            "reason": "empty_page",
        },
        {
            "action": "switch_dense_mode",
            "status": "recommended",
            "reason": "sparse_text",
        },
        {
            "action": "retry_block_or_grounded",
            "status": "recommended",
            "reason": "empty_large_block",
            "block_index": 2,
        },
    ]


def test_apply_across_multiple_pages():
    page0 = DocumentPage(
        page_index=0,
        metadata={"quality": {"findings": [{"code": "empty_page"}]}},
    )
    page1 = DocumentPage(
        page_index=1,
        metadata={
            "quality": {
                "findings": [
                    {"code": "sparse_text"},
                    {"code": "empty_large_block", "block_index": 0},
                ]
            }
        },
    )
    page2 = DocumentPage(
        page_index=2,
        metadata={"quality": {"findings": []}},
    )
    doc = DocumentResult(pages=[page0, page1, page2])
    policy = QualityRoutingPolicy()

    policy.apply(doc, QualityRoutingOptions(enabled=True))

    # ``metadata`` is typed loosely so the deeply-nested routing dict
    # access needs a cast at the entry point.
    page0_routing = cast(dict, page0.metadata["routing"])
    page1_routing = cast(dict, page1.metadata["routing"])
    assert page0_routing["decision_count"] == 1
    assert page0_routing["decisions"][0]["action"] == "retry_empty_page"

    assert page1_routing["decision_count"] == 2
    assert page1_routing["decisions"][0]["action"] == "switch_dense_mode"
    assert page1_routing["decisions"][1]["action"] == "retry_block_or_grounded"
    assert page1_routing["decisions"][1]["block_index"] == 0

    page2_routing = cast(dict, page2.metadata["routing"])
    assert page2_routing["decision_count"] == 0
    assert page2_routing["decisions"] == []
