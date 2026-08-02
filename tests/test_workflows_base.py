"""Tests for the shared workflow helpers in `core.workflows.base`.

`_cross_page_merge` covers the text-level post-processing; the rest of
``EngineBase`` (state lifecycle, ``_build_document_result``, ``_emit``) is
exercised both here in isolation and through the engine tests in
``test_pipeline.py``.
"""

from __future__ import annotations

from omniscribe.core.document import DocumentResult
from omniscribe.core.processors import DocumentProcessor
from omniscribe.core.workflows.base import EngineBase


def _noop_writer(_in: str, _out: str, _pages: dict, _dpi: int) -> None:
    """Output writer that throws away the pages dict. Tests don't inspect PDF output."""


def _engine(
    *,
    document_processors: list[DocumentProcessor] | None = None,
) -> EngineBase:
    """Construct an `EngineBase` without invoking `__init_subclass__` hooks."""

    class _StubEngine(EngineBase):
        pass

    return _StubEngine(
        output_writer=_noop_writer, document_processors=document_processors
    )


def test_cross_page_merge_joins_unterminated_tail_into_next_page() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Hello world")],
        1: [([0.0, 0.0, 1.0, 0.1], "continues here")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "Hello world continues here")


def test_cross_page_merge_does_not_join_terminated_sentence() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Sentence ends.")],
        1: [([0.0, 0.0, 1.0, 0.1], "New sentence.")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Sentence ends.")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "New sentence.")


def test_cross_page_merge_handles_single_page() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Only one")],
    }
    _engine()._cross_page_merge(pages, [0])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Only one")


def test_cross_page_merge_skips_blank_tail_box() -> None:
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [
            ([0.0, 0.0, 1.0, 0.1], "Sentence."),
            ([0.0, 0.0, 1.0, 0.1], "  "),
        ],
        1: [([0.0, 0.0, 1.0, 0.1], "Next page")],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    # The terminated sentence is untouched; the blank box is too.
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "Sentence.")
    assert pages[0][1] == ([0.0, 0.0, 1.0, 0.1], "  ")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "Next page")


def test_cross_page_merge_skips_blank_head_box() -> None:
    """If the next page's first non-blank box isn't its literal first, find it."""
    pages: dict[int, list[tuple[list[float], str]]] = {
        0: [([0.0, 0.0, 1.0, 0.1], "Trailing")],
        1: [
            ([0.0, 0.0, 1.0, 0.1], "  "),
            ([0.0, 0.0, 1.0, 0.1], "real head"),
        ],
    }
    _engine()._cross_page_merge(pages, [0, 1])
    assert pages[0][0] == ([0.0, 0.0, 1.0, 0.1], "")
    # The merge targets the first non-blank head box.
    assert pages[1][1] == ([0.0, 0.0, 1.0, 0.1], "Trailing real head")
    assert pages[1][0] == ([0.0, 0.0, 1.0, 0.1], "  ")


class _IdentityProcessor(DocumentProcessor):
    """Trivial document processor: tags each page so we can verify it ran."""

    async def process(self, document: DocumentResult) -> DocumentResult:
        for page in document.pages:
            page.metadata["identity_processor"] = True
        return document


class TestRunStateLifecycle:
    def test_initial_state_is_empty(self) -> None:
        engine = _engine()
        assert engine.last_document_result is None
        assert engine.last_failed_pages == []

    def test_reset_clears_state(self) -> None:
        engine = _engine()
        engine.last_document_result = DocumentResult(pages=[])
        engine.last_failed_pages = [0, 1]
        engine._reset_run_state()
        assert engine.last_document_result is None
        assert engine.last_failed_pages == []


