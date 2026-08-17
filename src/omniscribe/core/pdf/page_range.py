"""Leaf module for page-range string parsing.

Lives in `core/pdf` (not `core/workflows/utils`) so that both
`core/pdf/rasterizer.py` and `core/workflows/utils.py` can import
it without crossing the `rasterizer → workflows.utils → workflows
→ hybrid → pdf` import cycle that originally caused
`_parse_page_range_local` to be duplicated as a cycle-breaker.

The parser accepts strings like "1-3,5,7-9" and returns a list
of (start, end) page tuples (1-indexed, inclusive). Invalid
input returns None.
"""

from __future__ import annotations

import re
from typing import Final

_PAGE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def parse_page_range(spec: str) -> list[tuple[int, int]] | None:
    """Parse a page range string into a list of (start, end) tuples.

    Examples:
        "1-3,5,7-9" -> [(1, 3), (5, 5), (7, 9)]
        "1"        -> [(1, 1)]
        ""         -> []
        "abc"      -> None (invalid)
    """
    if not spec or not spec.strip():
        return []
    out: list[tuple[int, int]] = []
    for token in spec.split(","):
        m = _PAGE_PATTERN.match(token)
        if m is None:
            return None
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) is not None else start
        if start < 1 or end < start:
            return None
        out.append((start, end))
    return out
