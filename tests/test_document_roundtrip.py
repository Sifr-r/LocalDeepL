"""Round-trip tests for the DocumentResult IR (R-M4).

Asserts that:

- ``from_pages_data`` → ``to_pages_data`` preserves text and geometry.
- ``to_pages_data`` honours processor-assigned ``reading_order``.
- The rich writer path (``DocumentResultWriter``) delivers the full IR —
  kinds, confidence, metadata — to the output boundary without loss.
- All 6 built-in document processors' metadata survives the pipeline run
  on ``last_document_result``.
"""

from __future__ import annotations

import base64

from omniscribe.core.document import DocumentResult
from omniscribe.core.processors import (
    LayoutEnrichmentProcessor,
    QualityAnalysisProcessor,
    ReadingOrderProcessor,
    SectionAnalysisProcessor,
    StructureAnalysisProcessor,
    TableExtractionProcessor,
)
from omniscribe.core.workflows.base import DocumentResultWriter
from omniscribe.pipeline import OCRPipeline

# ---------------------------------------------------------------------------
# Pure IR round-trip
# ---------------------------------------------------------------------------


def test_from_pages_data_to_pages_data_preserves_text_and_geometry():
    pages = {
        0: [([0.1, 0.2, 0.3, 0.4], "alpha"), ([0.5, 0.6, 0.7, 0.8], "beta")],
        1: [([0.0, 0.0, 0.9, 0.1], "gamma")],
    }
    result = DocumentResult.from_pages_data(pages)
    round_tripped = result.to_pages_data()

    assert round_tripped == pages


def test_to_pages_data_respects_reading_order_annotation():
    """Blocks annotated with reading_order but NOT physically sorted are
    emitted in reading_order order."""
    result = DocumentResult.from_pages_data(
        {0: [([0.1, 0.5, 0.3, 0.6], "second"), ([0.1, 0.1, 0.3, 0.2], "first")]}
    )
    # Annotate out-of-order reading_order without physically sorting.
    result.pages[0].blocks[0].reading_order = 1
    result.pages[0].blocks[1].reading_order = 0

    pages_data = result.to_pages_data()

    assert [text for _, text in pages_data[0]] == ["first", "second"]


def test_to_pages_data_without_reading_order_preserves_list_order():
    result = DocumentResult.from_pages_data(
        {0: [([0.1, 0.5, 0.3, 0.6], "first"), ([0.1, 0.1, 0.3, 0.2], "second")]}
    )
    # Strip reading_order (simulates blocks from a source that doesn't set it).
    for block in result.pages[0].blocks:
        block.reading_order = None

    pages_data = result.to_pages_data()

    assert [text for _, text in pages_data[0]] == ["first", "second"]


# ---------------------------------------------------------------------------
# Rich writer protocol
# ---------------------------------------------------------------------------


class _RichWriter:
    """Captures the DocumentResult delivered via the rich protocol."""

    def __init__(self) -> None:
        self.received: DocumentResult | None = None

    def convert_to_images(self, input_path, dpi=200, max_image_dim=1024):
        return {0: base64.b64encode(b"image").decode()}

    def embed_structured_text(self, input_path, output_path, pages_data, dpi=200):
        raise AssertionError("legacy path should not be called for rich writers")

    def write_document_result(self, input_path, output_path, document_result, dpi=200):
        self.received = document_result


class _Aligner:
    def get_detected_boxes_batch(self, images):
        return [[[0.1, 0.2, 0.3, 0.4]] for _ in images]

    def align_text(self, structured, lines):
        return [(bbox, "\n".join(lines)) for bbox, _ in structured]


class _OCR:
    async def perform_ocr(self, image_base64, **kwargs):
        return ["hello"]


async def test_rich_writer_receives_full_document_result():
    writer = _RichWriter()
    assert isinstance(writer, DocumentResultWriter)

    pipe = OCRPipeline(_Aligner(), _OCR(), writer)
    pages_text = await pipe.run("in.pdf", "out.pdf", refine=False)

    assert pages_text == {0: ["hello"]}
    assert writer.received is not None
    block = writer.received.pages[0].blocks[0]
    assert block.text == "hello"
    assert block.bbox == [0.1, 0.2, 0.3, 0.4]
    assert block.source_processor == "hybrid"
    assert block.reading_order == 0


