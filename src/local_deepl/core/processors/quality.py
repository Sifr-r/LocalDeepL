"""Quality analysis processor for page quality metadata."""

from __future__ import annotations

from local_deepl.core.document import DocumentResult
from local_deepl.core.processors.base import ProcessorContract, _bbox_area


class QualityAnalysisProcessor:
    """Attach lightweight page quality findings without rejecting the document.

    Findings are advisory metadata for UI/export decisions. They deliberately do
    not raise on sparse text or blank boxes because OCR can still produce a
    useful searchable PDF for partially readable scans.
    """

    name = "quality_analysis"
    contract = ProcessorContract.ANNOTATE_ONLY

    def __init__(
        self,
        empty_block_area_threshold: float = 0.05,
        sparse_block_threshold: int = 20,
        min_chars_per_block: float = 2.0,
    ) -> None:
        if not 0 < empty_block_area_threshold <= 1:
            raise ValueError("empty_block_area_threshold must be in (0, 1]")
        if sparse_block_threshold < 1:
            raise ValueError("sparse_block_threshold must be positive")
        if min_chars_per_block < 0:
            raise ValueError("min_chars_per_block must be non-negative")
        self.empty_block_area_threshold = empty_block_area_threshold
        self.sparse_block_threshold = sparse_block_threshold
        self.min_chars_per_block = min_chars_per_block

    async def process(self, document: DocumentResult) -> DocumentResult:
        for page in document.pages:
            block_count = len(page.blocks)
            text_char_count = sum(len(block.text.strip()) for block in page.blocks)
            bbox_area = sum(_bbox_area(block.bbox) for block in page.blocks)
            chars_per_block = text_char_count / block_count if block_count else 0.0
            findings: list[dict[str, object]] = []
            if text_char_count == 0:
                findings.append({"code": "empty_page", "severity": "warning"})
            if (
                block_count >= self.sparse_block_threshold
                and chars_per_block < self.min_chars_per_block
            ):
                findings.append({"code": "sparse_text", "severity": "warning"})
            for index, block in enumerate(page.blocks):
                area = _bbox_area(block.bbox)
                if not block.text.strip() and area >= self.empty_block_area_threshold:
                    findings.append(
                        {
                            "code": "empty_large_block",
                            "severity": "warning",
                            "block_index": index,
                        }
                    )
            page.metadata["quality"] = {
                "block_count": block_count,
                "text_char_count": text_char_count,
                "text_density": text_char_count / bbox_area if bbox_area else 0.0,
                "findings": findings,
            }
        return document
