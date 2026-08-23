"""Direct tests of the page_range leaf module (P2 #9)."""

from __future__ import annotations

import pytest

from omniscribe.core.pdf.page_range import (
    parse_page_range,
    parse_page_range_with_total,
)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("1-3,5,7-9", [(1, 3), (5, 5), (7, 9)]),
        ("1", [(1, 1)]),
        ("1,2,3", [(1, 1), (2, 2), (3, 3)]),
        ("  1  -  3  ", [(1, 3)]),  # whitespace tolerated
        ("", []),
        ("   ", []),
    ],
)
def test_parse_page_range_valid(spec: str, expected: list[tuple[int, int]]) -> None:
    assert parse_page_range(spec) == expected


@pytest.mark.parametrize("spec", ["abc", "1-", "1-a", "0", "3-1", ",", "1,,2"])
def test_parse_page_range_invalid(spec: str) -> None:
    assert parse_page_range(spec) is None


@pytest.mark.parametrize(
    ("spec", "total_pages", "expected"),
    [
        ("1-3,5,7-9", 10, [0, 1, 2, 4, 6, 7, 8]),
        ("3", 10, [2]),
        ("1-3", 10, [0, 1, 2]),
        # out-of-range pages are dropped (not clamped)
        ("8-12", 5, []),
        # duplicates collapse
        ("1,1,2-3,3", 5, [0, 1, 2]),
        # empty spec -> empty selection
        ("", 10, []),
        ("   ", 10, []),
    ],
)
def test_parse_page_range_with_total_valid(
    spec: str, total_pages: int, expected: list[int]
) -> None:
    assert parse_page_range_with_total(spec, total_pages) == expected


@pytest.mark.parametrize("spec", ["abc", "1-", "1-a", "0", "3-1", ",", "1,,2"])
def test_parse_page_range_with_total_invalid_raises(spec: str) -> None:
    with pytest.raises(ValueError, match="Invalid page range syntax"):
        parse_page_range_with_total(spec, 10)
