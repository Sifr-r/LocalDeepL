"""Structure analysis processor for identifying block roles (headings, lists, key-value)."""

from __future__ import annotations

import re
from collections import Counter

from omniscribe.core.block_tree import BlockNode, BlockType
from omniscribe.core.document import DocumentBlock, DocumentResult
from omniscribe.core.processors.base import ProcessorContract

# Module-level regexes used by the structure heuristics below. They used
# to live in ``processors/base.py`` because they're shared with the
# ``section`` and ``table`` processors; moved here to colocate them with
# the processor that defines their semantics.
_KEY_VALUE_RE = re.compile(r"^\s*([^:\n]{1,50}):\s*(\S.+)$")
_LIST_ITEM_RE = re.compile(
    r"^\s*(?:[-*\u2022\u25e6\u2013\u2014]|\(?\d+[\).]|\(?[A-Za-z][\).])\s+"
)
_TABLE_SPLIT_RE = re.compile(r"\t+|\|+|\s{2,}")


class StructureAnalysisProcessor:
    """Attach deterministic block structure hints for local document intelligence."""

    name = "structure_analysis"
    contract = ProcessorContract.ANNOTATE_ONLY

    def __init__(
        self,
        heading_max_chars: int = 90,
        heading_max_words: int = 12,
        table_min_columns: int = 3,
    ) -> None:
        if heading_max_chars < 1:
            raise ValueError("heading_max_chars must be positive")
        if heading_max_words < 1:
            raise ValueError("heading_max_words must be positive")
        if table_min_columns < 2:
            raise ValueError("table_min_columns must be at least 2")
        self.heading_max_chars = heading_max_chars
        self.heading_max_words = heading_max_words
        self.table_min_columns = table_min_columns

    async def process(self, document: DocumentResult) -> DocumentResult:
        tree = document.tree
        for page_idx, page in enumerate(document.pages):
            counts: Counter[str] = Counter()
            tree_page = tree.pages[page_idx] if tree else None

            for block_idx, block in enumerate(page.blocks):
                kind, confidence, signals = self._classify(block)
                block.kind = kind
                block.metadata["structure"] = {
                    "kind": kind,
                    "confidence": confidence,
                    "signals": signals,
                }
                counts[kind] += 1

                if tree_page and block_idx < len(tree_page.children):
                    node = tree_page.children[block_idx]
                    if isinstance(node, BlockNode):
                        if kind == "heading":
                            node.block_type = BlockType.SECTION_HEADER
                            node.level = 1
                        elif kind == "list_item":
                            node.block_type = BlockType.LIST_ITEM
                        elif kind == "key_value":
                            node.block_type = BlockType.KEY_VALUE
                        elif kind == "table_candidate":
                            # Table processor will properly replace it later
                            node.block_type = BlockType.PARAGRAPH
                        else:
                            node.block_type = BlockType.PARAGRAPH

            page.metadata["structure"] = {
                "block_kinds": dict(sorted(counts.items())),
                "has_key_values": counts["key_value"] > 0,
                "has_tables": counts["table_candidate"] > 0,
            }
        return document

    def _classify(self, block: DocumentBlock) -> tuple[str, float, list[str]]:
        text = block.text.strip()
        if not text:
            return "empty", 1.0, ["blank_text"]

        if _LIST_ITEM_RE.match(text):
            return "list_item", 0.86, ["list_marker"]

        key_value = _KEY_VALUE_RE.match(text)
        if key_value and len(key_value.group(1).strip().split()) <= 6:
            return "key_value", 0.84, ["colon_key_value"]

        columns = [part.strip() for part in _TABLE_SPLIT_RE.split(text) if part.strip()]
        if len(columns) >= self.table_min_columns:
            return "table_candidate", 0.76, ["column_separators"]

        words = text.split()
        if self._looks_like_heading(text, words):
            return "heading", 0.68, ["short_prominent_text"]

        return "paragraph", 0.55, ["default_text"]

    def _looks_like_heading(self, text: str, words: list[str]) -> bool:
        if "\n" in text or len(text) > self.heading_max_chars:
            return False
        if len(words) > self.heading_max_words:
            return False
        if text.endswith((".", ",", ";", ":")):
            return False

        letters = [char for char in text if char.isalpha()]
        if not letters:
            return False
        uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
        title_words = sum(word[:1].isupper() for word in words if word[:1].isalpha())
        return uppercase_ratio >= 0.65 or title_words >= max(1, len(words) // 2)
