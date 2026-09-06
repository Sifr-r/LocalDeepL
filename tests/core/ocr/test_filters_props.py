"""Property-based tests for OCR output filters and text deduplication in :mod:`omniscribe.core.ocr.filters`."""

import pytest

from omniscribe.core.ocr.filters import (
    _HALLUCINATION_PATTERNS,
    _is_fallback_response,
    _strip_runaway_repetition,
    _strip_yaml_front_matter,
)

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_line_pool = st.sampled_from(
    ["Title", "Header", "Row A", "Row B", "Cell", "", "   ", "\t"]
)
_lines_strat = st.lists(st.text(max_size=30) | _line_pool, max_size=80)


@settings(max_examples=100, deadline=None)
@given(
    lines=_lines_strat,
    max_repeat=st.integers(min_value=1, max_value=30),
)
def test_filtering_never_increases_count(lines: list[str], max_repeat: int) -> None:
    """_strip_runaway_repetition output length never exceeds input length."""
    out = _strip_runaway_repetition(lines, max_repeat=max_repeat)
    assert len(out) <= len(lines)


@settings(max_examples=100, deadline=None)
@given(
    lines=_lines_strat,
    max_repeat=st.integers(min_value=1, max_value=30),
)
def test_repetition_cap_respected(lines: list[str], max_repeat: int) -> None:
    """No single line appears more than max_repeat times in the filtered output."""
    out = _strip_runaway_repetition(lines, max_repeat=max_repeat)
    counts: dict[str, int] = {}
    for line in out:
        counts[line] = counts.get(line, 0) + 1
        assert counts[line] <= max_repeat


@settings(max_examples=100, deadline=None)
@given(
    lines=_lines_strat,
    max_repeat=st.integers(min_value=1, max_value=30),
)
def test_order_preservation(lines: list[str], max_repeat: int) -> None:
    """Filtered output preserves the exact relative sequence order of lines."""
    out = _strip_runaway_repetition(lines, max_repeat=max_repeat)
    iterator = iter(lines)
    for line in out:
        # Every element in out must be found sequentially in lines
        assert any(item == line for item in iterator)


@settings(max_examples=100, deadline=None)
@given(
    unique_lines=st.sets(st.text(min_size=1, max_size=30), min_size=0, max_size=30),
    max_repeat=st.integers(min_value=1, max_value=10),
)
def test_preserves_all_lines_below_threshold(
    unique_lines: set[str], max_repeat: int
) -> None:
    """Lines that appear <= max_repeat times are completely preserved."""
    lines = list(unique_lines)
    out = _strip_runaway_repetition(lines, max_repeat=max_repeat)
    assert out == lines


def test_empty_lines_and_boxes_handling() -> None:
    """Empty list and lists of empty/blank strings are handled without crashing."""
    assert _strip_runaway_repetition([]) == []
    empty_lines = [""] * 50
    out = _strip_runaway_repetition(empty_lines, max_repeat=5)
    assert len(out) == 5
    assert all(line == "" for line in out)


@settings(max_examples=100, deadline=None)
@given(
    front_matter=st.text(
        alphabet=st.characters(blacklist_characters="`\r\n"), max_size=50
    ),
    body=st.text(alphabet=st.characters(blacklist_characters="`"), max_size=200),
)
def test_strip_yaml_front_matter_invariants(front_matter: str, body: str) -> None:
    """_strip_yaml_front_matter strips header and is idempotent on markdown bodies."""
    raw = f"---\n{front_matter}\n---\n{body}"
    stripped = _strip_yaml_front_matter(raw)
    assert _strip_yaml_front_matter(stripped) == stripped
    assert len(stripped) <= len(raw)
    assert stripped == body.strip()


_SUPPORTED_TRIM_PUNCT = list(".!?\"'`)([]{}<>“”‘’ \t")  # noqa: RUF001


@settings(max_examples=100, deadline=None)
@given(
    fallback=st.sampled_from(_HALLUCINATION_PATTERNS),
    punct_prefix=st.text(alphabet=st.sampled_from(_SUPPORTED_TRIM_PUNCT), max_size=5),
    punct_suffix=st.text(alphabet=st.sampled_from(_SUPPORTED_TRIM_PUNCT), max_size=5),
)
def test_is_fallback_response_detects_hallucinations(
    fallback: str, punct_prefix: str, punct_suffix: str
) -> None:
    """Known hallucination patterns are detected regardless of casing and wrapping punctuation."""
    padded = f"{punct_prefix}{fallback.upper()}{punct_suffix}"
    assert _is_fallback_response(padded) is True


@settings(max_examples=100, deadline=None)
@given(text=st.text(max_size=100))
def test_is_fallback_response_never_crashes(text: str) -> None:
    """_is_fallback_response always returns a boolean for arbitrary inputs."""
    result = _is_fallback_response(text)
    assert isinstance(result, bool)
