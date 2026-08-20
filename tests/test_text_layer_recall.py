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
