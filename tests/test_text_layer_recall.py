"""Unit tests for the PDF text-layer recall source (``core/text_layer_recall.py``).

The source recovers text lines Surya missed by reading the input PDF's
embedded text layer. These tests build real one/two-line PDFs with
PyMuPDF so extraction, normalization, dedup, and the cap are exercised
against genuine ``get_text("words")`` output rather than mocks.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

from omniscribe.core.text_layer_recall import (
    PdfTextLayerRecall,
    TextLayerRecallOptions,
)
from omniscribe.core.workflows.hybrid import HybridEngine
from tests.conftest import _StubOCR
from tests.test_pipeline import _make_tiny_b64_image, _StubAligner, _StubPDF
from tests.test_workflows_hybrid import _engine, _noop_writer

# Page geometry for the fixture PDFs: US Letter in points. Line ``i`` sits
# with its baseline at ``100 + 40*i`` pt, so normalized centers land near
# (100 + 40*i) / 792 — stable anchors for the assertions below.
_PAGE_W, _PAGE_H = 612.0, 792.0


def _build_pdf(tmp_path: Path, pages: list[list[str]]) -> Path:
    """Create a PDF with one text line per entry at a predictable position."""
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        for i, text in enumerate(lines):
            page.insert_text((72.0, 100.0 + 40.0 * i), text, fontsize=12)
    pdf_path = tmp_path / "sample.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestOpenAndLifecycle:
    def test_open_returns_true_for_pdf(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["Hello world line"]])
        src = PdfTextLayerRecall()
        assert src.open(str(pdf)) is True
        src.close()

    def test_non_pdf_input_is_a_noop(self, tmp_path: Path) -> None:
        src = PdfTextLayerRecall()
        assert src.open(str(tmp_path / "scan.png")) is False
        assert src.supplement(0, []) == []
        src.close()  # close without open must be safe

    def test_missing_pdf_fails_open(self, tmp_path: Path) -> None:
        src = PdfTextLayerRecall()
        assert src.open(str(tmp_path / "does-not-exist.pdf")) is False
        assert src.supplement(0, []) == []

    def test_disabled_options_skip_everything(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["Hello world line"]])
        src = PdfTextLayerRecall(TextLayerRecallOptions(enabled=False))
        assert src.enabled is False
        assert src.open(str(pdf)) is False
        assert src.supplement(0, []) == []

    def test_supplement_before_open_returns_empty(self) -> None:
        src = PdfTextLayerRecall()
        assert src.supplement(0, []) == []

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["Hello world line"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        src.close()
        src.close()

    def test_out_of_range_pages_return_empty(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["Hello world line"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            assert src.supplement(3, []) == []
            assert src.supplement(-1, []) == []
        finally:
            src.close()


class TestKillSwitchEnv:
    @pytest.mark.parametrize(
        "value",
        [
            "0",
            "false",
            "no",
            "off",
            "n",
            "disabled",
            "FALSE",
            " Off ",
            "N",
            " Disabled ",
        ],
    )
    def test_disable_values(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OMNISCRIBE_TEXT_LAYER_RECALL", value)
        assert TextLayerRecallOptions.from_env().enabled is False

    @pytest.mark.parametrize("value", ["", "1", "true", "yes", "on", "bogus"])
    def test_unset_and_truthy_values_stay_enabled(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_TEXT_LAYER_RECALL", value)
        assert TextLayerRecallOptions.from_env().enabled is True

    def test_unset_env_defaults_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_TEXT_LAYER_RECALL", raising=False)
        assert TextLayerRecallOptions.from_env().enabled is True


class TestSupplement:
    def test_recovers_line_not_covered_by_existing_boxes(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["First line of text", "Second line of text"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            # Existing boxes cover line 1 (baseline y=100 -> normalized
            # ~0.11-0.13); line 2 (baseline 140) is the Surya miss.
            extras = src.supplement(0, [(0.05, 0.10, 0.95, 0.145)])
        finally:
            src.close()
        assert len(extras) == 1
        x0, y0, x1, y1 = extras[0]
        assert 0.0 <= x0 < x1 <= 1.0
        assert 0.0 <= y0 < y1 <= 1.0
        # Second-line baseline at 140pt of 792pt: center near 0.17.
        assert 0.14 < (y0 + y1) / 2 < 0.20

    def test_covered_lines_are_deduped(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["Only line on page"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            # A box spanning the whole line region covers the candidate.
            extras = src.supplement(0, [(0.05, 0.05, 0.95, 0.20)])
        finally:
            src.close()
        assert extras == []
        assert src.candidates_dropped == 1

    def test_page_without_text_layer_yields_nothing(self, tmp_path: Path) -> None:
        doc = fitz.open()
        doc.new_page(width=_PAGE_W, height=_PAGE_H)
        pdf_path = tmp_path / "blank.pdf"
        doc.save(str(pdf_path))
        doc.close()
        src = PdfTextLayerRecall()
        src.open(str(pdf_path))
        try:
            assert src.supplement(0, []) == []
        finally:
            src.close()

    def test_multiword_line_merges_into_union_box(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["hello wide world of words"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            extras = src.supplement(0, [])
        finally:
            src.close()
        # Five words on one extraction line collapse to one union box.
        assert len(extras) == 1
        x0, _y0, x1, _y1 = extras[0]
        # "hello" alone spans ~0.07 of the page width; the union of all
        # five words must be far wider than any single word.
        assert x1 - x0 > 0.18

    def test_cap_bounds_boxes_per_page(self, tmp_path: Path) -> None:
        lines = [f"Text line number {i} here" for i in range(15)]
        pdf = _build_pdf(tmp_path, [lines])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            extras = src.supplement(0, [])
        finally:
            src.close()
        assert len(extras) == 10
        assert src.candidates_dropped == 5

    def test_straddle_guard_rejects_line_spanning_two_boxes(
        self, tmp_path: Path
    ) -> None:
        pdf = _build_pdf(
            tmp_path, [["A rather long line of text spanning across the page"]]
        )
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            # Two side-by-side boxes each cover well over 15% of the line:
            # the candidate straddles and must be rejected, never merged.
            extras = src.supplement(
                0, [(0.05, 0.10, 0.35, 0.16), (0.35, 0.10, 0.95, 0.16)]
            )
        finally:
            src.close()
        assert extras == []

    def test_candidates_dropped_is_cumulative(self, tmp_path: Path) -> None:
        pdf = _build_pdf(tmp_path, [["First line of text", "Second line of text"]])
        src = PdfTextLayerRecall()
        src.open(str(pdf))
        try:
            src.supplement(0, [(0.05, 0.10, 0.95, 0.145)])  # 1 of 2 dropped
            src.supplement(0, [])  # nothing dropped
        finally:
            src.close()
        assert src.candidates_dropped == 1


# ---------------------------------------------------------------------------
# HybridEngine wiring (moved from test_workflows_hybrid.py — Phase 4.2)
# ---------------------------------------------------------------------------


class _TLStub:
    """Duck-typed ``PdfTextLayerRecall`` for engine-level wiring tests."""

    def __init__(
        self,
        extras_by_page: dict[int, list[tuple[float, float, float, float]]]
        | None = None,
        *,
        enabled: bool = True,
        failing_pages: set[int] | None = None,
    ) -> None:
        self.extras_by_page = extras_by_page or {}
        self.enabled = enabled
        self.failing_pages = failing_pages or set()
        self.candidates_dropped = 0
        self.opened_with: str | None = None
        self.closed = False
        self.seen_references: dict[int, list] = {}

    def open(self, input_path: str) -> bool:
        self.opened_with = input_path
        return self.enabled

    def close(self) -> None:
        self.closed = True

    def supplement(self, page_num: int, existing_boxes: list):
        self.seen_references[page_num] = list(existing_boxes)
        if page_num in self.failing_pages:
            raise RuntimeError("text layer exploded")
        return list(self.extras_by_page.get(page_num, []))


class TestHybridTextLayerRecall:
    """Second box source merged after the whitespace booster."""

    async def test_extras_merged_and_summary_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        source = _TLStub(extras_by_page={0: [(0.1, 0.5, 0.9, 0.55)]})
        aligner = _StubAligner(boxes_per_page=[(0.1, 0.1, 0.9, 0.2)])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            text_layer_recall=source,  # type: ignore[arg-type]
        )
        with caplog.at_level("INFO", logger="omniscribe.core.workflows.hybrid"):
            pages = await engine._detect_layout(
                images_dict={0: _make_tiny_b64_image()},
                page_nums=[0],
                progress=None,
                input_path="in.pdf",
            )
        boxes = [box for box, _text in pages[0]]
        assert (0.1, 0.5, 0.9, 0.55) in boxes
        assert (0.1, 0.1, 0.9, 0.2) in boxes
        summaries = [
            r.getMessage()
            for r in caplog.records
            if "Text-layer recall summary" in r.getMessage()
        ]
        assert summaries == [
            "Text-layer recall summary: 1 box(es) added on 1 of 1 page(s); "
            "0 line(s) dropped by dedup/cap"
        ]
        assert source.opened_with == "in.pdf"
        assert source.closed is True

    async def test_disabled_source_never_supplements_but_still_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        source = _TLStub(extras_by_page={0: [(0.1, 0.5, 0.9, 0.55)]}, enabled=False)
        aligner = _StubAligner(boxes_per_page=[(0.1, 0.1, 0.9, 0.2)])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            text_layer_recall=source,  # type: ignore[arg-type]
        )
        with caplog.at_level("INFO", logger="omniscribe.core.workflows.hybrid"):
            pages = await engine._detect_layout(
                images_dict={0: _make_tiny_b64_image()},
                page_nums=[0],
                progress=None,
                input_path="in.pdf",
            )
        # open() ran (and declined); supplement never did.
        assert source.opened_with == "in.pdf"
        assert source.seen_references == {}
        assert source.closed is False
        boxes = [box for box, _text in pages[0]]
        assert boxes == [(0.1, 0.1, 0.9, 0.2)]
        summaries = [
            r.getMessage()
            for r in caplog.records
            if "Text-layer recall summary" in r.getMessage()
        ]
        assert summaries == [
            "Text-layer recall summary: 0 box(es) added on 0 of 1 page(s); "
            "0 line(s) dropped by dedup/cap"
        ]

    async def test_no_source_keeps_output_and_stays_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        aligner = _StubAligner(boxes_per_page=[(0.1, 0.1, 0.9, 0.2)])
        engine = _engine(aligner=aligner)
        with caplog.at_level("INFO", logger="omniscribe.core.workflows.hybrid"):
            pages = await engine._detect_layout(
                images_dict={0: _make_tiny_b64_image()},
                page_nums=[0],
                progress=None,
                input_path="in.pdf",
            )
        assert [box for box, _text in pages[0]] == [(0.1, 0.1, 0.9, 0.2)]
        assert not [
            r for r in caplog.records if "Text-layer recall summary" in r.getMessage()
        ]

    async def test_partial_failure_keeps_page_boxes(self) -> None:
        source = _TLStub(extras_by_page={0: [(0.1, 0.5, 0.9, 0.55)]}, failing_pages={1})
        aligner = _StubAligner(
            boxes_per_page=[(0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4)]
        )
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(n_pages=2),
            output_writer=_noop_writer,
            text_layer_recall=source,  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image(), 1: _make_tiny_b64_image()},
            page_nums=[0, 1],
            progress=None,
            input_path="in.pdf",
        )
        # Page 0 merged; page 1 failed inside supplement and kept its
        # Surya boxes (fail-open, per page). The stub hands every page
        # the same box list.
        assert (0.1, 0.5, 0.9, 0.55) in [box for box, _text in pages[0]]
        assert [box for box, _text in pages[1]] == [
            (0.1, 0.1, 0.9, 0.2),
            (0.1, 0.3, 0.9, 0.4),
        ]

    async def test_dedup_reference_includes_booster_extras(self) -> None:
        class _BoosterStubTL:
            enabled = True

            def __init__(self, extra: tuple[float, float, float, float]) -> None:
                self._extra = extra

            def supplement(self, image, boxes):
                return [self._extra]

        booster_extra = (0.1, 0.02, 0.9, 0.05)
        source = _TLStub()
        aligner = _StubAligner(boxes_per_page=[(0.1, 0.1, 0.9, 0.2)])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_BoosterStubTL(booster_extra),  # type: ignore[arg-type]
            text_layer_recall=source,  # type: ignore[arg-type]
        )
        await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            progress=None,
            input_path="in.pdf",
        )
        # Cross-source dedup contract: the text-layer pass sees the page's
        # boxes AFTER the whitespace booster merged its extras.
        reference = source.seen_references[0]
        assert booster_extra in reference
        assert (0.1, 0.1, 0.9, 0.2) in reference

    async def test_real_source_through_detect_layout(self, tmp_path) -> None:
        # Real ``PdfTextLayerRecall`` against a real PDF: no Surya boxes,
        # both text-layer lines must land in the detection output.
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72.0, 100.0), "First line of text", fontsize=12)
        page.insert_text((72.0, 140.0), "Second line of text", fontsize=12)
        pdf_path = tmp_path / "real.pdf"
        doc.save(str(pdf_path))
        doc.close()

        class _EmptyAligner:
            # ``_StubAligner`` cannot express zero boxes per page (an
            # empty list falls back to its defaults).
            def get_detected_boxes_batch(self, images):
                return [[] for _ in images]

        engine = HybridEngine(
            aligner=_EmptyAligner(),  # type: ignore[arg-type]
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            text_layer_recall=PdfTextLayerRecall(),
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            progress=None,
            input_path=str(pdf_path),
        )
        assert len(pages[0]) == 2
        for box, _text in pages[0]:
            # Merge boundary normalizes onto the BBox tuple contract.
            assert isinstance(box, tuple)
            assert all(0.0 <= v <= 1.0 for v in box)
