"""
Direct unit tests for ``HybridEngine``'s staged methods.

PR-C decomposed ``HybridEngine.execute()`` into five phases
(``_convert_pages`` → ``_detect_layout`` → ``_select_dense_pages`` →
``_ocr_pages`` → ``_refine_pages`` → ``_finalize``). These tests call each
phase in isolation so failures point at a single stage rather than the full
e2e flow. ``test_pipeline.py`` still covers the public surface end-to-end;
this file is the per-phase drill-down.
"""

from __future__ import annotations

from omniscribe.core.routing import QualityRoutingOptions
from omniscribe.core.workflows.hybrid import HybridEngine
from tests.conftest import _StubOCR
from tests.test_pipeline import _make_tiny_b64_image, _StubAligner, _StubPDF


def _noop_writer(_in: str, _out: str, _pages: dict, _dpi: int) -> None:
    """Output writer that discards its arguments. Tests don't inspect PDF output."""


def _engine(
    *,
    aligner: _StubAligner | None = None,
    ocr: _StubOCR | None = None,
    pdf: _StubPDF | None = None,
) -> HybridEngine:
    """Construct a HybridEngine wired to the standard stubs."""
    return HybridEngine(
        aligner=aligner or _StubAligner(),
        ocr_processor=ocr or _StubOCR(),
        pdf_handler=pdf or _StubPDF(),
        output_writer=_noop_writer,
    )


# ---------------------------------------------------------------------------
# _convert_pages
# ---------------------------------------------------------------------------


class TestHybridConvertPages:
    async def test_returns_images_page_nums_and_empty_metadata(self) -> None:
        engine = _engine(pdf=_StubPDF(n_pages=3))
        images, page_nums, metadata = await engine._convert_pages(
            input_path="in.pdf",
            dpi=150,
            max_image_dim=1024,
            pages=None,
            preprocessing_options=None,
            progress=None,
        )
        assert page_nums == [0, 1, 2]
        assert set(images.keys()) == {0, 1, 2}
        assert metadata == {}

    async def test_applies_page_range_filter(self) -> None:
        engine = _engine(pdf=_StubPDF(n_pages=10))
        images, page_nums, _ = await engine._convert_pages(
            input_path="in.pdf",
            dpi=150,
            max_image_dim=1024,
            pages="1-2,5",
            preprocessing_options=None,
            progress=None,
        )
        # 1-indexed input → 0-indexed output.
        assert page_nums == [0, 1, 4]
        assert set(images.keys()) == {0, 1, 4}

    async def test_no_preprocessing_when_disabled(self) -> None:
        # A preprocessor passed in but with `enabled=False` must be skipped
        # entirely; the call returns the un-preprocessed images and empty metadata.
        class _RecordingPreprocessor:
            def __init__(self) -> None:
                self.called = False

            def preprocess(self, images, options):
                self.called = True
                return _PreprocessResult(images, {})

        preprocessor = _RecordingPreprocessor()

        from omniscribe.core.preprocessing import PagePreprocessingOptions

        engine = HybridEngine(
            aligner=_StubAligner(),
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(n_pages=2),
            output_writer=_noop_writer,
            page_preprocessor=preprocessor,  # type: ignore[arg-type]
        )
        _, _, metadata = await engine._convert_pages(
            input_path="in.pdf",
            dpi=150,
            max_image_dim=1024,
            pages=None,
            preprocessing_options=PagePreprocessingOptions(enabled=False),
            progress=None,
        )
        assert preprocessor.called is False
        assert metadata == {}

    async def test_emits_progress_events(self) -> None:
        engine = _engine(pdf=_StubPDF(n_pages=2))
        events: list[tuple[str, int, int]] = []

        async def cb(stage: str, cur: int, tot: int, msg: str) -> None:
            events.append((stage, cur, tot))

        await engine._convert_pages(
            input_path="in.pdf",
            dpi=150,
            max_image_dim=1024,
            pages=None,
            preprocessing_options=None,
            progress=cb,
        )
        # Convert emits (0,1) at start and (1,1) at end of the stage.
        assert ("convert", 0, 1) in events
        assert ("convert", 1, 1) in events


# ---------------------------------------------------------------------------
# _detect_layout
# ---------------------------------------------------------------------------


