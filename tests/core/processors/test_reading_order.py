"""Tests for :class:`ReadingOrderProcessor`.

D1-08 audit fix: ``_sort_key`` used to unpack ``block.bbox``
without a ``None`` guard. While the type system forbids a
``DocumentBlock`` with ``bbox=None`` at construction time,
nothing stops a downstream code path from mutating the
attribute to ``None`` after the fact. The defensive guard
keeps the sort from raising on a hypothetical regression.

The regression test pins the new behaviour: a block with
``bbox=None`` is sorted to the end of the row (all-zero
sentinel) instead of raising.
"""

from __future__ import annotations

from omniscribe.core.document import (
    DocumentBlock,
    DocumentPage,
    DocumentResult,
)
from omniscribe.core.processors.reading_order import ReadingOrderProcessor


def _make_block(
    text: str = "x", *, bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
) -> DocumentBlock:
    """Build a :class:`DocumentBlock` with the given bbox."""
    return DocumentBlock(bbox=bbox, text=text)


def test_sort_key_handles_none_bbox() -> None:
    """``_sort_key`` does not raise on ``block.bbox is None``.

    D1-08 audit fix: the previous implementation called
    ``x0, y0, _, _ = block.bbox`` and crashed with ``TypeError``
    for a block whose ``bbox`` attribute was ``None``. The
    defensive guard uses an all-zero sentinel so the block is
    sorted last instead of raising.
    """
    proc = ReadingOrderProcessor()
    block = _make_block(bbox=(0.1, 0.2, 0.3, 0.4))
    # Mutate past the type guard to exercise the defensive branch.
    object.__setattr__(block, "bbox", None)
    key = proc._sort_key(block)  # type: ignore[attr-defined]
    assert isinstance(key, tuple)
    assert len(key) == 3
    # The all-zero sentinel means the block sorts into row 0
    # (round(0.0 / 0.02) = 0), x=0.0, y=0.0.
    assert key == (0, 0.0, 0.0)


async def test_process_succeeds_with_none_bbox_block() -> None:
    """``process()`` does not raise when a page has a None-bbox block.

    End-to-end version of the regression: a page containing a
    mix of normal blocks and a None-bbox block (typical of a
    code path that mutates the bbox after construction) must
    sort cleanly. The None-bbox block is sorted to the end of
    the row-major order.
    """
    proc = ReadingOrderProcessor()
    none_block = _make_block(bbox=(0.0, 0.0, 0.0, 0.0))
    high_row = _make_block(bbox=(0.0, 0.5, 0.4, 0.6))  # row 25
    low_row = _make_block(bbox=(0.0, 0.1, 0.4, 0.2))  # row 5
    # Mutate past the type guard to exercise the defensive branch.
    object.__setattr__(none_block, "bbox", None)

    page = DocumentPage(page_index=0)
    page.blocks = [high_row, none_block, low_row]
    document = DocumentResult(pages=[page])
    # The previous implementation raised TypeError here.
    await proc.process(document)

    # ``process`` sorts in place; look up by identity. The
    # None-bbox sentinel sorts to the *start* of the row-major
    # order (all-zero key) — same as a block at the page's
    # top-left corner. The other two blocks sort by row
    # tolerance, so the low row comes second and the high row
    # third.
    reading_order_by_block = {id(b): b.reading_order for b in page.blocks}
    assert reading_order_by_block[id(none_block)] == 0, "None-bbox sentinel sorts first"
    assert reading_order_by_block[id(low_row)] == 1, "low row sorts second"
    assert reading_order_by_block[id(high_row)] == 2, "high row sorts third"
