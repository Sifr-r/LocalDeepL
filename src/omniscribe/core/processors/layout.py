"""Layout enrichment processor for labeling headers, footers, figures, and captions."""

from __future__ import annotations

from collections import Counter

from omniscribe.core.block_tree import BlockType
from omniscribe.core.document import DocumentBlock, DocumentResult
from omniscribe.core.processors.base import (
    ProcessorContract,
    _bbox_area,
    _normalize_space,
    _page_region,
    _structure_kind,
)


class LayoutEnrichmentProcessor:
    """Attach local page-region and document-layout labels to blocks."""

    name = "layout_enrichment"
    contract = ProcessorContract.ANNOTATE_ONLY

    async def process(self, document: DocumentResult) -> DocumentResult:
        tree = document.tree
        for page_idx, page in enumerate(document.pages):
            counts: Counter[str] = Counter()
            tree_page = tree.pages[page_idx] if tree else None

            for block_idx, block in enumerate(page.blocks):
                role, region, confidence, signals = self._classify(block)
                block.metadata["layout"] = {
                    "role": role,
                    "region": region,
                    "confidence": confidence,
                    "signals": signals,
                }
                counts[role] += 1

                if tree_page and block_idx < len(tree_page.children):
                    node = tree_page.children[block_idx]
                    if role == "header":
                        node.block_type = BlockType.PAGE_HEADER
                    elif role == "footer":
                        node.block_type = BlockType.PAGE_FOOTER
                    elif role == "page_number":
                        node.block_type = BlockType.PAGE_NUMBER
                    elif role == "figure":
                        node.block_type = BlockType.FIGURE
                    elif role == "caption":
                        node.block_type = BlockType.CAPTION

            page.metadata["layout"] = {
                "roles": dict(sorted(counts.items())),
                "has_figures": counts["figure"] > 0,
                "has_captions": counts["caption"] > 0,
                "has_headers": counts["header"] > 0,
                "has_footers": counts["footer"] > 0,
            }
        return document

    def _classify(self, block: DocumentBlock) -> tuple[str, str, float, list[str]]:
        text = _normalize_space(block.text)
        lower = text.lower()
        x0, y0, x1, _y1 = block.bbox
        region = _page_region(block.bbox)
        kind = _structure_kind(block)
        signals: list[str] = [f"region:{region}"]

        if region == "header" and text and len(text) <= 120:
            return "header", region, 0.72, [*signals, "top_short_text"]
        if region == "footer":
            if text.isdecimal() or lower.startswith(("page ", "p. ")):
                return "page_number", region, 0.82, [*signals, "footer_page_number"]
            if text and len(text) <= 140:
                return "footer", region, 0.7, [*signals, "bottom_short_text"]
        if lower.startswith(("figure ", "fig. ", "table ", "caption:")):
            return "caption", region, 0.82, [*signals, "caption_prefix"]
        if kind == "heading" and y0 < 0.28:
            return "title_block", region, 0.76, [*signals, "early_heading"]
        if not text and _bbox_area(block.bbox) >= 0.08:
            return "figure", region, 0.58, [*signals, "large_empty_region"]

        width = x1 - x0
        if width < 0.32:
            region = f"{region}_side"
            signals.append("narrow_column")
        return "body", region, 0.5, signals
