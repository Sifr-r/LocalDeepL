"""Block-tree document IR (Docling/Marker style).

This is a richer alternative to :mod:`local_deepl.core.document` that carries
the structural information (headings, tables, figures, sections, spans) needed
for structured export (DOCX, HTML, block-tree JSON) and structure-preserving
translation.

The legacy :class:`~local_deepl.core.document.DocumentResult` is kept for
backward compatibility; new exporters and translation paths consume
:class:`DocumentTree`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from local_deepl.core.document import DocumentResult


class BlockType(StrEnum):
    TEXT = "text"
    PARAGRAPH = "paragraph"
    SECTION_HEADER = "section_header"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    EQUATION = "equation"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    PAGE_NUMBER = "page_number"
    FOOTNOTE = "footnote"
    CODE = "code"
    KEY_VALUE = "key_value"


_BBox = list[float]


def _new_block_id() -> str:
    """Generate a stable, sortable block id."""
    return uuid.uuid4().hex[:16]


@dataclass(slots=True)
class Span:
    """An inline run inside a block (bold, italic, font)."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bold": self.bold,
            "italic": self.italic,
            "code": self.code,
        }


@dataclass(slots=True)
class BlockNode:
    """A single block in the document tree.

    The ``block_id`` is stable across the pipeline and is what the UI binds to
    when rendering the bbox overlay. ``children`` are populated for tables
    (cell nodes), lists (item nodes), and nested sections.
    """

    block_type: BlockType
    bbox: _BBox
    text: str
    page_idx: int
    block_id: str = field(default_factory=_new_block_id)
    confidence: float | None = None
    children: list[BlockNode] = field(default_factory=list)
    parent_id: str | None = None
    level: int = 0  # heading level (1..6) for SECTION_HEADER; list depth for LIST_ITEM
    section_hierarchy: list[str] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "block_id": self.block_id,
            "block_type": self.block_type.value,
            "bbox": list(self.bbox),
            "text": self.text,
            "page_idx": self.page_idx,
            "confidence": self.confidence,
            "level": self.level,
            "section_hierarchy": list(self.section_hierarchy),
            "spans": [s.to_dict() for s in self.spans],
            "metadata": dict(self.metadata),
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass(slots=True)
class PageTree:
    page_idx: int
    width: int | None = None
    height: int | None = None
    children: list[BlockNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_idx": self.page_idx,
            "width": self.width,
            "height": self.height,
            "children": [c.to_dict() for c in self.children],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Section:
    """A cross-page section entry in the document outline."""

    title: str
    level: int
    start_page: int
    children: list[Section] = field(default_factory=list)
    block_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "start_page": self.start_page,
            "block_id": self.block_id,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass(slots=True)
class TableNode:
    rows: int
    cols: int
    page_idx: int
    bbox: _BBox
    cells: list[list[BlockNode]] = field(default_factory=list)
    block_id: str = field(default_factory=_new_block_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_type": "table",
            "rows": self.rows,
            "cols": self.cols,
            "page_idx": self.page_idx,
            "bbox": list(self.bbox),
            "cells": [[c.to_dict() for c in row] for row in self.cells],
        }


@dataclass(slots=True)
class FigureNode:
    page_idx: int
    bbox: _BBox
    image_bytes: bytes | None = None
    caption: str = ""
    block_id: str = field(default_factory=_new_block_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_type": "figure",
            "page_idx": self.page_idx,
            "bbox": list(self.bbox),
            "has_image": self.image_bytes is not None,
            "caption": self.caption,
        }


@dataclass(slots=True)
class EquationNode:
    page_idx: int
    bbox: _BBox
    latex: str
    block_id: str = field(default_factory=_new_block_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_type": "equation",
            "page_idx": self.page_idx,
            "bbox": list(self.bbox),
            "latex": self.latex,
        }


@dataclass(slots=True)
class DocumentTree:
    """The canonical rich IR for structured export and structure-preserving translation."""

    pages: list[PageTree] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: list[TableNode] = field(default_factory=list)
    figures: list[FigureNode] = field(default_factory=list)
    equations: list[EquationNode] = field(default_factory=list)
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages": [p.to_dict() for p in self.pages],
            "sections": [s.to_dict() for s in self.sections],
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "equations": [e.to_dict() for e in self.equations],
            "source_path": self.source_path,
            "metadata": dict(self.metadata),
        }

    def iter_text_blocks(self) -> list[BlockNode]:
        """Yield every leaf text block in reading order."""
        out: list[BlockNode] = []
        for page in self.pages:
            for child in page.children:
                out.extend(_walk_text(child))
        return out


