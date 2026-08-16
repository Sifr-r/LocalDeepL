"""Tests for :mod:`omniscribe.core.trocr_engine`."""

from __future__ import annotations

from omniscribe.core.trocr_engine import _heuristic_confidence


def test_trocr_heuristic_confidence():
    assert _heuristic_confidence("") == 0.0
    assert _heuristic_confidence("bcdfg") == 0.2  # no vowel
    # Two words sits in the 0.7 band
    assert _heuristic_confidence("hello world") == 0.7
    # Three or more words triggers the higher confidence band
    assert _heuristic_confidence("one two three four") == 0.85


def test_trocr_engine_is_available():
    from omniscribe.core.trocr_engine import TrOCREngine

    eng = TrOCREngine()
    # The function must return a bool; the actual value depends on env
    assert isinstance(eng.is_available(), bool)
