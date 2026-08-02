"""Regression test for review C1.

Pre-fix, `TableExtractionProcessor.process()` raised `TypeError:
TableNode.__init__() got an unexpected keyword argument 'block_type'`
when called through `run_document_processors`, because the broken
code path was guarded by `if tree and tree.pages[page_idx]:` and
the tree is only initialized by `run_document_processors`. The
original direct-call test bypassed the entry point and so missed
the bug; this test exercises the production path.
"""

from __future__ import annotations

from omniscribe.core.document import DocumentResult
from omniscribe.core.processors import (
    TableExtractionProcessor,
    run_document_processors,
)

# A 2x2 grid on page 0. Bboxes are normalized in 0..1 and the y
# values place "Name"/"Total" in row 1 and "A"/"$1" in row 2, so
# `row_tolerance=0.018` (default) buckets them correctly.
_GRID_BLOCKS = {
    0: [
        ([0.1, 0.02, 0.8, 0.08], "Report Header"),  # header, not a cell
        ([0.1, 0.2, 0.3, 0.24], "Name"),
        ([0.4, 0.2, 0.6, 0.24], "Total"),
        ([0.1, 0.3, 0.3, 0.34], "A"),
        ([0.4, 0.3, 0.6, 0.34], "$1"),
    ],
}


async def test_table_extraction_passes_when_invoked_via_run_document_processors():
    """Verify the production entry point does not crash on a 2x2 grid.

    Pre-fix this raised `TypeError: TableNode.__init__() got an
    unexpected keyword argument 'block_type'` from inside the
    `if tree and tree.pages[page_idx]:` branch.
    """
    document = DocumentResult.from_pages_data(_GRID_BLOCKS)

    result = await run_document_processors(document, [TableExtractionProcessor()])

    # The tree must have been initialized by run_document_processors
    # and at least one table must have been extracted from the grid.
    assert result.tree is not None
    assert len(result.tree.tables) == 1
    table = result.tree.tables[0]
    assert table.rows == 2
    assert table.cols == 2
    # Cell text survives the TableNode construction.
    cell_texts = sorted(c.text for row in table.cells for c in row if c.text)
    assert "A" in cell_texts
    assert "Name" in cell_texts


async def test_table_extraction_skips_pages_without_grid():
    """Non-tabular pages must not produce a TableNode.

    Guards against a regression where the C1 fix accidentally
    over-constructs TableNode for sparse pages.
    """
    document = DocumentResult.from_pages_data(
        {0: [([0.1, 0.1, 0.5, 0.2], "Just a paragraph.")]}
    )

    result = await run_document_processors(document, [TableExtractionProcessor()])

    assert result.tree is not None
    # No candidate blocks -> no tables. tree.tables stays empty.
    assert result.tree.tables == []