class TestBuildDocumentResult:
    async def test_applies_spellcheck_in_place(self, monkeypatch) -> None:
        class _StubSpellchecker:
            def __init__(self, lang):
                self.lang = lang

            async def ensure_loaded(self):
                pass

            def correct_text(self, text):
                return text + " [corrected " + self.lang + "]"

        monkeypatch.setattr(
            "omniscribe.core.postprocess.DictionaryPostProcessor", _StubSpellchecker
        )

        engine = _engine()
        pages_data: dict[int, list[tuple[list[float], str]]] = {
            0: [([0.0, 0.0, 1.0, 0.1], "teh"), ([0.0, 0.0, 1.0, 0.1], "")],
        }

        result = await engine._build_document_result(
            pages_data=pages_data,
            page_nums=[0],
            source_path="in.pdf",
            source_processor="test",
            spellcheck="en-US",
            cross_page=False,
        )

        assert pages_data[0][0][1] == "teh [corrected en-US]"
        assert pages_data[0][1][1] == ""  # empty text is unchanged
        assert result.pages[0].blocks[0].text == "teh [corrected en-US]"

    async def test_applies_cross_page_merge_in_place(self) -> None:
        engine = _engine()
        pages_data: dict[int, list[tuple[list[float], str]]] = {
            0: [([0.0, 0.0, 1.0, 0.1], "Trailing")],
            1: [([0.0, 0.0, 1.0, 0.1], "head")],
        }
        result = await engine._build_document_result(
            pages_data=pages_data,
            page_nums=[0, 1],
            source_path="in.pdf",
            source_processor="test",
            spellcheck="none",
            cross_page=True,
        )
        # cross_page merge mutates pages_data AND the emitted DocumentResult.
        assert pages_data[0][0][1] == ""
        assert pages_data[1][0][1] == "Trailing head"
        assert result.pages[0].blocks[0].text == ""
        assert result.pages[1].blocks[0].text == "Trailing head"

    async def test_runs_document_processors(self) -> None:
        engine = _engine(document_processors=[_IdentityProcessor()])
        pages_data: dict[int, list[tuple[list[float], str]]] = {
            0: [([0.0, 0.0, 1.0, 0.1], "hello")],
        }
        result = await engine._build_document_result(
            pages_data=pages_data,
            page_nums=[0],
            source_path="in.pdf",
            source_processor="test",
            spellcheck="none",
            cross_page=False,
        )
        assert result.pages[0].metadata.get("identity_processor") is True

    async def test_overlays_page_metadata(self) -> None:
        engine = _engine()
        pages_data: dict[int, list[tuple[list[float], str]]] = {
            0: [([0.0, 0.0, 1.0, 0.1], "x")],
        }
        result = await engine._build_document_result(
            pages_data=pages_data,
            page_nums=[0],
            source_path="in.pdf",
            source_processor="test",
            spellcheck="none",
            cross_page=False,
            page_metadata_overlays={0: {"preprocessing": {"deskewed": True}}},
        )
        assert result.pages[0].metadata.get("preprocessing") == {"deskewed": True}


class TestEmit:
    async def test_assigns_last_document_result_and_invokes_writer(self) -> None:
        captured: dict = {}

        def writer(inp: str, out: str, pages: dict, dpi: int) -> None:
            captured["called"] = True
            captured["pages"] = dict(pages)
            captured["dpi"] = dpi
            captured["input"] = inp
            captured["output"] = out

        class _WriterEngine(EngineBase):
            pass

        engine = _WriterEngine(output_writer=writer)
        result_doc = DocumentResult.from_pages_data(
            {0: [([0.0, 0.0, 1.0, 0.1], "line one")], 1: [([0.0, 0.1, 1.0, 0.2], "")]}
        )

        pages_text = await engine._emit(
            input_path="in.pdf",
            output_path="out.pdf",
            document_result=result_doc,
            dpi=200,
            progress=None,
        )

        assert engine.last_document_result is result_doc
        assert captured["called"] is True
        assert captured["dpi"] == 200
        assert captured["input"] == "in.pdf"
        assert captured["output"] == "out.pdf"
        # Blank-text boxes are filtered out of the pages_text view.
        assert pages_text == {0: ["line one"], 1: []}

    async def test_emits_progress_events(self) -> None:
        events: list[tuple[str, int, int]] = []

        async def cb(stage: str, cur: int, tot: int, msg: str) -> None:
            events.append((stage, cur, tot))

        class _WriterEngine(EngineBase):
            pass

        engine = _WriterEngine(output_writer=_noop_writer)
        result_doc = DocumentResult.from_pages_data({0: [([0.0, 0.0, 1.0, 0.1], "x")]})
        await engine._emit(
            input_path="in.pdf",
            output_path="out.pdf",
            document_result=result_doc,
            dpi=150,
            progress=cb,
        )
        # Expect both embed events with terminal counts.
        assert ("embed", 0, 1) in events
        assert ("embed", 1, 1) in events
