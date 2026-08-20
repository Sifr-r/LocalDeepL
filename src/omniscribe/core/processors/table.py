"""Table extraction processor for extracting grid structures from blocks."""

from __future__ import annotations

from typing import TypedDict

from omniscribe.core.block_tree import BlockNode, BlockType, TableNode
from omniscribe.core.document import BBox, DocumentBlock, DocumentPage, DocumentResult
from omniscribe.core.processors.base import (
    ProcessorContract,
    _bbox_area,
    _normalize_space,
)
from omniscribe.core.processors.structure import _TABLE_SPLIT_RE


class _TableCellRecord(TypedDict):
    row_index: int
    column_index: int
    block_index: int
    text: str
    bbox: BBox


class _TableRecord(TypedDict):
    table_index: int
    row_count: int
    column_count: int
    cells: list[_TableCellRecord]


class TableExtractionProcessor:
    """Extract simple local table structures from aligned OCR boxes."""

    name = "table_extraction"
    contract = ProcessorContract.MAY_DELETE

    def __init__(self, row_tolerance: float = 0.018, min_columns: int = 2):
        if row_tolerance <= 0:
            raise ValueError("row_tolerance must be positive")
        if min_columns < 2:
            raise ValueError("min_columns must be at least 2")
        self.row_tolerance = row_tolerance
        self.min_columns = min_columns

    async def process(self, document: DocumentResult) -> DocumentResult:
        tree = document.tree
        for page_idx, page in enumerate(document.pages):
            candidate_indices = [
                index
                for index, block in enumerate(page.blocks)
                if self._is_candidate(block)
            ]
            tables_data = self._extract_page_tables(page, candidate_indices)
            page.metadata["tables"] = tables_data

            # Bounds-check before indexing: ``document.pages`` and ``tree.pages``
            # are populated by the same pipeline today, but a future caller could
            # construct them independently. Without the guard, ``tree.pages[page_idx]``
            # raises ``IndexError`` instead of degrading gracefully.
            if tree and page_idx < len(tree.pages) and tree.pages[page_idx]:
                tree_page = tree.pages[page_idx]
                table_cell_indices: set[int] = set()
                first_cell_map: dict[int, TableNode] = {}

                for table_data in tables_data:
                    row_count = table_data["row_count"]
                    cells_data = table_data["cells"]

                    # Create empty grid
                    max_col = max((c["column_index"] for c in cells_data), default=-1)
                    if max_col < 0:
                        continue

                    grid: list[list[BlockNode]] = [[] for _ in range(row_count)]

                    min_x, min_y, max_x, max_y = (
                        float("inf"),
                        float("inf"),
                        float("-inf"),
                        float("-inf"),
                    )

                    first_b_idx: int | None = None
                    for cell in cells_data:
                        r_idx = cell["row_index"]
                        b_idx = cell["block_index"]
                        table_cell_indices.add(b_idx)
                        if first_b_idx is None or b_idx < first_b_idx:
                            first_b_idx = b_idx

                        if b_idx < len(tree_page.children):
                            child_node = tree_page.children[b_idx]
                            if isinstance(child_node, BlockNode):
                                child_node.block_type = BlockType.TABLE
                                grid[r_idx].append(child_node)
                                bbox = child_node.bbox
                                min_x = min(min_x, bbox[0])
                                min_y = min(min_y, bbox[1])
                                max_x = max(max_x, bbox[2])
                                max_y = max(max_y, bbox[3])

                    if min_x == float("inf"):
                        min_x, min_y, max_x, max_y = 0.0, 0.0, 1.0, 1.0

                    # Pad grid rows to ensure rectangular matrix
                    for r in range(row_count):
                        while len(grid[r]) < max_col + 1:
                            empty_node = BlockNode(
                                block_type=BlockType.TABLE,
                                bbox=(min_x, min_y, max_x, max_y),  # fallback bbox
                                text="",
                                page_idx=page.page_index,
                            )
                            grid[r].append(empty_node)

                    table_node = TableNode(
                        bbox=(min_x, min_y, max_x, max_y),
                        page_idx=page.page_index,
                        rows=row_count,
                        cols=max_col + 1,
                        cells=grid,
                    )
                    tree.tables.append(table_node)
                    if first_b_idx is not None:
                        first_cell_map[first_b_idx] = table_node

                if table_cell_indices:
                    # Place TableNodes in reading order at the position of their first cell
                    new_children: list[BlockNode | TableNode] = []
                    for i, node in enumerate(tree_page.children):
                        if i in first_cell_map:
                            new_children.append(first_cell_map[i])
                        elif i not in table_cell_indices:
                            new_children.append(node)
                    tree_page.children = new_children

        return document

    def _is_candidate(self, block: DocumentBlock) -> bool:
        """Decide whether a block is a possible table cell."""
        text = _normalize_space(block.text)
        if not text:
            return False
        if len(_TABLE_SPLIT_RE.split(text)) >= self.min_columns:
            return True
        if len(text) > 24:
            return False
        x0, _, x1, _ = block.bbox
        area = _bbox_area(block.bbox)
        return max(0.0, x1 - x0) < 0.35 and area < 0.08

    def _extract_page_tables(
        self, page: DocumentPage, candidate_indices: list[int]
    ) -> list[_TableRecord]:
        if not candidate_indices:
            return []

        rows: list[list[int]] = []
        row_sums: list[float] = []

        for block_index in candidate_indices:
            block = page.blocks[block_index]
            center_y = (block.bbox[1] + block.bbox[3]) / 2
            for i, row in enumerate(rows):
                row_center = row_sums[i] / len(row)
                if abs(center_y - row_center) <= self.row_tolerance:
                    row.append(block_index)
                    row_sums[i] += center_y
                    break
            else:
                rows.append([block_index])
                row_sums.append(center_y)

        rows = [sorted(row, key=lambda i: page.blocks[i].bbox[0]) for row in rows]
        rows.sort(key=lambda row: page.blocks[row[0]].bbox[1])
        if len(rows) < 2 or max(len(row) for row in rows) < self.min_columns:
            return []

        cells: list[_TableCellRecord] = []
        for row_index, row in enumerate(rows):
            for column_index, block_index in enumerate(row):
                block = page.blocks[block_index]
                block.metadata["table"] = {
                    "table_index": 0,
                    "row_index": row_index,
                    "column_index": column_index,
                }
                cells.append(
                    {
                        "row_index": row_index,
                        "column_index": column_index,
                        "block_index": block_index,
                        "text": block.text,
                        "bbox": block.bbox,
                    }
                )

        return [
            {
                "table_index": 0,
                "row_count": len(rows),
                "column_count": max(len(row) for row in rows),
                "cells": cells,
            }
        ]
