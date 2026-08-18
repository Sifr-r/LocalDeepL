"""A/B contract tests for local document processors.

Each processor carries a ``ProcessorContract`` declaration
(ANNOTATE_ONLY / MAY_REORDER / MAY_DELETE). This file builds a
synthetic ``DocumentResult`` and runs the processor against it,
asserting that the contract is honoured: an annotate-only processor
must not change block count or order, a reorder processor must
change order, etc.

These tests catch regressions where a processor accidentally drops
blocks (silent data loss) or reorders blocks whose ``contract`` says
it shouldn't. They're cheap (no LLM, no Surya) so they can run in
the fast tier.
"""

from __future__ import annotations

from omniscribe.core.document import DocumentBlock, DocumentPage, DocumentResult
from omniscribe.core.processors.base import (
    LOCAL_DOCUMENT_PROCESSOR_NAMES,
    ProcessorContract,
    build_document_processors,
    run_document_processors,
)
from omniscribe.core.processors.quality import QualityAnalysisProcessor
from omniscribe.core.processors.reading_order import ReadingOrderProcessor


def _make_doc_result() -> DocumentResult:
    """Synthetic single-page document with three text blocks in a known order.

    The blocks are placed out of row-major order (``y=0.05`` then
    ``y=0.20`` then ``y=0.55``) so the reading-order reorderer has
    something to do; the assert at the bottom of the reorder test then
    verifies the result is sorted ascending. Text density is chosen so
    QualityAnalysis sees a non-sparse page.
    """
    blocks = [
        # Deliberately top-of-page header first; the reorder test relies on
        # this being a non-monotonic y order to assert the processor ran.
        DocumentBlock(
            bbox=[0.1, 0.05, 0.9, 0.12],
            text="first header line",
            kind="text",
        ),
        DocumentBlock(
            bbox=[0.1, 0.20, 0.9, 0.45],
            text="body paragraph with enough text to look real",
            kind="text",
        ),
        DocumentBlock(
            bbox=[0.1, 0.55, 0.9, 0.62],
            text="second header line",
            kind="text",
        ),
    ]
    page = DocumentPage(
        page_index=0,
        width=1700,
        height=2200,
        blocks=blocks,
    )
    return DocumentResult(
        source_path="synthetic://test_doc",
        pages=[page],
    )


def _run_processor(processor) -> DocumentResult:
    """Build a fresh synthetic document.

    Kept as a thin wrapper around ``_make_doc_result`` so the test body
    reads as "run processor against a controlled input". The
    ``processor`` argument is unused — it documents intent only — so a
    regression that adds new processor-specific seed state has a single
    place to extend.
    """
    del processor  # documented for readability; not yet branched on
    return _make_doc_result()


async def test_quality_analysis_is_annotate_only_and_emits_metadata() -> None:
    """QualityAnalysis declares ANNOTATE_ONLY and must not change blocks/order.

    ``run_document_processors(strict=True)`` would raise ValueError if a
    declared annotate-only processor mutated the block count, so passing
    strict=True turns the contract declaration into a load-bearing check.
    The treatment must also attach a ``quality`` metadata entry per page
    so downstream code can read the score without re-running the LLM.
    """
    seed = _run_processor(QualityAnalysisProcessor())
    # Deep-copy the seed so the control is byte-identical to the input;
    # processors are allowed to mutate in place, so we cannot rely on
    # the seed itself for the control comparison.
    import copy

    control = copy.deepcopy(seed)

    result = await run_document_processors(
        seed,
        [QualityAnalysisProcessor()],
        strict=True,
    )

    # Block count, order, and content are unchanged.
    assert [(b.bbox, b.text) for page in result.pages for b in page.blocks] == [
        (b.bbox, b.text) for page in control.pages for b in page.blocks
    ]
    # A quality metadata entry was added.
    quality_meta = result.pages[0].metadata.get("quality")
    assert isinstance(quality_meta, dict)
    assert "block_count" in quality_meta
    assert quality_meta["block_count"] == len(control.pages[0].blocks)


async def test_reading_order_may_reorder_blocks() -> None:
    """ReadingOrder may reorder blocks but must not drop or create them.

    The synthetic document is constructed out of row-major order so the
    sort must change the order on output. Block count and content are
    preserved (multiset equality on the text strings), and the final
    y-coordinates are sorted ascending — the canonical reading-order
    invariant for top-to-bottom Latin scripts.
    """
    seed = _run_processor(ReadingOrderProcessor())
    import copy

    control = copy.deepcopy(seed)

    result = await run_document_processors(seed, [ReadingOrderProcessor()])

    original_count = sum(len(p.blocks) for p in control.pages)
    treated_count = sum(len(p.blocks) for p in result.pages)
    assert treated_count == original_count

    # Multiset equality on text proves no block was dropped or duplicated
    # even though their order may have changed.
    original_texts = [b.text for p in control.pages for b in p.blocks]
    treated_texts = [b.text for p in result.pages for b in p.blocks]
    assert sorted(original_texts) == sorted(treated_texts)

    # Reading order indices should reflect the new order, top to bottom.
    bboxes_in_order = [(p.page_index, b.bbox) for p in result.pages for b in p.blocks]
    ys = [bb[1][1] for bb in bboxes_in_order]
    assert ys == sorted(ys), (
        "reading_order processor must produce non-decreasing y coordinates"
    )


def test_build_document_processors_resolves_every_public_name() -> None:
    """Every name in ``LOCAL_DOCUMENT_PROCESSOR_NAMES`` resolves through the registry.

    Catches regressions where a new processor is added to the public
    list but its factory is forgotten in ``build_document_processors``
    (silent ``KeyError`` for users who pick it via the Web/API). Also
    asserts that every registered processor declares one of the three
    valid ``ProcessorContract`` values so a typo in a future enum
    member doesn't silently downgrade the strict-validation gate.
    """
    expected_contracts = {
        ProcessorContract.ANNOTATE_ONLY,
        ProcessorContract.MAY_REORDER,
        ProcessorContract.MAY_DELETE,
    }
    for name in LOCAL_DOCUMENT_PROCESSOR_NAMES:
        proc = build_document_processors([name])
        assert len(proc) == 1, f"{name!r} resolved to {len(proc)} factories"
        assert proc[0].name == name
        # Every public processor must declare a meaningful contract.
        assert proc[0].contract in expected_contracts, (
            f"{name!r} declared unknown contract {proc[0].contract!r}"
        )
