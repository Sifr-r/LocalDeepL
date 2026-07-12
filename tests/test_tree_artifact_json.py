"""Tests for the JSON tree artifact (review M4).

The pre-fix code path used `pickle.dumps` / `pickle.load` to round-trip
the DocumentTree through the artifact store. Pickle on user-influenced
bytes is an RCE footgun: a `__reduce__` method in the loaded object's
class is called during deserialization, with no sandboxing. Phase D
replaces the format with JSON via `DocumentTree.from_dict` /
`to_dict`, and `read_tree` / `write_tree_atomic` wrap the I/O.

These tests cover the round-trip on a non-trivial tree (multiple
pages, tables, figures, equations, sections, spans) plus the
error paths of `read_tree` so we never silently accept malformed
artifacts.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from local_deepl.api.services.tree_artifact import (
    TreeArtifactError,
    read_tree,
    write_tree_atomic,
)
from local_deepl.core.block_tree import (
    BlockNode,
    BlockType,
    DocumentTree,
    EquationNode,
    FigureNode,
    PageTree,
    Section,
    Span,
    TableNode,
)


def _build_round_trip_tree() -> DocumentTree:
    """A tree that exercises every node type that has its own `from_dict`.

    We don't try to construct a "real" document — just enough variety
    that a missing / misnamed field in any `from_dict` would surface
    as a round-trip mismatch.
    """
    page0 = PageTree(
        page_idx=0,
        width=612,
        height=792,
        metadata={"layout": {"has_figures": True}},
        children=[
            BlockNode(
                block_type=BlockType.SECTION_HEADER,
                bbox=[0.1, 0.05, 0.9, 0.1],
                text="Chapter 1",
                page_idx=0,
                level=1,
                section_hierarchy=["Chapter 1"],
                spans=[Span(text="Chapter 1", bold=True)],
            ),
            BlockNode(
                block_type=BlockType.PARAGRAPH,
                bbox=[0.1, 0.2, 0.9, 0.4],
                text="Some text with Ünicode and éàcent.",
                page_idx=0,
                confidence=0.92,
                metadata={"section": {"section_index": 0}},
            ),
        ],
    )
    page1 = PageTree(
        page_idx=1,
        width=612,
        height=792,
        children=[
            BlockNode(
                block_type=BlockType.PARAGRAPH,
                bbox=[0.1, 0.1, 0.9, 0.3],
                text="Second page body.",
                page_idx=1,
            ),
        ],
    )
    table_node = TableNode(
        rows=2,
        cols=2,
        page_idx=1,
        bbox=[0.1, 0.5, 0.9, 0.8],
        cells=[
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.1, 0.5, 0.5, 0.6],
                    text="A",
                    page_idx=1,
                ),
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.5, 0.5, 0.9, 0.6],
                    text="B",
                    page_idx=1,
                ),
            ],
            [
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.1, 0.7, 0.5, 0.8],
                    text="1",
                    page_idx=1,
                ),
                BlockNode(
                    block_type=BlockType.PARAGRAPH,
                    bbox=[0.5, 0.7, 0.9, 0.8],
                    text="2",
                    page_idx=1,
                ),
            ],
        ],
    )
    figure_node = FigureNode(
        page_idx=0,
        bbox=[0.1, 0.5, 0.5, 0.8],
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        caption="A test figure",
    )
    equation_node = EquationNode(
        page_idx=0,
        bbox=[0.6, 0.5, 0.9, 0.7],
        latex=r"E = mc^2",
    )
    section = Section(
        title="Chapter 1",
        level=1,
        start_page=0,
        children=[
            Section(title="1.1 Subsection", level=2, start_page=0),
        ],
    )
    return DocumentTree(
        pages=[page0, page1],
        sections=[section],
        tables=[table_node],
        figures=[figure_node],
        equations=[equation_node],
        source_path="in-memory://test.pdf",
        metadata={"summary": "round-trip fixture"},
    )


def test_round_trip_preserves_every_field(tmp_path: Path):
    """The whole point of the artifact: load a tree back and get
    a tree that is semantically identical. We compare `to_dict()`
    output rather than the in-memory objects directly because the
    BlockNode `block_id` is generated on construction; comparing
    via the dict normalizes that."""
    original = _build_round_trip_tree()
    path = tmp_path / "tree.json"

    write_tree_atomic(original, path)
    loaded = read_tree(path)

    # The to_dict() output is the canonical equality — any field
    # that round-trips differently would show up here.
    assert loaded.to_dict() == original.to_dict()

    # The figure's image bytes round-trip exactly (modulo the
    # base64 detour, which is lossless by construction).
    assert loaded.figures[0].image_bytes == original.figures[0].image_bytes
    assert loaded.figures[0].image_bytes is not None
    # The JSON file on disk has the base64 form, not the raw bytes.
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["figures"][0]["image_bytes_b64"] == base64.b64encode(
        original.figures[0].image_bytes
    ).decode("ascii")


def test_write_is_atomic_no_partial_file_on_existing_target(tmp_path: Path):
    """write_tree_atomic must use a tempfile + rename so a pre-existing
    artifact is replaced atomically; a reader that opens the path
    mid-write either sees the old content or the new content,
    never a half-written file."""
    path = tmp_path / "tree.json"

    # First write: original.
    original = _build_round_trip_tree()
    write_tree_atomic(original, path)
    before_bytes = path.read_bytes()
    assert json.loads(before_bytes)  # valid JSON

    # Second write: different content. After this call, the file must
    # be either the old bytes or the new bytes — no mix.
    replacement = DocumentTree(
        source_path="different",
        metadata={"replaced": True},
    )
    write_tree_atomic(replacement, path)
    after = json.loads(path.read_bytes())

    # The new content is the replacement's dict.
    assert after == replacement.to_dict()
    # The old file was fully replaced — file size may differ.
    assert path.read_bytes() != before_bytes


def test_no_tmp_file_left_behind(tmp_path: Path):
    """The write uses `tmp.replace(path)`; if the rename succeeds the
    .tmp is gone. (If the write process is killed mid-flight, the
    .tmp may be left behind; we don't claim to handle that, but the
    success path must not leave one.)"""
    path = tmp_path / "tree.json"
    write_tree_atomic(_build_round_trip_tree(), path)
    siblings = list(tmp_path.iterdir())
    assert siblings == [path]


def test_read_tree_rejects_missing_file(tmp_path: Path):
    path = tmp_path / "does-not-exist.json"
    with pytest.raises(FileNotFoundError):
        read_tree(path)


def test_read_tree_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "tree.json"
    path.write_text("this is not { valid json", encoding="utf-8")
    with pytest.raises(TreeArtifactError, match="not valid JSON"):
        read_tree(path)


def test_read_tree_rejects_wrong_root_type(tmp_path: Path):
    path = tmp_path / "tree.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")  # list, not dict
    with pytest.raises(TreeArtifactError, match="root must be a JSON object"):
        read_tree(path)


def test_read_tree_rejects_schema_mismatch(tmp_path: Path):
    """A JSON object that is structurally valid but does not match
    the DocumentTree.from_dict contract must raise TreeArtifactError,
    NOT crash with a bare KeyError. (Bare KeyError would leak
    internal field names to API callers — TreeArtifactError is the
    public contract.)"""
    path = tmp_path / "tree.json"
    # Missing required fields — `pages` is empty, which is legal,
    # but a malformed `block_type` would trip BlockType(value) on
    # any block under "pages". So put a bad block_type in.
    path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_idx": 0,
                        "children": [
                            {
                                "block_type": "not-a-real-block-type",
                                "bbox": [0.0, 0.0, 1.0, 0.1],
                                "text": "x",
                                "page_idx": 0,
                            }
                        ],
                    }
                ],
                "sections": [],
                "tables": [],
                "figures": [],
                "equations": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TreeArtifactError, match="does not match DocumentTree schema"):
        read_tree(path)


def test_round_trip_with_empty_figure_is_correct(tmp_path: Path):
    """FigureNode with image_bytes=None should serialize and
    deserialize without inventing a base64 field."""
    original = DocumentTree(
        figures=[
            FigureNode(
                page_idx=0,
                bbox=[0.0, 0.0, 1.0, 0.1],
                image_bytes=None,
                caption="caption only",
            )
        ],
    )
    path = tmp_path / "tree.json"
    write_tree_atomic(original, path)
    loaded = read_tree(path)
    assert loaded.figures[0].image_bytes is None
    assert loaded.figures[0].caption == "caption only"
    # The JSON on disk should not contain an image_bytes_b64 key.
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "image_bytes_b64" not in raw["figures"][0]