class TestHybridDetectLayout:
    async def test_seeds_each_page_with_detected_boxes(self) -> None:
        aligner = _StubAligner(
            boxes_per_page=[[0.1, 0.1, 0.9, 0.2], [0.1, 0.3, 0.9, 0.4]]
        )
        engine = _engine(aligner=aligner)
        images = {0: _make_tiny_b64_image()}
        pages_structured = await engine._detect_layout(
            images_dict=images, page_nums=[0], progress=None
        )
        assert pages_structured == {
            0: [([0.1, 0.1, 0.9, 0.2], ""), ([0.1, 0.3, 0.9, 0.4], "")]
        }

    async def test_batches_by_detect_chunk_size(self) -> None:
        # Detect chunks at 10; 25 pages should produce batches of [10, 10, 5].
        batch_sizes: list[int] = []

        class _ChunkTracker(_StubAligner):
            def get_detected_boxes_batch(self, images):
                batch_sizes.append(len(images))
                return super().get_detected_boxes_batch(images)

        page_nums = list(range(25))
        images = {p: _make_tiny_b64_image() for p in page_nums}
        engine = _engine(aligner=_ChunkTracker())
        await engine._detect_layout(
            images_dict=images, page_nums=page_nums, progress=None
        )
        assert batch_sizes == [10, 10, 5]

    async def test_emits_detect_progress(self) -> None:
        events: list[tuple[str, int, int]] = []

        async def cb(stage: str, cur: int, tot: int, msg: str) -> None:
            events.append((stage, cur, tot))

        engine = _engine()
        await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=cb
        )
        assert ("detect", 0, 1) in events
        assert ("detect", 1, 1) in events


# ---------------------------------------------------------------------------
# _select_dense_pages
# ---------------------------------------------------------------------------


class TestHybridSelectDensePages:
    @staticmethod
    def _structured(
        n_boxes_per_page: dict[int, int],
    ) -> dict[int, list[tuple[list[float], str]]]:
        return {
            p: [([0.1, 0.1, 0.9, 0.2], "") for _ in range(n)]
            for p, n in n_boxes_per_page.items()
        }

    def test_auto_above_threshold_picks_dense(self) -> None:
        engine = _engine()
        structured = self._structured({0: 5, 1: 2})
        result = engine._select_dense_pages(
            pages_structured=structured,
            page_nums=[0, 1],
            dense_mode="auto",
            dense_threshold=3,
        )
        assert result == {0}

    def test_auto_at_or_below_threshold_keeps_sparse(self) -> None:
        engine = _engine()
        structured = self._structured({0: 3, 1: 1})
        result = engine._select_dense_pages(
            pages_structured=structured,
            page_nums=[0, 1],
            dense_mode="auto",
            dense_threshold=3,
        )
        assert result == set()

    def test_always_selects_every_page(self) -> None:
        engine = _engine()
        structured = self._structured({0: 1, 1: 2})
        result = engine._select_dense_pages(
            pages_structured=structured,
            page_nums=[0, 1],
            dense_mode="always",
            dense_threshold=999,
        )
        assert result == {0, 1}


# ---------------------------------------------------------------------------
# _ocr_pages
# ---------------------------------------------------------------------------


class TestHybridOCRPages:
    async def test_dispatches_sparse_to_full_page_ocr(self) -> None:
        ocr = _StubOCR()
        aligner = _StubAligner(alignment=lambda s, lines: [(b, lines[0]) for b, _ in s])
        engine = _engine(aligner=aligner, ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "")] * 3}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=[0],
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
        )

        assert ocr.page_calls == 1
        assert ocr.crop_calls == 0
        # Aligner wired all 3 boxes to the first OCR line.
        assert all(text == ocr.page_lines[0] for _, text in pages_structured[0])

    async def test_dispatches_dense_to_per_box_ocr(self) -> None:
        ocr = _StubOCR(crop_text="from crop")
        engine = _engine(ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "")] * 3}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=[0],
            per_box_pages={0},
            concurrency=2,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
        )

        assert ocr.page_calls == 0
        assert ocr.crop_calls == 3
        assert all(text == "from crop" for _, text in pages_structured[0])

    async def test_handles_empty_full_page_ocr_response(self) -> None:
        # When the full-page LLM returns [], _ocr_pages should leave the
        # page's structured boxes untouched (no aligner call, no failure).
        class _EmptyOCR(_StubOCR):
            async def perform_ocr(self, image_base64, **kwargs):
                self.page_calls += 1
                return []

        ocr = _EmptyOCR()
        engine = _engine(ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        original_boxes = [([0.1, 0.1, 0.9, 0.2], "preserved")] * 3
        pages_structured = {0: list(original_boxes)}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=[0],
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
        )

        assert ocr.page_calls == 1
        # Boxes preserved exactly when OCR returned no lines.
        assert pages_structured[0] == original_boxes

    async def test_records_failure_and_invokes_warning(self) -> None:
        class _FailOCR(_StubOCR):
            async def perform_ocr(self, image_base64, **kwargs):
                raise RuntimeError("simulated OCR timeout")

        warnings: list[tuple[int, BaseException]] = []

        async def on_warning(page_index: int, exc: BaseException) -> None:
            warnings.append((page_index, exc))

        engine = _engine(ocr=_FailOCR())
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "")] * 3}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=[0],
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=on_warning,
        )

        assert engine.last_failed_pages == [0]
        assert len(warnings) == 1
        assert warnings[0][0] == 0
        assert isinstance(warnings[0][1], RuntimeError)


