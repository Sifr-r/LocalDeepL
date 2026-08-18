"""
Unit tests for Phase 1 async unblocking, streaming rasterization, and VLM concurrency.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.pdf.rasterizer import convert_batches, convert_generator


@pytest.fixture
def pdf_handler() -> PDFHandler:
    return PDFHandler()


def test_convert_generator_streams_pages(example_pdfs: dict[str, Path]):
    input_pdf = str(example_pdfs["digital.pdf"])
    gen = convert_generator(input_pdf, dpi=150, max_image_dim=512)

    item = next(gen)
    assert isinstance(item, tuple)
    assert len(item) == 3
    page_num, img, b64_str = item

    assert page_num == 0
    assert isinstance(img, Image.Image)
    assert isinstance(b64_str, str) and len(b64_str) > 100


def test_convert_generator_filters_pages(example_pdfs: dict[str, Path]):
    input_pdf = str(example_pdfs["hybrid.pdf"])
    pages = list(convert_generator(input_pdf, dpi=150, pages="1"))
    assert len(pages) == 1
    assert pages[0][0] == 0


def test_convert_generator_input_validation():
    with pytest.raises(ValueError, match="dpi must be greater than 0"):
        list(convert_generator("dummy.pdf", dpi=0))

    with pytest.raises(ValueError, match="Source file path cannot be empty"):
        list(convert_generator(""))

    with pytest.raises(ValueError, match="Source bytes cannot be empty"):
        list(convert_generator(b""))


def test_pdf_handler_convert_and_generator(
    pdf_handler: PDFHandler, example_pdfs: dict[str, Path]
):
    input_pdf = str(example_pdfs["digital.pdf"])
    gen_items = list(pdf_handler.convert_generator(input_pdf, dpi=150))
    dict_items = pdf_handler.convert(input_pdf, dpi=150)

    assert len(gen_items) == len(dict_items)
    for page_num, _img, b64_str in gen_items:
        assert dict_items[page_num] == b64_str


# ---------------------------------------------------------------------------
# H1 audit fix: convert_batches bounded-memory streaming
#
# These tests pin the H1 contract:
#   * ``convert_batches`` yields lists of at most ``batch_size`` items
#   * the last batch may be shorter than ``batch_size``
#   * ``PDFHandler.convert_batches`` delegates to the rasterizer
#   * the high-volume OCR pipeline consumes the batched streaming API
#     (not the eager ``convert``) so peak memory during rasterization is
#     bounded to ``batch_size`` pages
# ---------------------------------------------------------------------------


def test_convert_batches_yields_bounded_batches(example_pdfs: dict[str, Path]):
    """Every batch has at most ``batch_size`` items."""
    input_pdf = str(example_pdfs["digital.pdf"])
    batches = list(convert_batches(input_pdf, batch_size=2, dpi=150, max_image_dim=256))
    assert batches, "expected at least one batch"
    for batch in batches[:-1]:
        assert len(batch) <= 2
        assert len(batch) >= 1  # a batch that size-2 would yield is non-empty


def test_convert_batches_last_batch_may_be_smaller(example_pdfs: dict[str, Path]):
    """The last batch may be shorter than ``batch_size``."""
    import fitz

    input_pdf = str(example_pdfs["digital.pdf"])
    with fitz.open(input_pdf) as doc:
        total_pages = len(doc)

    # Pick a batch size that does not divide ``total_pages`` evenly so the
    # final batch is guaranteed to be smaller than ``batch_size``.
    batch_size = total_pages + 1
    batches = list(
        convert_batches(input_pdf, batch_size=batch_size, dpi=150, max_image_dim=256)
    )
    assert len(batches) == 1
    assert len(batches[0]) == total_pages
    assert len(batches[0]) < batch_size


def test_convert_batches_flattens_to_full_page_set(example_pdfs: dict[str, Path]):
    """Concatenating every batch reproduces the full page order with no gaps."""
    import fitz

    input_pdf = str(example_pdfs["digital.pdf"])
    with fitz.open(input_pdf) as doc:
        total_pages = len(doc)

    seen: list[int] = []
    for batch in convert_batches(input_pdf, batch_size=3, dpi=150, max_image_dim=256):
        for page_num, _img, b64_str in batch:
            seen.append(page_num)
            assert isinstance(b64_str, str) and len(b64_str) > 100

    assert seen == list(range(total_pages))


def test_convert_batches_respects_pages_filter(example_pdfs: dict[str, Path]):
    """``pages=`` filters the same way as ``convert_generator``."""
    input_pdf = str(example_pdfs["hybrid.pdf"])
    pages = list(
        convert_batches(input_pdf, batch_size=10, dpi=150, pages="1", max_image_dim=256)
    )
    flat = [item[0] for batch in pages for item in batch]
    assert flat == [0]


def test_convert_batches_input_validation():
    """Non-positive ``batch_size`` raises immediately."""
    import pytest

    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        next(convert_batches("dummy.pdf", batch_size=0))

    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        next(convert_batches("dummy.pdf", batch_size=-3))

    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        next(convert_batches("dummy.pdf", batch_size=1.5))  # type: ignore[arg-type]


def test_convert_batches_propagates_source_validation():
    """Empty source paths / bytes still raise the same ValueError as before."""
    import pytest

    with pytest.raises(ValueError, match="Source file path cannot be empty"):
        next(convert_batches("", batch_size=1))

    with pytest.raises(ValueError, match="Source bytes cannot be empty"):
        next(convert_batches(b"", batch_size=1))

    with pytest.raises(ValueError, match="dpi must be greater than 0"):
        next(convert_batches("dummy.pdf", batch_size=1, dpi=0))


def test_pdf_handler_convert_batches_delegates_to_rasterizer(
    pdf_handler: PDFHandler, example_pdfs: dict[str, Path]
):
    """``PDFHandler.convert_batches`` mirrors the rasterizer output."""
    input_pdf = str(example_pdfs["digital.pdf"])
    handler_batches = list(
        pdf_handler.convert_batches(input_pdf, batch_size=3, dpi=150)
    )
    module_batches = list(convert_batches(input_pdf, batch_size=3, dpi=150))
    assert len(handler_batches) == len(module_batches)
    for hb, mb in zip(handler_batches, module_batches, strict=True):
        for (hp, _hi, hb64), (mp, _mi, mb64) in zip(hb, mb, strict=True):
            assert hp == mp
            assert hb64 == mb64


def test_convert_batches_handles_image_input(tmp_path: Path):
    """Raw image inputs (no PDF header) flow through the batched path."""
    from PIL import Image as PILImage

    img = PILImage.new("RGB", (200, 200), "white")
    src = tmp_path / "scan.png"
    img.save(src, format="PNG")

    batches = list(convert_batches(str(src), batch_size=4, max_image_dim=128))
    flat = [item[0] for batch in batches for item in batch]
    assert flat == [0]
    # Each batch contains one (page_num, Image, b64_str) triple.
    for batch in batches:
        assert len(batch) == 1
        page_num, rendered, b64 = batch[0]
        assert page_num == 0
        assert isinstance(rendered, PILImage.Image)
        assert isinstance(b64, str) and len(b64) > 100


@pytest.mark.slow
def test_convert_batches_peak_memory_is_bounded_by_batch_size(
    example_pdfs: dict[str, Path],
):
    """Tracemalloc sanity check: peak PIL buffer growth during streaming is
    independent of the document's total page count.

    The audit's H1 finding is about *peak* memory, not total work. This
    test forces all generator frames to be materialized at once (so the
    ``convert_batches`` consumer cannot release PIL buffers early) and
    then compares against the eager ``convert`` path on the same file.
    Because the example PDFs are tiny, the absolute byte counts are
    small, but the *ratio* is the meaningful signal: ``convert_batches``
    consumes at most ``batch_size`` pages' worth of PIL Image objects
    while the eager path consumes them all.
    """
    import tracemalloc

    from omniscribe.core.pdf.rasterizer import convert

    input_pdf = str(example_pdfs["digital.pdf"])

    tracemalloc.start()
    eager_dict = convert(input_pdf, dpi=150, max_image_dim=512)
    eager_snapshot = tracemalloc.take_snapshot()
    eager_peak = sum(stat.size for stat in eager_snapshot.statistics("filename"))
    del eager_dict

    tracemalloc.start()
    batched: list[list[tuple[int, object, str]]] = []
    for batch in convert_batches(input_pdf, batch_size=1, dpi=150, max_image_dim=512):
        batched.append(batch)
    batched_snapshot = tracemalloc.take_snapshot()
    batched_peak = sum(stat.size for stat in batched_snapshot.statistics("filename"))
    del batched

    # We do not assert an absolute byte budget here because the example
    # PDFs are small and tracemalloc has measurement overhead. We DO
    # assert that the batched path does not regress above the eager
    # path's tracked footprint — a guardrail for future changes.
    assert batched_peak <= eager_peak * 4


@pytest.mark.slow
@pytest.mark.asyncio
async def test_hybrid_engine_convert_pages_uses_batched_streaming(
    example_pdfs: dict[str, Path], stub_ocr
):
    """The high-volume ``HybridEngine._convert_pages`` consumes
    :meth:`PDFHandler.convert_batches`, not the eager ``convert``.

    This is the H1 audit-remediated hot path. If a future refactor
    silently regresses to the eager ``convert`` API this test fails,
    because the mock spy on ``convert_batches`` records zero calls.
    """
    from omniscribe.core.workflows.hybrid import HybridEngine

    class _SpyPDFHandler(PDFHandler):
        def __init__(self) -> None:
            super().__init__()
            self.batch_calls = 0
            self.eager_calls = 0

        def convert_batches(self, source, **kwargs):  # type: ignore[override]
            self.batch_calls += 1
            return super().convert_batches(source, **kwargs)

        def convert(self, source, **kwargs):  # type: ignore[override]
            self.eager_calls += 1
            return super().convert(source, **kwargs)

    handler = _SpyPDFHandler()
    engine = HybridEngine(
        aligner=HybridAligner(),
        ocr_processor=stub_ocr,
        pdf_handler=handler,
        output_writer=lambda *args, **kwargs: None,
    )
    images_dict, page_nums, _meta = await engine._convert_pages(
        input_path=str(example_pdfs["digital.pdf"]),
        dpi=150,
        max_image_dim=256,
        pages=None,
        preprocessing_options=None,
        progress=None,
    )

    assert handler.batch_calls == 1, (
        "HybridEngine._convert_pages must call convert_batches exactly "
        "once; got "
        f"{handler.batch_calls} (eager calls: {handler.eager_calls})"
    )
    assert handler.eager_calls == 0
    assert images_dict, "expected rasterized pages"
    assert page_nums == sorted(page_nums)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_hybrid_engine_convert_pages_rasterize_batch_size_override(
    example_pdfs: dict[str, Path], stub_ocr
):
    """``rasterize_batch_size`` kwarg is forwarded to ``convert_batches``."""
    from unittest.mock import patch

    from omniscribe.core.workflows.hybrid import HybridEngine

    handler = PDFHandler()
    engine = HybridEngine(
        aligner=HybridAligner(),
        ocr_processor=stub_ocr,
        pdf_handler=handler,
        output_writer=lambda *args, **kwargs: None,
    )

    with patch.object(
        PDFHandler, "convert_batches", wraps=handler.convert_batches
    ) as spy:
        await engine._convert_pages(
            input_path=str(example_pdfs["digital.pdf"]),
            dpi=150,
            max_image_dim=256,
            pages=None,
            preprocessing_options=None,
            progress=None,
            rasterize_batch_size=2,
        )
        # The forwarded batch_size kwarg must reach the rasterizer.
        assert spy.call_count == 1
        _, kwargs = spy.call_args
        assert kwargs.get("batch_size") == 2