async def test_rich_writer_receives_processor_metadata():
    """Metadata added by document processors is visible to the rich writer."""
    writer = _RichWriter()
    pipe = OCRPipeline(
        _Aligner(),
        _OCR(),
        writer,
        document_processors=[QualityAnalysisProcessor()],
    )
    await pipe.run("in.pdf", "out.pdf", refine=False)

    assert writer.received is not None
    page = writer.received.pages[0]
    assert "quality" in page.metadata
    assert page.metadata["quality"]["block_count"] == 1


async def test_legacy_callable_writer_still_works():
    """Explicitly injected legacy 4-arg writers keep the old contract."""
    captured: dict = {}

    def legacy_writer(input_path, output_path, pages_data, dpi):
        captured["pages_data"] = pages_data

    class _PDF:
        def convert_to_images(self, input_path, dpi=200, max_image_dim=1024):
            return {0: base64.b64encode(b"image").decode()}

        def embed_structured_text(self, input_path, output_path, pages_data, dpi=200):
            raise AssertionError("should use injected writer, not handler")

    pipe = OCRPipeline(_Aligner(), _OCR(), _PDF(), output_writer=legacy_writer)
    pages_text = await pipe.run("in.pdf", "out.pdf", refine=False)

    assert pages_text == {0: ["hello"]}
    assert captured["pages_data"][0][0][1] == "hello"


# ---------------------------------------------------------------------------
# All 6 processors' metadata survives the pipeline
# ---------------------------------------------------------------------------

_ALL_PROCESSORS = [
    ReadingOrderProcessor(),
    QualityAnalysisProcessor(),
    StructureAnalysisProcessor(),
    SectionAnalysisProcessor(),
    LayoutEnrichmentProcessor(),
    TableExtractionProcessor(),
]


class _MultiBoxAligner:
    """Aligner returning boxes that form a heading, a paragraph, and a
    2×3 cell grid so all six processors have material to work with."""

    BOXES = [
        [0.1, 0.05, 0.6, 0.1],  # heading
        [0.1, 0.15, 0.8, 0.2],  # paragraph
        [0.1, 0.25, 0.2, 0.29],  # table cell: Item
        [0.25, 0.25, 0.35, 0.29],  # table cell: Qty
        [0.4, 0.25, 0.55, 0.29],  # table cell: Price
        [0.1, 0.31, 0.2, 0.35],  # table cell: Widget
        [0.25, 0.31, 0.35, 0.35],  # table cell: 3
        [0.4, 0.31, 0.55, 0.35],  # table cell: 30.00
    ]

    def get_detected_boxes_batch(self, images):
        return [list(self.BOXES) for _ in images]

    def align_text(self, structured, lines):
        texts = [
            "Quarterly Report",
            "Revenue increased 12% year over year.",
            "Item",
            "Qty",
            "Price",
            "Widget",
            "3",
            "30.00",
        ]
        return [(bbox, texts[i]) for i, (bbox, _) in enumerate(structured)]


class _MultiLineOCR:
    async def perform_ocr(self, image_base64, **kwargs):
        return [
            "Quarterly Report",
            "Revenue increased 12% year over year.",
            "Item Qty Price",
            "Widget 3 30.00",
        ]

    async def perform_ocr_on_crop(self, image_base64, **kwargs):
        return "crop text"


async def test_all_processor_metadata_survives_on_last_document_result():
    pipe = OCRPipeline(
        _MultiBoxAligner(),
        _MultiLineOCR(),
        _RichWriter(),
        document_processors=_ALL_PROCESSORS,
    )
    await pipe.run("in.pdf", "out.pdf", refine=False)

    result = pipe.last_document_result
    assert result is not None
    page = result.pages[0]

    # reading_order: blocks sorted and annotated
    assert [b.reading_order for b in page.blocks] == list(range(8))

    # quality_analysis: page-level findings
    assert "quality" in page.metadata
    assert page.metadata["quality"]["block_count"] == 8

    # structure_analysis: block kinds assigned
    assert "structure" in page.metadata
    assert any(b.kind == "heading" for b in page.blocks)

    # section_analysis: heading/body roles
    assert page.blocks[0].metadata["section"]["role"] == "heading"
    assert "sections" in page.metadata

    # layout_enrichment: region annotations
    assert any("region" in b.metadata.get("layout", {}) for b in page.blocks)

    # table_extraction: 2×3 grid detected, cells annotated
    assert page.metadata["tables"]
    table = page.metadata["tables"][0]
    assert table["row_count"] == 2
    assert table["column_count"] == 3
    assert any("table" in b.metadata for b in page.blocks)