# ---------------------------------------------------------------------------
# _refine_pages
# ---------------------------------------------------------------------------


class TestHybridRefinePages:
    async def test_skips_when_all_pages_are_dense(self) -> None:
        ocr = _StubOCR(crop_text="should not appear")
        engine = _engine(ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "")] * 3}

        await engine._refine_pages(
            pages_structured=pages_structured,
            images_dict=images,
            page_nums=[0],
            per_box_pages={0},
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
        )
        assert ocr.crop_calls == 0
        assert all(text == "" for _, text in pages_structured[0])

    async def test_refines_empty_refinable_boxes_on_sparse_pages(self) -> None:
        ocr = _StubOCR(crop_text="recovered")
        # Aligner fills every box with empty text — perfect refine candidate.
        aligner = _StubAligner(alignment=lambda s, lines: [(b, "") for b, _ in s])
        engine = _engine(aligner=aligner, ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "")] * 3}

        await engine._refine_pages(
            pages_structured=pages_structured,
            images_dict=images,
            page_nums=[0],
            per_box_pages=set(),
            concurrency=2,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
        )

        assert ocr.crop_calls == 3
        assert all(text == "recovered" for _, text in pages_structured[0])

    async def test_skips_thin_or_tiny_boxes_via_refinable_gate(self) -> None:
        ocr = _StubOCR(crop_text="x")
        engine = _engine(ocr=ocr)
        images = {0: _make_tiny_b64_image()}
        # One refinable box, one thin rule line, one tiny decoration.
        pages_structured = {
            0: [
                ([0.1, 0.1, 0.5, 0.2], ""),  # refinable
                ([0.1, 0.3, 0.9, 0.301], ""),  # thin: height < 0.008
                ([0.1, 0.5, 0.105, 0.51], ""),  # tiny: width < 0.03
            ]
        }

        await engine._refine_pages(
            pages_structured=pages_structured,
            images_dict=images,
            page_nums=[0],
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
        )
        # Only the refinable box gets a crop call.
        assert ocr.crop_calls == 1


# ---------------------------------------------------------------------------
# _finalize
# ---------------------------------------------------------------------------


class TestHybridFinalize:
    async def test_quality_routing_runs_when_enabled(self) -> None:
        engine = _engine()
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "hello")]}

        await engine._finalize(
            input_path="in.pdf",
            output_path="out.pdf",
            pages_structured=pages_structured,
            page_nums=[0],
            preprocessing_metadata={},
            spellcheck="none",
            cross_page=False,
            quality_routing_options=QualityRoutingOptions(enabled=True),
            dpi=150,
            progress=None,
        )

        assert engine.last_document_result is not None
        routing = engine.last_document_result.pages[0].metadata.get("routing")
        assert routing is not None
        assert routing["enabled"] is True

    async def test_quality_routing_skipped_when_disabled(self) -> None:
        engine = _engine()
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "hello")]}

        await engine._finalize(
            input_path="in.pdf",
            output_path="out.pdf",
            pages_structured=pages_structured,
            page_nums=[0],
            preprocessing_metadata={},
            spellcheck="none",
            cross_page=False,
            quality_routing_options=QualityRoutingOptions(enabled=False),
            dpi=150,
            progress=None,
        )

        routing = engine.last_document_result.pages[0].metadata.get("routing")
        assert routing is None

    async def test_quality_routing_skipped_when_options_none(self) -> None:
        # No options at all → routing never runs, document is emitted unchanged.
        engine = _engine()
        pages_structured = {0: [([0.1, 0.1, 0.9, 0.2], "hello")]}

        await engine._finalize(
            input_path="in.pdf",
            output_path="out.pdf",
            pages_structured=pages_structured,
            page_nums=[0],
            preprocessing_metadata={},
            spellcheck="none",
            cross_page=False,
            quality_routing_options=None,
            dpi=150,
            progress=None,
        )

        routing = engine.last_document_result.pages[0].metadata.get("routing")
        assert routing is None
        # Writer was still called.
        assert engine.last_document_result is not None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


# Used in test_no_preprocessing_when_disabled to keep the preprocessor stub
# self-contained; the real result type is a dataclass imported from
# preprocessing.py but we don't depend on its shape here.
class _PreprocessResult:
    def __init__(self, images, metadata):
        self.images = images
        self.metadata = metadata