def _walk_text(node: BlockNode) -> list[BlockNode]:
    if node.block_type == BlockType.TABLE:
        # table cells are walked separately
        return []
    if node.children and node.block_type not in (BlockType.LIST_ITEM,):
        # nested blocks (e.g. a section header followed by paragraphs) — walk children
        out: list[BlockNode] = []
        for c in node.children:
            out.extend(_walk_text(c))
        if out:
            return out
    return [node]


def from_pages_data(
    pages_data: dict[int, Sequence[tuple[Sequence[float], str]]],
    *,
    source_path: str | None = None,
) -> DocumentTree:
    """Best-effort conversion from the legacy {page: [(bbox, text)]} shape.

    Each line becomes a :class:`BlockNode` of type :attr:`BlockType.PARAGRAPH`
    (or :attr:`BlockType.SECTION_HEADER` for short, uppercase-heavy lines).
    """
    tree = DocumentTree(source_path=source_path)
    for page_idx in sorted(pages_data):
        page = PageTree(page_idx=page_idx)
        for bbox, text in pages_data[page_idx]:
            text = (text or "").strip()
            if not text:
                continue
            kind = _classify_simple(text)
            page.children.append(
                BlockNode(
                    block_type=kind,
                    bbox=[float(v) for v in bbox],
                    text=text,
                    page_idx=page_idx,
                    level=1 if kind == BlockType.SECTION_HEADER else 0,
                )
            )
        tree.pages.append(page)
    return tree


def from_document_result(document: "DocumentResult") -> DocumentTree:
    """Initialize a DocumentTree from a DocumentResult."""
    tree = DocumentTree(source_path=document.source_path, metadata=dict(document.metadata) if hasattr(document, 'metadata') else {})
    for page in document.pages:
        tree_page = PageTree(
            page_idx=page.page_index,
            width=page.width,
            height=page.height,
            metadata=dict(page.metadata)
        )
        for block in page.blocks:
            # Prefer 'label' from metadata (Grounded path), then 'kind'
            kind_str = block.metadata.get("label") or (block.kind if isinstance(block.kind, str) else "paragraph")
            
            if kind_str in ("image", "figure"):
                fig_node = FigureNode(
                    page_idx=page.page_index,
                    bbox=list(block.bbox),
                    image_bytes=block.metadata.get("image_bytes"),
                    caption=block.text,
                )
                tree.figures.append(fig_node)
                # Keep a BlockNode in the page children too, just mark it as figure
                node = BlockNode(
                    block_type=BlockType.FIGURE,
                    bbox=list(block.bbox),
                    text=block.text,
                    page_idx=page.page_index,
                    confidence=block.confidence,
                    metadata=dict(block.metadata)
                )
                node.image_bytes = fig_node.image_bytes # For html_writer compatibility
                tree_page.children.append(node)
                continue

            try:
                block_type = BlockType(kind_str)
            except ValueError:
                block_type = BlockType.PARAGRAPH
            
            node = BlockNode(
                block_type=block_type,
                bbox=list(block.bbox),
                text=block.text,
                page_idx=page.page_index,
                confidence=block.confidence,
                metadata=dict(block.metadata)
            )
            tree_page.children.append(node)
        tree.pages.append(tree_page)
    return tree


def _classify_simple(text: str) -> BlockType:
    """Cheap classifier used when richer processor data is unavailable."""
    if len(text) <= 80:
        upper = sum(1 for c in text if c.isalpha() and c.isupper())
        alpha = sum(1 for c in text if c.isalpha())
        if alpha > 0 and upper / alpha >= 0.65:
            return BlockType.SECTION_HEADER
    return BlockType.PARAGRAPH
