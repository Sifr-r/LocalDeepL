"""Tests for the shared workflow helpers in `core.workflows.base`.

Focused on `_cross_page_merge` since the rest of `EngineBase` is exercised
through the engine tests in `test_pipeline.py`.
"""

from __future__ import annotations

from local_deepl.core.workflows.base import EngineBase


def _engine() -> EngineBase:
    """Construct an `EngineBase` without invoking `__init_subclass__` hooks."""

    class _StubEngine(EngineBase):
        pass

    return _StubEngine()


def test_cross_page_merge_joins_unterminated_tail_into_next_page() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Hello world")],
        1: [([0.0, 0.0, 1.0, 0.1], "continues here")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "Hello world continues here")


def test_cross_page_merge_does_not_join_terminated_sentence() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Sentence ends.")],
        1: [([0.0, 0.0, 1.0, 0.1], "New sentence.")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Sentence ends.")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "New sentence.")


def test_cross_page_merge_handles_single_page() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Only one")],
    }
    _engine()._cross_page_merge(pages, [0])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Only one")


def test_cross_page_merge_skips_blank_tail_box() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [
            ([0.0, 0.0, 1.0, 0.1], "Sentence."),
            ([0.0, 0.0, 1.0, 0.1], "  "),
        ],
        1: [([0.0, 0.0, 1.0, 0.1], "Next page")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    # The terminated sentence is untouched; the blank box is too.
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Sentence.")
    assert pages[0][1] == ([0.0, 0.0, 1.0, 0.1], "  ")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "Next page")


def test_cross_page_merge_skips_blank_head_box() -> None:
    """If the next page's first non-blank box isn't its literal first, find it."""
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Trailing")],
        1: [
            ([0.0, 0.0, 1.0, 0.1], "  "),
            ([0.0, 0.0, 1.0, 0.1], "real head"),
        ],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "")
    # The merge targets the first non-blank head box.
    assert pages[1][1] == ([0.0, 0.0, 1.0, 0.1], "Trailing real head")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "  ")
