"""Tests for the trust fields on :class:`DocumentBlock`."""

from __future__ import annotations

from omniscribe.core.document import DocumentBlock


class TestTrustFields:
    def test_defaults_to_none(self):
        block = DocumentBlock(bbox=[0.0, 0.0, 1.0, 1.0], text="hi")
        assert block.trust_score is None
        assert block.trust_flags is None

    def test_can_be_populated(self):
        block = DocumentBlock(
            bbox=[0.0, 0.0, 1.0, 1.0],
            text="hi",
            trust_score=0.42,
            trust_flags=("watermark_hit",),
        )
        assert block.trust_score == 0.42
        assert block.trust_flags == ("watermark_hit",)

    def test_default_tuple_contents_unordered_match(self):
        block = DocumentBlock(
            bbox=[0.0, 0.0, 1.0, 1.0],
            text="hi",
            trust_flags=("x",),
        )
        # Trust flags tuple contents are immutable (tuple type).
        assert block.trust_flags == ("x",)
        assert tuple(block.trust_flags) == ("x",)


class TestExistingBehavior:
    def test_slots_still_work(self):
        # slots=True means arbitrary attribute assignment must raise.
        block = DocumentBlock(bbox=[0.0, 0.0, 1.0, 1.0], text="hi")
        import pytest

        with pytest.raises(AttributeError):
            block.nonexistent_field = 1  # type: ignore[attr-defined]
