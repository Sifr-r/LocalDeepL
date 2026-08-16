"""Tests for :mod:`omniscribe.core.html_writer`."""

from __future__ import annotations

from omniscribe.core.block_tree import (
    BlockNode,
    BlockType,
    DocumentTree,
    EquationNode,
    FigureNode,
    PageTree,
    TableNode,
)
from omniscribe.core.html_writer import render_html


def test_html_writer_emits_semantic_tags():
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.SECTION_HEADER,
                        bbox=[0, 0, 1, 0.1],
                        text="Chapter 1",
                        page_idx=0,
                        level=1,
                    ),
                    BlockNode(
                        block_type=BlockType.PARAGRAPH,
                        bbox=[0, 0.1, 1, 0.2],
                        text="Body text.",
                        page_idx=0,
                        confidence=0.85,
                    ),
                    BlockNode(
                        block_type=BlockType.CODE,
                        bbox=[0, 0.2, 1, 0.3],
                        text="print(hi)",
                        page_idx=0,
                    ),
                ],
            ),
            PageTree(
                page_idx=1,
                children=[
                    BlockNode(
                        block_type=BlockType.PARAGRAPH,
                        bbox=[0, 0, 1, 0.1],
                        text="Page 2",
                        page_idx=1,
                    ),
                ],
            ),
        ]
    )
    html = render_html(tree)
    assert "<h1" in html and "Chapter 1" in html
    assert "<p" in html and "Body text." in html
    assert "<pre" in html and "<code>print(hi)</code>" in html
    assert "<!-- PageBreak -->" in html
    assert "data-block-id" in html
    assert 'data-confidence="0.850"' in html
    assert '<section data-page-idx="0">' in html
    assert '<section data-page-idx="1">' in html


def test_html_writer_handles_figure_and_table():
    table = TableNode(
        rows=2,
        cols=2,
        page_idx=0,
        bbox=[0, 0, 1, 0.5],
        cells=[
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0, 0, 0.5, 0.25],
                    text="A",
                    page_idx=0,
                ),
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.5, 0, 1, 0.25],
                    text="B",
                    page_idx=0,
                ),
            ],
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0, 0.25, 0.5, 0.5],
                    text="C",
                    page_idx=0,
                ),
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.5, 0.25, 1, 0.5],
                    text="D",
                    page_idx=0,
                ),
            ],
        ],
    )
    # Put the table on the tree's `tables` list; the figure goes in page children.
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.FIGURE,
                        bbox=[0, 0, 1, 0.5],
                        text="caption text",
                        page_idx=0,
                    ),
                ],
            )
        ],
        tables=[table],
    )
    html = render_html(tree)
    assert "<figure" in html and "<figcaption>caption text</figcaption>" in html
    # The tables list is also rendered (figure + table block).
    assert "<table" in html
    # Header row uses <th>, data rows use <td>; the <th> contains a data-block-id attr
    assert ">A</th>" in html and ">C</td>" in html


def test_html_writer_does_not_duplicate_figure_when_on_both_page_and_tree():
    """Regression for H6: ``from_document_result`` adds a figure to both
    ``page.children`` (as a ``BlockNode``) and ``tree.figures`` (as a
    ``FigureNode``). The renderer used to emit a ``<figure>`` from each
    location, producing two copies of the same caption. The post-walk of
    ``tree.figures`` is gone, so the figure renders exactly once.
    """
    figure_block_id = "figure-block-1"
    fig_node = FigureNode(
        page_idx=0,
        bbox=(0.0, 0.0, 1.0, 0.5),
        image_bytes=None,
        caption="caption text",
        block_id="figure-node-1",
    )
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.FIGURE,
                        bbox=(0.0, 0.0, 1.0, 0.5),
                        text="caption text",
                        page_idx=0,
                        block_id=figure_block_id,
                    )
                ],
            )
        ],
        figures=[fig_node],
    )
    html = render_html(tree)
    # Exactly one <figure ...> tag in the output.
    assert html.count("<figure") == 1, html
    # The single figure is the page-walk one (carries the bbox metadata).
    assert figure_block_id in html
    # The caption still renders once.
    assert "caption text" in html


def test_html_writer_does_not_duplicate_equation_when_on_both_page_and_tree():
    """Regression for H6: the post-walk of ``tree.equations`` used to
    append a ``<span>`` for every equation. Equations are sourced from
    ``page.children`` via ``_render_block``'s ``equation`` branch, so the
    post-walk has been removed; rendering the same equation on both sides
    must not produce two ``<span>``s.
    """
    equation_block_id = "equation-block-1"
    eq_node = EquationNode(
        page_idx=0,
        bbox=(0.0, 0.0, 1.0, 0.1),
        latex="E = mc^2",
        block_id="equation-node-1",
    )
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.EQUATION,
                        bbox=(0.0, 0.0, 1.0, 0.1),
                        text="E = mc^2",
                        page_idx=0,
                        block_id=equation_block_id,
                    )
                ],
            )
        ],
        equations=[eq_node],
    )
    html = render_html(tree)
    # Exactly one <span data-block-id=...> tag tied to the equation block.
    assert html.count(equation_block_id) == 1, html
    # The equation content is rendered exactly once.
    assert html.count("E = mc^2") == 1, html


def test_html_writer_renders_table_only_from_tree_tables():
    """Tables live on ``tree.tables`` (the table-extraction processor
    removes the cell blocks from ``page.children``), so the ``<table>``
    tag must come from the ``tree.tables`` post-walk. If a table-shaped
    block is also present in ``page.children``, it must not produce a
    second ``<table>`` element.
    """
    table = TableNode(
        rows=2,
        cols=1,
        page_idx=0,
        bbox=(0.0, 0.0, 1.0, 0.2),
        cells=[
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=(0.0, 0.0, 1.0, 0.1),
                    text="head",
                    page_idx=0,
                )
            ],
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=(0.0, 0.1, 1.0, 0.2),
                    text="data",
                    page_idx=0,
                )
            ],
        ],
        block_id="table-only-1",
    )
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.PARAGRAPH,
                        bbox=(0.0, 0.2, 1.0, 0.3),
                        text="body",
                        page_idx=0,
                    )
                ],
            )
        ],
        tables=[table],
    )
    html = render_html(tree)
    assert html.count("<table") == 1, html
    # Row 0 -> <th>, row 1 -> <td>; both cell texts render once.
    assert ">head</th>" in html
    assert ">data</td>" in html
    assert "body" in html
