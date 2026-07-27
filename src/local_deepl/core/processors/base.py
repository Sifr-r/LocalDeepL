"""DocumentResult processor interfaces and registry.

Processors run after OCR/refinement/spellcheck and before output embedding.
They receive the mutable normalized document graph, so changes to block text,
order, and metadata are visible to later processors and to export surfaces that
read ``OCRPipeline.last_document_result``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from local_deepl.core.document import DocumentBlock, DocumentResult

LOCAL_DOCUMENT_PROCESSOR_NAMES = (
    "reading_order",
    "quality_analysis",
    "structure_analysis",
    "section_analysis",
    "layout_enrichment",
    "table_extraction",
)

_KEY_VALUE_RE = re.compile(r"^\s*([^:\n]{1,50}):\s*(\S.+)$")
_LIST_ITEM_RE = re.compile(
    r"^\s*(?:[-*\u2022\u25e6\u2013\u2014]|\(?\d+[\).]|\(?[A-Za-z][\).])\s+"
)
_TABLE_SPLIT_RE = re.compile(r"\t+|\|+|\s{2,}")


class DocumentProcessor(Protocol):
    """Async transform contract for in-memory document handoff stages."""

    name: str

    async def process(self, document: DocumentResult) -> DocumentResult: ...


DocumentProcessorFactory = Callable[[], DocumentProcessor]


class DocumentProcessorRegistry:
    """Name-to-factory registry used by callers that expose processor choices.

    Factories should return fresh processor instances; processors may keep
    per-run state and the pipeline executes them sequentially.
    """

    def __init__(self) -> None:
        self._factories: dict[str, DocumentProcessorFactory] = {}

    @property
    def names(self) -> list[str]:
        return sorted(self._factories)

    def register(self, name: str, factory: DocumentProcessorFactory) -> None:
        key = name.strip()
        if not key:
            raise ValueError("Document processor name cannot be empty")
        if key in self._factories:
            raise ValueError(f"Document processor already registered: {key}")
        self._factories[key] = factory

    def create(self, name: str) -> DocumentProcessor:
        try:
            return self._factories[name]()
        except KeyError:
            raise KeyError(f"Unknown document processor: {name}") from None

    def create_many(self, names: Sequence[str]) -> list[DocumentProcessor]:
        return [self.create(name) for name in names]


def build_document_processors(names: Iterable[str]) -> tuple[DocumentProcessor, ...]:
    """Instantiate known local document processors by user-facing name."""
    from local_deepl.core.processors.layout import LayoutEnrichmentProcessor
    from local_deepl.core.processors.quality import QualityAnalysisProcessor
    from local_deepl.core.processors.reading_order import ReadingOrderProcessor
    from local_deepl.core.processors.section import SectionAnalysisProcessor
    from local_deepl.core.processors.structure import StructureAnalysisProcessor
    from local_deepl.core.processors.table import TableExtractionProcessor

    registry = DocumentProcessorRegistry()
    registry.register("reading_order", ReadingOrderProcessor)
    registry.register("quality_analysis", QualityAnalysisProcessor)
    registry.register("structure_analysis", StructureAnalysisProcessor)
    registry.register("section_analysis", SectionAnalysisProcessor)
    registry.register("layout_enrichment", LayoutEnrichmentProcessor)
    registry.register("table_extraction", TableExtractionProcessor)
    return tuple(registry.create(name) for name in names)


def _structure_kind(block: DocumentBlock) -> str:
    structure = block.metadata.get("structure")
    if isinstance(structure, dict):
        kind = structure.get("kind")
        if isinstance(kind, str):
            return kind
    return block.kind


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _page_region(bbox: Sequence[float]) -> str:
    _x0, y0, _x1, y1 = bbox
    if y1 <= 0.16:
        return "header"
    if y0 >= 0.84:
        return "footer"
    return "body"


def _bbox_area(bbox: Sequence[float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


async def run_document_processors(
    document: DocumentResult, processors: Sequence[DocumentProcessor]
) -> DocumentResult:
    """Run processors in order, passing each mutation to the next stage."""

    if document.tree is None:
        from local_deepl.core.block_tree import from_document_result

        document.tree = from_document_result(document)

    result = document
    for processor in processors:
        result = await processor.process(result)
    return result
