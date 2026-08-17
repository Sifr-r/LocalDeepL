"""Direct tests of the page_range leaf module (P2 #9)."""

from __future__ import annotations

import pytest

from omniscribe.core.pdf.page_range import parse_page_range


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
