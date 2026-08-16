"""Tests for :mod:`omniscribe.core.docx_tree_writer`."""

from __future__ import annotations

from omniscribe.core.block_tree import (
    BlockNode,
    BlockType,
    DocumentTree,
    PageTree,
)
from omniscribe.core.docx_tree_writer import convert_tree_to_docx


def test_docx_tree_writer_creates_real_structure():
    from docx import Document

    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.SECTION_HEADER,
                        bbox=[0, 0, 1, 0.1],
                        text="Title",
                        page_idx=0,
                        level=1,
                    ),
                    BlockNode(
                        block_type=BlockType.LIST_ITEM,
                        bbox=[0, 0.1, 1, 0.2],
                        text="item",
                        page_idx=0,
                        level=0,
                    ),
                    BlockNode(
                        block_type=BlockType.CODE,
                        bbox=[0, 0.2, 1, 0.3],
                        text="x = 1",
                        page_idx=0,
                    ),
                    BlockNode(
                        block_type=BlockType.PARAGRAPH,
                        bbox=[0, 0.3, 1, 0.4],
                        text="body",
                        page_idx=0,
                    ),
                ],
            )
        ]
    )
    stream = convert_tree_to_docx(tree)
    doc = Document(stream)
    # Heading 1 should be present
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
    assert "Title" in headings
    # Code line preserved
    assert any("x = 1" in p.text for p in doc.paragraphs)
    # Body text present
    assert any("body" in p.text for p in doc.paragraphs)
    # List item present
    assert any("item" in p.text for p in doc.paragraphs)
