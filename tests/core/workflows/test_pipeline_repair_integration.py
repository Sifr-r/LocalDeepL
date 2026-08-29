"""Sprint 4 / H-1 audit fix: end-to-end integration test for the
QualityRepairLoop wired into OCRPipeline.process().

The unit tests in ``test_repair.py`` cover the repair loop in isolation
with a synthetic ``re_ocr`` callable. They do not exercise the
``OCRPipeline -> HybridEngine -> _repair_blocks -> QualityRepairLoop``
wiring. A regression that drops the call site (e.g. a refactor that
removes the ``repair_options`` forwarding) would pass the unit tests
silently but leave the user-facing "low confidence retry" feature
broken.

This module is the integration test that catches that. It wires a
tiny ``OCRPipeline`` with stubbed aligner / OCR / PDF and asserts
that ``run(..., repair_options=enabled)`` actually drives the repair
loop and the repaired text reaches the final document.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from omniscribe.core.workflows.repair import RepairOptions
from omniscribe.pipeline import OCRPipeline
from tests.conftest import _StubOCR


# Tiny 1-page base64 image that always passes the blank-crop guard in
# the refine stage. Stolen from the existing test_pipeline helper.
def _tiny_b64() -> str:
    import base64

    img = Image.new("RGB", (300, 300), "white")
    draw = ImageDraw.Draw(img)
    for y in range(0, 300, 20):
        draw.rectangle([0, y, 300, y + 5], fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _StubAligner:
    def __init__(self) -> None:
        # Three boxes; the OCR text length matches the aligner so
        # ``_align_text`` is a no-op identity. The 1st box is "low
        # confidence" (single short character) so the repair loop
        # MUST re-OCR it; the 2nd and 3rd are "high confidence" (3+
        # alphabetic words) so the loop MUST NOT touch them.
        self.boxes = [
            [0.1, 0.1, 0.9, 0.15],
            [0.1, 0.2, 0.9, 0.25],
            [0.1, 0.3, 0.9, 0.35],
        ]
        self.calls = 0

    def get_detected_boxes_batch(self, images):
        return [list(self.boxes) for _ in images]

    def align_text(self, structured, lines):
        self.calls += 1
        out = []
        for i, (box, _) in enumerate(structured):
            out.append((box, lines[i] if i < len(lines) else ""))
        return out


class _StubPDF:
    def __init__(self, n_pages: int = 1) -> None:
        self.n_pages = n_pages
        # page_index -> list[(box, text)]
        self.pages: dict[int, list[tuple[list[float], str]]] = {}
        # crop calls recorded by the pipeline (via
        # ``perform_ocr_on_crop``) so the test can assert the repair
        # loop actually fired.
        self.embedded: dict[int, list[tuple[list[float], str]]] = {}

    def convert_to_images(self, path, dpi=150, max_image_dim=1024):
        return {i: _tiny_b64() for i in range(self.n_pages)}

    def embed_structured_text(self, inp, out, pages, dpi):
        # ``pages`` is what the engine actually decided to write;
        # we mirror it so the test can read back the final text.
        self.embedded = {k: list(v) for k, v in pages.items()}


async def test_H1_OCRPipeline_runs_repair_loop_when_enabled() -> None:
    """Low-confidence blocks are re-OCR'd; the result reaches the PDF.

    The first aligned text is a single character ``"x"`` so the
    confidence estimator returns ~0.0 (one short char, no real
    words). The QualityRepairLoop MUST classify that block as
    below the 0.9 target and re-OCR it via
    ``perform_ocr_on_crop``. The other two blocks are 3+ words of
    real prose, so the loop MUST leave them alone.
    """
    aligner = _StubAligner()
    pdf = _StubPDF(n_pages=1)
    # The first aligned line is low-confidence text (a single short
    # character triggers the estimator's 1-2 word branch at ~0.7,
    # or 0.0 for the all-whitespace branch). The 2nd and 3rd lines
    # are 3+ alphabetic words so the estimator returns 0.99.
    ocr = _StubOCR(
        page_lines=[
            "x",  # low confidence — repair loop re-OCRs to "recovered"
            "Section heading with several words here",
            "First paragraph of body text with several words.",
        ],
        crop_text="REPAIRED low confidence text",
    )

    pipe = OCRPipeline(aligner, ocr, pdf)
    repair_opts = RepairOptions(enabled=True, target=0.9, max_retries=1)
    await pipe.run(
        "in.pdf",
        "out.pdf",
        concurrency=1,
        refine=False,
        repair_options=repair_opts,
    )

    # The repair loop should have called perform_ocr_on_crop at
    # least once for the low-confidence block.
    assert ocr.crop_calls >= 1, (
        f"expected QualityRepairLoop to fire perform_ocr_on_crop at "
        f"least once for the low-confidence block, got crop_calls="
        f"{ocr.crop_calls}"
    )
    # The PDF's embed step was called with the engine's per-page
    # block list. The first block on page 0 should be the REPAIRED
    # text (not the original "x").
    embedded = pdf.embedded[0]
    assert embedded[0][1] == "REPAIRED low confidence text", (
        f"expected first block on page 0 to be the repaired text, "
        f"got {embedded[0][1]!r}"
    )
    # The other two blocks should be untouched.
    assert embedded[1][1] == "Section heading with several words here"
    assert embedded[2][1] == "First paragraph of body text with several words."


async def test_H1_OCRPipeline_skips_repair_when_disabled() -> None:
    """When ``repair_options`` is None (the in-process default), the
    QualityRepairLoop MUST NOT be invoked — even if a block has
    low confidence — so programmatic callers that opt out of the
    retry loop pay the same VLM cost as before the feature landed.
    """
    aligner = _StubAligner()
    pdf = _StubPDF(n_pages=1)
    ocr = _StubOCR(page_lines=["x", "y", "z"], crop_text="REPAIRED")

    pipe = OCRPipeline(aligner, ocr, pdf)
    # Pass ``repair_options=None`` explicitly so the test reads as the
    # canonical "in-process programmatic use" path documented in
    # AGENTS.md.
    await pipe.run(
        "in.pdf",
        "out.pdf",
        concurrency=1,
        refine=False,
        repair_options=None,
    )

    # The first block on page 0 should still be the original "x" —
    # the repair loop never ran.
    embedded = pdf.embedded[0]
    assert embedded[0][1] == "x", (
        f"expected first block on page 0 to be the un-repaired text, "
        f"got {embedded[0][1]!r}"
    )
    assert ocr.crop_calls == 0, (
        "QualityRepairLoop must not call perform_ocr_on_crop when "
        "repair_options is None"
    )
