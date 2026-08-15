"""Reading order processor for assigning row-major order."""

from __future__ import annotations

from omniscribe.core.document import DocumentBlock, DocumentResult
from omniscribe.core.processors.base import ProcessorContract


class ReadingOrderProcessor:
    """Assign deterministic row-major order using normalized bbox positions.

    Warning:
        This mutates each page's block list in place. The row bucketing assumes
        bboxes remain normalized in ``0..1``; pixel coordinates would collapse
        unrelated rows into unstable groups.
    """

    name = "reading_order"
    contract = ProcessorContract.MAY_REORDER

    def __init__(self, row_tolerance: float = 0.02) -> None:
        if row_tolerance <= 0:
            raise ValueError("row_tolerance must be positive")
        self.row_tolerance = row_tolerance

    async def process(self, document: DocumentResult) -> DocumentResult:
        for page in document.pages:
            page.blocks.sort(key=self._sort_key)
            for index, block in enumerate(page.blocks):
                block.reading_order = index
        if document.tree is not None:
            from omniscribe.core.block_tree import from_document_result

            document.tree = from_document_result(document)
        return document

    def _sort_key(self, block: DocumentBlock) -> tuple[int, float, float]:
        x0, y0, _, _ = block.bbox
        return (round(y0 / self.row_tolerance), x0, y0)
