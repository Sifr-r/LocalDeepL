"""Property-based tests for page range parsing and serialization in :mod:`omniscribe.core.pdf`."""

from __future__ import annotations

import pytest

from omniscribe.core.pdf import (
    parse_page_range,
    parse_page_range_with_total,
    serialize_page_range,
)

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_positive_pages_set = st.sets(
    st.integers(min_value=1, max_value=500), min_size=1, max_size=60
)
_positive_pages_list = st.lists(
    st.integers(min_value=1, max_value=500), min_size=1, max_size=100
)


@settings(max_examples=100, deadline=None)
@given(pages=_positive_pages_set)
def test_roundtrip_valid_sorted_positive_integers(pages: set[int]) -> None:
    """Serialization and parsing form a lossless round-trip for valid pages."""
    spec = serialize_page_range(pages)
    assert isinstance(spec, str)

    # 1-indexed tuple parsing
    ranges = parse_page_range(spec)
    assert ranges is not None
    recovered_pages = {p for start, end in ranges for p in range(start, end + 1)}
    assert recovered_pages == pages

    # 0-indexed total-clamped parsing
    max_page = max(pages)
    zero_indexed = parse_page_range_with_total(spec, total_pages=max_page)
    assert set(zero_indexed) == {p - 1 for p in pages}
    assert zero_indexed == sorted(zero_indexed)


@settings(max_examples=100, deadline=None)
@given(pages=_positive_pages_list)
def test_serialization_collapses_duplicates(pages: list[int]) -> None:
    """Duplicate page numbers are deduplicated during serialization."""
    spec_from_list = serialize_page_range(pages)
    spec_from_set = serialize_page_range(set(pages))
    assert spec_from_list == spec_from_set

    # Verify parsed tuples are ordered and disjoint
    ranges = parse_page_range(spec_from_list)
    assert ranges is not None
    for i in range(len(ranges) - 1):
        assert ranges[i][1] < ranges[i + 1][0]


@settings(max_examples=100, deadline=None)
@given(
    valid_pages=st.lists(st.integers(min_value=1, max_value=100), max_size=10),
    invalid_page=st.integers(max_value=0),
)
def test_serialization_rejects_negative_or_zero(
    valid_pages: list[int], invalid_page: int
) -> None:
    """serialize_page_range raises ValueError when any page <= 0."""
    all_pages = valid_pages + [invalid_page]
    with pytest.raises(ValueError, match="positive integers >= 1"):
        serialize_page_range(all_pages)


def test_serialization_empty() -> None:
    """Empty input serializes to empty string."""
    assert serialize_page_range([]) == ""
    assert parse_page_range("") == []
    assert parse_page_range_with_total("", total_pages=10) == []


@settings(max_examples=100, deadline=None)
@given(invalid_page=st.integers(max_value=0))
def test_parsing_rejects_negative_or_zero(invalid_page: int) -> None:
    """parse_page_range returns None and parse_page_range_with_total raises on <= 0."""
    spec = str(invalid_page)
    assert parse_page_range(spec) is None
    with pytest.raises(ValueError, match="Invalid page range syntax"):
        parse_page_range_with_total(spec, total_pages=10)


@settings(max_examples=100, deadline=None)
@given(
    pages=_positive_pages_set,
    total_pages=st.integers(min_value=1, max_value=600),
)
def test_parse_with_total_clamps_and_filters(pages: set[int], total_pages: int) -> None:
    """parse_page_range_with_total retains only pages <= total_pages (0-indexed)."""
    spec = serialize_page_range(pages)
    parsed = parse_page_range_with_total(spec, total_pages=total_pages)

    expected = sorted([p - 1 for p in pages if 1 <= p <= total_pages])
    assert parsed == expected
    assert all(0 <= p < total_pages for p in parsed)


@settings(max_examples=100, deadline=None)
@given(text=st.text(max_size=100))
def test_random_string_parsing_safe(text: str) -> None:
    """Parsing random text never causes unhandled exceptions."""
    result = parse_page_range(text)
    if result is not None:
        for start, end in result:
            assert 1 <= start <= end
