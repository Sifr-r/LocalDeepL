"""Section analysis processor for grouping blocks under headings."""

from __future__ import annotations

from omniscribe.core.block_tree import BlockNode, Section
from omniscribe.core.document import DocumentBlock, DocumentResult
from omniscribe.core.processors.base import (
    _KEY_VALUE_RE,
    _LIST_ITEM_RE,
    _TABLE_SPLIT_RE,
    ProcessorContract,
    _normalize_space,
    _structure_kind,
)


class SectionAnalysisProcessor:
    """Group blocks under locally detected section headings."""

    name = "section_analysis"
    contract = ProcessorContract.ANNOTATE_ONLY

    def __init__(
        self, heading_max_chars: int = 120, heading_max_words: int = 14
    ) -> None:
        if heading_max_chars < 1:
            raise ValueError("heading_max_chars must be positive")
        if heading_max_words < 1:
            raise ValueError("heading_max_words must be positive")
        self.heading_max_chars = heading_max_chars
        self.heading_max_words = heading_max_words

    async def process(self, document: DocumentResult) -> DocumentResult:
        current_section: dict[str, object] | None = None
        current_tree_section: Section | None = None
        section_index = -1
        tree = document.tree

        for page_idx, page in enumerate(document.pages):
            page_headings: list[dict[str, object]] = []
            tree_page = tree.pages[page_idx] if tree else None

            for block_index, block in enumerate(page.blocks):
                node = (
                    tree_page.children[block_index]
                    if tree_page and block_index < len(tree_page.children)
                    else None
                )

                if self._is_heading(block):
                    section_index += 1
                    title = _normalize_space(block.text)
                    current_section = {
                        "section_index": section_index,
                        "title": title,
                        "heading_page_index": page.page_index,
                        "heading_block_index": block_index,
                    }
                    page_headings.append(dict(current_section))
                    block.metadata["section"] = {
                        **current_section,
                        "role": "heading",
                    }

                    if tree and node and isinstance(node, BlockNode):
                        current_tree_section = Section(
                            title=title,
                            level=1,
                            start_page=page.page_index,
                            block_id=node.block_id,
                        )
                        tree.sections.append(current_tree_section)
                        node.parent_id = current_tree_section.block_id
                        node.section_hierarchy = [title]
                    continue

                if current_section is None:
                    block.metadata["section"] = {
                        "section_index": None,
                        "title": None,
                        "heading_page_index": None,
                        "heading_block_index": None,
                        "role": "unsectioned",
                    }
                else:
                    block.metadata["section"] = {
                        **current_section,
                        "role": "body",
                    }
                    if node and current_tree_section and isinstance(node, BlockNode):
                        node.parent_id = current_tree_section.block_id
                        node.section_hierarchy = [current_tree_section.title]

            page.metadata["sections"] = {
                "headings": page_headings,
                "section_count": len(page_headings),
                "active_section": current_section["title"]
                if current_section is not None
                else None,
            }

        return document

    def _is_heading(self, block: DocumentBlock) -> bool:
        kind = _structure_kind(block)
        if kind == "heading":
            return True
        if kind not in {"text", "paragraph"}:
            return False

        text = block.text.strip()
        if not text or "\n" in text:
            return False
        if len(text) > self.heading_max_chars:
            return False
        words = text.split()
        if len(words) > self.heading_max_words:
            return False
        if text.endswith((".", ",", ";", ":")):
            return False
        if _LIST_ITEM_RE.match(text) or _KEY_VALUE_RE.match(text):
            return False
        columns = [part.strip() for part in _TABLE_SPLIT_RE.split(text) if part.strip()]
        if len(columns) >= 3:
            return False

        letters = [char for char in text if char.isalpha()]
        if not letters:
            return False
        uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
        title_words = sum(word[:1].isupper() for word in words if word[:1].isalpha())
        return uppercase_ratio >= 0.65 or title_words >= max(1, len(words) // 2)
