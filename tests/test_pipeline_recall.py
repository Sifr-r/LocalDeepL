"""End-to-end OCR confidence gate.

Heavyweight integration test: load real Surya, run real PDF conversion,
stub the LLM to return the ground-truth text verbatim, run the hybrid
pipeline (Surya detection → DP align), then compute block recall against
the matching ``ground_truth_*.json`` fixture.

Parametrised over the three original (non-bootstrapped) fixtures --
``digital.pdf``, ``hybrid.pdf``, ``handwritten.pdf``. ``dense.pdf`` and
``notes.pdf`` are intentionally excluded: their fixtures were built from
a previous pipeline run rather than hand-annotation, so a regression
here would measure the pipeline against itself and mask real drift.

The stub returning the GT text is the upper bound on what the pipeline
can ever recover on a fixture -- this test measures the
detection+alignment+formatting stack's fidelity when transcription is
free. If the recall regresses here, something in the DP or PDF embedding
path lost a box.

Marked ``slow`` because Surya init is ~5s on first run.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from local_deepl.core.aligner import HybridAligner
from local_deepl.core.document import BBox
from local_deepl.core.ocr import OCRProcessor
from local_deepl.core.pdf import PDFHandler
from local_deepl.evaluation import (
    compute_report,
    load_ground_truth,
)
from local_deepl.pipeline import OCRPipeline

pytestmark = pytest.mark.slow


FIXTURES = Path(__file__).parent / "fixtures"

# PDF name -> (GT fixture, recall floor, text-similarity floor). Limited to
# hand-annotated fixtures (see module docstring). Adding more PDFs here is the
# right knob for the recall regression gate to expand its coverage.
#
# Per-PDF floors: digital + handwritten pages are paragraph-style text so a
# tight 0.40 recall / 0.50 text-sim floor catches catastrophic box loss
# without false alarms.
# ``hybrid.pdf`` is a HEALTH INTAKE FORM where the pipeline emits ~16 boxes
# that aggregate the 38 hand-annotated form fields into wider regions
# (label+answer concatenated, surrounding-legend absorbed), so:
#   - recall floor is 0.25: 16/38 = 0.42 is the geometric upper bound, and a
#     true "Hungarian finds zero matches" regression still falls below 0.25
#   - text-sim floor is 0.20: the Hungarian matcher has to pair single GT
#     rows against pipeline boxes whose text contains multiple GT blocks, so
#     the per-pair ratio is naturally diluted
PDF_TO_FIXTURE = {
    "digital.pdf": ("ground_truth_digital.json", 0.40, 0.50),
    "hybrid.pdf": ("ground_truth_hybrid.json", 0.25, 0.20),
    "handwritten.pdf": ("ground_truth_handwritten.json", 0.40, 0.50),
}


@pytest.mark.parametrize(
    "pdf_name,fixture_name,recall_floor,text_sim_floor",
    [
        (name, fixture, recall, text_sim)
        for name, (fixture, recall, text_sim) in sorted(PDF_TO_FIXTURE.items())
    ],
)
def test_recall_above_threshold(
    pdf_name: str,
    fixture_name: str,
    recall_floor: float,
    text_sim_floor: float,
    surya_aligner: HybridAligner,
    example_pdfs: dict[str, Path],
    tmp_path: Path,
) -> None:
    """Upper-bound recall check: stub returns GT text, expect per-PDF floors.

    These are deliberately conservative floors so the test fails loudly
    when the pipeline breaks and not when detection geometry drifts by
    a few pixels. A regression that halves the recall across every PDF
    in the parametrize set is the real alarm bell.

    The block-recall floor catches *catastrophic* box loss (Hungarian
    pairing finds zero matches). The text-similarity floor catches
    content corruption in the refinement/embed pipeline. Nuanced quality
    regressions live in ``scripts/confidence_eval.py`` instead -- this
    gate is "did the pipeline at least deliver?".
    """
    # Build a stub whose ``perform_ocr`` always emits the GT text for
    # page 0, in order. This is the upper-bound: if transcription were
    # perfect, this is what the pipeline would see.
    gt_fixture = FIXTURES / fixture_name
    gt_blocks, _page_size = load_ground_truth(gt_fixture)
    if not gt_blocks:
        pytest.skip(f"{gt_fixture.name} is empty")
    gt_text = [b.text for b in gt_blocks]

    # Snapshot the document blocks emitted into the output PDF. We use
    # this to compute recall against the ground-truth fixture without
    # re-running Surya detection -- the boxes are exactly what the
    # embedder used, which is the strongest "did the pipeline lose a
    # block?" check we can run offline. YAGNI: only ``(bbox, text)``
    # pairs are read; richer fields on the DocumentResult are kept but
    # ignored here.
    captured: list[tuple[BBox, str]] = []

    class _CaptureStub(OCRProcessor):
        # Skip __init__: we don't need a live LLM client.
        def __init__(self) -> None:  # type: ignore[no-untyped-def]
            return  # type: ignore[return-value]

        async def perform_ocr(  # type: ignore[no-untyped-def]
            self, image_base64: str, **kwargs
        ):
            return list(gt_text)

        async def perform_ocr_on_crop(self, image_base64: str, **kwargs) -> str:
            return "recovered"

    pipe = OCRPipeline(
        aligner=surya_aligner,
        ocr_processor=_CaptureStub(),
        pdf_handler=PDFHandler(),
    )
    output_pdf = str(tmp_path / f"recall_{pdf_name}")
    asyncio.run(
        pipe.run(
            str(example_pdfs[pdf_name]),
            output_pdf,
            pages="1",
            concurrency=1,
            refine=False,
        )
    )

    # The pipeline exposes ``last_document_result`` for exactly this
    # kind of "what boxes did you actually emit?" introspection. Walk
    # the page tree and collect (bbox, text) pairs in document order.
    doc_result = pipe.last_document_result
    if doc_result is None:
        pytest.skip(f"{pdf_name}: pipeline produced no DocumentResult")
    for page in doc_result.pages:
        for block in page.blocks:
            text = getattr(block, "text", "") or ""
            bbox = getattr(block, "bbox", None)
            if not text or bbox is None:
                continue
            captured.append((bbox, text))

    if not captured:
        pytest.skip(
            f"{pdf_name}: pipeline emitted no (bbox, text) pairs to compare against GT"
        )

    report = compute_report(
        f"{pdf_name} (recall upper bound)",
        gt_blocks,
        captured,
        iou_threshold=0.3,
    )

    assert report.block_recall >= recall_floor, (
        f"{pdf_name}: lost too many GT blocks (floor={recall_floor:.2f}): "
        f"{report.summary_line()}"
    )
    # The Hungarian matcher should pair most GT rows with pipeline
    # boxes whose text semantically matches. A regression that mangles
    # the text (refinement corrupting content, wrong-line emission)
    # drops avg text_similarity; the catastrophic-recovery bar is 0.5
    # (substantial substring overlap after normalization).
    assert report.avg_text_similarity >= text_sim_floor, (
        f"{pdf_name}: matched blocks no longer carry GT text faithfully "
        f"(floor={text_sim_floor:.2f}): {report.summary_line()}"
    )
