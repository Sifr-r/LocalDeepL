"""Tests for :mod:`omniscribe.core.tree_export`."""

from __future__ import annotations

import json

from omniscribe.core.block_tree import (
    BlockNode,
    BlockType,
    DocumentTree,
    PageTree,
)
from omniscribe.core.tree_export import export_json, export_json_bytes


def test_tree_export_json_round_trip():
    tree = DocumentTree(
        pages=[
            PageTree(
                page_idx=0,
                children=[
                    BlockNode(
                        block_type=BlockType.PARAGRAPH,
                        bbox=[0, 0, 1, 0.1],
                        text="hi",
                        page_idx=0,
                    ),
                ],
            )
        ]
    )
    raw = export_json(tree)
    data = json.loads(raw)
    assert "pages" in data
    assert data["pages"][0]["children"][0]["text"] == "hi"
    # Bytes variant
    b = export_json_bytes(tree)
    assert isinstance(b, bytes)
    assert json.loads(b.decode("utf-8"))["pages"][0]["page_idx"] == 0
