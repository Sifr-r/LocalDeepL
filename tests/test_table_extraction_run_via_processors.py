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

from omniscribe.core.block_tree import DocumentTree, PageTree
from omniscribe.core.document import DocumentBlock, DocumentResult
from omniscribe.core.processors import (
    TableExtractionProcessor,
    run_document_processors,
)
from omniscribe.core.processors.base import _bbox_area

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


async def test_table_extraction_handles_tree_with_fewer_pages_than_document():
    """§4.9 regression: page index out of tree range degrades gracefully.

    Pre-fix, ``if tree and tree.pages[page_idx]:`` evaluated
    ``tree.pages[page_idx]`` directly. With ``document.pages`` containing
    pages 0..1 but ``tree.pages`` containing only page 0, page 1 raised
    ``IndexError`` instead of being skipped.
    """
    document = DocumentResult.from_pages_data(
        {
            0: [([0.1, 0.1, 0.5, 0.2], "Header")],
            1: [
                ([0.1, 0.2, 0.3, 0.24], "A"),
                ([0.4, 0.2, 0.6, 0.24], "B"),
                ([0.1, 0.3, 0.3, 0.34], "1"),
                ([0.4, 0.3, 0.6, 0.34], "2"),
            ],
        }
    )
    # Manually inject a tree that only covers page 0 — simulates a
    # future caller constructing the tree independently of pages.
    document.tree = DocumentTree(pages=[PageTree(page_idx=0, children=[])])

    # Must not raise IndexError on page 1.
    result = await TableExtractionProcessor().process(document)

    assert result is document  # mutated in place
    assert result.tree is not None
    # The bounds-check skipped tree mutation for page 1, so no tables
    # were appended to tree.tables even though page 1 has a valid grid.
    assert result.tree.tables == []
    # Page 0 had no candidate blocks -> metadata tables list is empty.
    assert result.pages[0].metadata.get("tables") == []
    # Page 1's metadata was still populated (tables_data is computed
    # before the bounds check), but the tree mutation was skipped.
    page1_tables = result.pages[1].metadata["tables"]
    assert isinstance(page1_tables, list)
    assert len(page1_tables) == 1


def test_table_extraction_is_candidate_uses_shared_bbox_area():
    """§4.3 regression: ``_is_candidate`` reuses ``_bbox_area``.

    Construct two blocks that exercise both the ``width < 0.35`` and
    ``area < 0.08`` cuts. The wide-thin block is a candidate
    (width < 0.35, area < 0.08); the wide-fat block is not. Assert the
    boolean is identical to the pre-refactor expression
    ``width * height`` to lock in semantic equivalence with
    ``processors/base.py:_bbox_area``.
    """
    # wide-thin: width=0.2 < 0.35, area=0.2*0.05=0.01 < 0.08 -> candidate
    block_thin = DocumentBlock(
        bbox=(0.0, 0.0, 0.2, 0.05),
        text="thin",
        source_processor="ocr",
    )
    # wide-fat: width=0.2 < 0.35 BUT area=0.2*0.5=0.10 >= 0.08 -> not candidate
    block_fat = DocumentBlock(
        bbox=(0.0, 0.0, 0.2, 0.5),
        text="fat",
        source_processor="ocr",
    )

    proc = TableExtractionProcessor()
    assert proc._is_candidate(block_thin) is True
    assert proc._is_candidate(block_fat) is False

    # Cross-check: the helper and the old inline formula agree.
    assert _bbox_area(block_thin.bbox) == 0.2 * 0.05
    assert _bbox_area(block_fat.bbox) == 0.2 * 0.5
