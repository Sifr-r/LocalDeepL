"""Tests for §9g — DenseMode enum comparisons in HybridEngine."""

from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from omniscribe.core.document import DenseMode
from omniscribe.core.workflows.hybrid import HybridEngine


def _structured(
    n_boxes_per_page: dict[int, int],
) -> dict[int, list[tuple[tuple[float, float, float, float], str]]]:
    return {
        p: [((0.1, 0.1, 0.9, 0.2), "") for _ in range(n)]
        for p, n in n_boxes_per_page.items()
    }


def _engine() -> HybridEngine:
    """Bare HybridEngine; tests only call pure helpers."""
    with TemporaryDirectory():
        return HybridEngine(
            aligner=None,  # type: ignore[arg-type]
            ocr_processor=None,  # type: ignore[arg-type]
            pdf_handler=None,  # type: ignore[arg-type]
            output_writer=lambda *_: None,
        )


def test_dense_mode_always_adds_every_page():
    engine = _engine()
    structured = _structured({0: 1, 1: 2, 2: 0})
    result = engine._select_dense_pages(
        pages_structured=structured,
        page_nums=[0, 1, 2],
        dense_mode=DenseMode.ALWAYS,
        dense_threshold=10,
    )
    assert result == {0, 1, 2}


def test_dense_mode_auto_threshold_filters():
    engine = _engine()
    structured = _structured({0: 5, 1: 11, 2: 100})
    result = engine._select_dense_pages(
        pages_structured=structured,
        page_nums=[0, 1, 2],
        dense_mode=DenseMode.AUTO,
        dense_threshold=10,
    )
    # > 10 boxes → dense
    assert result == {1, 2}


def test_dense_mode_never_adds_nothing():
    engine = _engine()
    structured = _structured({0: 50, 1: 100})
    result = engine._select_dense_pages(
        pages_structured=structured,
        page_nums=[0, 1],
        dense_mode=DenseMode.NEVER,
        dense_threshold=0,
    )
    assert result == set()


async def test_execute_rejects_string_dense_mode():
    """§9g: a legacy caller passing a raw string must raise ValueError."""
    engine = _engine()
    with pytest.raises(ValueError, match="dense_mode must be a DenseMode"):
        await engine.execute(
            "in.pdf",
            "out.pdf",
            dense_mode="auto",  # type: ignore[arg-type]
        )
