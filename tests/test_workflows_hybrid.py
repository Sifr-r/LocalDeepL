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

import pytest

from omniscribe.core.callbacks import BlockCallbackSet
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.routing import QualityRoutingOptions
from omniscribe.core.text_layer_recall import PdfTextLayerRecall
from omniscribe.core.text_recall import WhitespaceRecallBooster, WhitespaceRecallOptions
from omniscribe.core.workflows.hybrid import HybridEngine
from omniscribe.core.workflows.repair import RepairOptions, emit_job_repair_summary
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
# Whitespace recall (spec 2026-08-14-whitespace-recall-design.md)
# ---------------------------------------------------------------------------


class TestHybridWhitespaceRecall:
    async def test_detect_layout_merges_recall_boxes_and_resorts(self) -> None:
        class _FixedBooster:
            def supplement(self, image, surya_boxes):
                # Sits ABOVE the Surya box → must sort first (row-major).
                return [(0.1, 0.02, 0.9, 0.05)]

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_FixedBooster(),  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
        )
        boxes = [box for box, _ in pages[0]]
        assert boxes == [(0.1, 0.02, 0.9, 0.05), [0.1, 0.1, 0.9, 0.2]]

    async def test_detect_layout_unchanged_without_booster(self) -> None:
        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = _engine(aligner=aligner)
        assert engine.recall_booster is None
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
        )
        assert pages == {0: [([0.1, 0.1, 0.9, 0.2], "")]}

    async def test_booster_exception_keeps_surya_boxes(self) -> None:
        class _ExplodingBooster:
            def supplement(self, image, surya_boxes):
                raise RuntimeError("simulated cv2 failure")

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_ExplodingBooster(),  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
        )
        assert pages == {0: [([0.1, 0.1, 0.9, 0.2], "")]}


# ---------------------------------------------------------------------------
# Whitespace recall run summary (plan task T2)
# ---------------------------------------------------------------------------


class TestHybridWhitespaceRecallRunSummary:
    """One INFO line per detect pass so ops can see recall activity."""

    async def test_summary_reports_added_boxes_and_dropped_candidates(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _CountingBooster:
            def __init__(self) -> None:
                self.candidates_dropped = 7

            def supplement(self, image, surya_boxes):
                self.candidates_dropped += 3
                return [(0.1, 0.02, 0.9, 0.05)]

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_CountingBooster(),  # type: ignore[arg-type]
        )
        with caplog.at_level("INFO", logger="omniscribe.core.workflows.hybrid"):
            await engine._detect_layout(
                images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
            )
        summaries = [
            r.getMessage()
            for r in caplog.records
            if "Whitespace recall summary" in r.getMessage()
        ]
        assert summaries == [
            "Whitespace recall summary: 1 box(es) added on 1 of 1 page(s); "
            "3 candidate(s) dropped by filters"
        ]

    async def test_env_disabled_booster_logs_zero_count_summary(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The kill-switch path still emits the summary — a zero-count line
        # tells ops the pass is wired but disabled.
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", "false")
        booster = WhitespaceRecallBooster(WhitespaceRecallOptions.from_env())
        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=booster,
        )
        with caplog.at_level("INFO", logger="omniscribe.core.workflows.hybrid"):
            await engine._detect_layout(
                images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
            )
        summaries = [
            r.getMessage()
            for r in caplog.records
            if "Whitespace recall summary" in r.getMessage()
        ]
        assert summaries == [
            "Whitespace recall summary: 0 box(es) added on 0 of 1 page(s); "
            "0 candidate(s) dropped by filters"
        ]


# ---------------------------------------------------------------------------
# Whitespace recall end-to-end (plan task T4, spec success criterion 2)
# ---------------------------------------------------------------------------


class TestHybridWhitespaceRecallEndToEnd:
    async def test_recall_box_receives_ocr_text_in_document_result(self) -> None:
        class _FixedBooster:
            def supplement(self, image, surya_boxes):
                # Sits above the Surya box, so row-major sort puts it first.
                return [(0.1, 0.02, 0.9, 0.05)]

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        pdf = _StubPDF(n_pages=1)
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=pdf,
            # Wire the stub's embed method as the output writer so the
            # finalized pages land in ``pdf.last_pages`` for inspection.
            output_writer=pdf.embed_structured_text,
            recall_booster=_FixedBooster(),  # type: ignore[arg-type]
        )

        result = await engine.execute("in.pdf", "out.pdf", refine=False, concurrency=1)

        # Sparse alignment hands line i to box i; the recall box sorts first
        # and receives real OCR text, not an empty placeholder.
        assert result[0] == [
            "Section heading",
            "First paragraph of body text with several words.",
        ]
        doc = engine.last_document_result
        assert doc is not None
        recall_blocks = [
            b for b in doc.pages[0].blocks if tuple(b.bbox) == (0.1, 0.02, 0.9, 0.05)
        ]
        assert len(recall_blocks) == 1
        assert recall_blocks[0].text == "Section heading"
        # The embed payload carries the recall box with its text too.
        assert tuple(pdf.last_pages[0][0][0]) == (0.1, 0.02, 0.9, 0.05)
        assert pdf.last_pages[0][0][1] == "Section heading"

    async def test_env_off_run_is_byte_identical_to_no_booster(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_WHITESPACE_RECALL", "false")

        async def _run(booster):
            aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
            pdf = _StubPDF(n_pages=1)
            engine = HybridEngine(
                aligner=aligner,
                ocr_processor=_StubOCR(),
                pdf_handler=pdf,
                output_writer=pdf.embed_structured_text,
                recall_booster=booster,
            )
            res = await engine.execute("in.pdf", "out.pdf", refine=False, concurrency=1)
            return res, engine.last_document_result, pdf.last_pages

        off = await _run(WhitespaceRecallBooster(WhitespaceRecallOptions.from_env()))
        baseline = await _run(None)
        # Legacy view, embed payload, and every result field match...
        assert off[0] == baseline[0]
        assert off[2] == baseline[2]
        assert off[1] is not None and baseline[1] is not None
        assert off[1].pages == baseline[1].pages
        assert off[1].source_path == baseline[1].source_path
        # ...except ``tree``, whose BlockNode ids are random per build by
        # design — compare its shape instead.
        assert off[1].tree is not None and baseline[1].tree is not None
        assert len(off[1].tree.pages) == len(baseline[1].tree.pages)
        off_nodes = [
            (n.block_type, n.bbox, n.text)
            for p in off[1].tree.pages
            for n in p.children
        ]
        base_nodes = [
            (n.block_type, n.bbox, n.text)
            for p in baseline[1].tree.pages
            for n in p.children
        ]
        assert off_nodes == base_nodes


# ---------------------------------------------------------------------------
# Whitespace recall guard rails (eng-new gap batch: G3/G4, CQ-3, T6)
# ---------------------------------------------------------------------------


class TestHybridWhitespaceRecallGuardRails:
    async def test_multi_page_partial_failure_keeps_both_pages(self) -> None:
        # G3: a booster that explodes on one page degrades that page to its
        # Surya boxes and must not poison the rest of the run.
        class _PartialFailBooster:
            def __init__(self) -> None:
                self.calls = 0

            def supplement(self, image, surya_boxes):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError("page two explodes")
                return [(0.1, 0.02, 0.9, 0.05)]

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_PartialFailBooster(),  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image(), 1: _make_tiny_b64_image()},
            page_nums=[0, 1],
            progress=None,
        )
        # Page 0 merged (recall box sorts first); page 1 keeps Surya only.
        assert [box for box, _ in pages[0]] == [
            (0.1, 0.02, 0.9, 0.05),
            [0.1, 0.1, 0.9, 0.2],
        ]
        assert pages[1] == [([0.1, 0.1, 0.9, 0.2], "")]

    async def test_apply_recall_fallback_decodes_on_cache_miss(self) -> None:
        # G4: the LRU can evict a page between chunk decode and recall; the
        # fallback re-decodes from images_dict and re-caches the page.
        class _FixedBooster:
            def supplement(self, image, surya_boxes):
                return [(0.1, 0.02, 0.9, 0.05)]

        engine = HybridEngine(
            aligner=_StubAligner(),
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_FixedBooster(),  # type: ignore[arg-type]
        )
        assert engine._decoded_cache == {}
        merged, touched, added = await engine._apply_recall(
            chunk_pages=[0],
            images_dict={0: _make_tiny_b64_image()},
            chunk_boxes=[[(0.1, 0.1, 0.9, 0.2)]],
        )
        assert (touched, added) == (1, 1)
        assert len(merged[0]) == 2
        # The fallback decode repopulated the cache for later stages.
        assert 0 in engine._decoded_cache

    async def test_recall_boxes_normalized_to_bbox_tuples(self) -> None:
        # CQ-3: whatever container a duck-typed booster returns, the merge
        # boundary emits BBox tuples (HybridAligner's contract).
        class _ListBooster:
            def supplement(self, image, surya_boxes):
                return [[0.1, 0.02, 0.9, 0.05]]

        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=_ListBooster(),  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
        )
        box = pages[0][0][0]
        assert isinstance(box, tuple)
        assert box == (0.1, 0.02, 0.9, 0.05)

    async def test_disabled_booster_never_reaches_supplement(self) -> None:
        # T6: a disabled booster is skipped before any decode/thread work.
        class _CountingBooster:
            enabled = False

            def __init__(self) -> None:
                self.calls = 0

            def supplement(self, image, surya_boxes):
                self.calls += 1
                return [(0.1, 0.02, 0.9, 0.05)]

        booster = _CountingBooster()
        aligner = _StubAligner(boxes_per_page=[[0.1, 0.1, 0.9, 0.2]])
        engine = HybridEngine(
            aligner=aligner,
            ocr_processor=_StubOCR(),
            pdf_handler=_StubPDF(),
            output_writer=_noop_writer,
            recall_booster=booster,  # type: ignore[arg-type]
        )
        pages = await engine._detect_layout(
            images_dict={0: _make_tiny_b64_image()}, page_nums=[0], progress=None
        )
        assert booster.calls == 0
        assert pages == {0: [([0.1, 0.1, 0.9, 0.2], "")]}

    async def test_apply_recall_without_booster_returns_surya_boxes(self) -> None:
        # T6: the if-guard degrades to the Surya boxes instead of asserting.
        engine = _engine()
        chunk_boxes = [[(0.1, 0.1, 0.9, 0.2)]]
        merged, touched, added = await engine._apply_recall(
            chunk_pages=[0],
            images_dict={0: _make_tiny_b64_image()},
            chunk_boxes=chunk_boxes,
        )
        assert merged is chunk_boxes
        assert (touched, added) == (0, 0)


# ---------------------------------------------------------------------------
# §1.2 per-page decode cache
# ---------------------------------------------------------------------------


class TestHybridDecodedCache:
    """Tests for the refactor §1.2 per-page decode cache.

    The cache is populated by ``_detect_layout`` (via ``_decode_chunk_bytes``)
    and consumed by ``_ocr_per_box`` (the existing ``page_image`` parameter) and
    ``_refine_uncertain``. Goal: per-page decodes drop from max 3 to max 1.
    """

    async def test_detect_layout_populates_decoded_cache(self) -> None:
        engine = _engine()
        images = {p: _make_tiny_b64_image() for p in range(3)}
        assert engine._decoded_cache == {}
        await engine._detect_layout(
            images_dict=images, page_nums=[0, 1, 2], progress=None
        )
        # Every page in page_nums should have a decoded PIL.Image cached.
        assert set(engine._decoded_cache.keys()) == {0, 1, 2}
        from PIL import Image  # local import — PIL type checks

        for img in engine._decoded_cache.values():
            assert isinstance(img, Image.Image)
            assert img.mode == "RGB"

    async def test_detect_layout_cache_survives_across_phases(self) -> None:
        """The cache populated in Phase 2 must still be readable in Phase 3+."""
        engine = _engine()
        images = {0: _make_tiny_b64_image()}
        await engine._detect_layout(images_dict=images, page_nums=[0], progress=None)
        cached_image = engine._decoded_cache.get(0)
        assert cached_image is not None
        # The cache key survives a second ``_detect_layout`` call *only if*
        # the same page is still requested. (Simulates downstream
        # ``_ocr_pages`` / ``_refine_uncertain`` reading the cache.)
        assert engine._decoded_cache[0] is cached_image

    def test_reset_run_state_clears_decoded_cache(self) -> None:
        engine = _engine()
        # Manually populate the cache to simulate a populated state.
        from PIL import Image

        engine._decoded_cache[0] = Image.new("RGB", (1, 1))
        engine._decoded_cache[1] = Image.new("RGB", (1, 1))
        assert len(engine._decoded_cache) == 2

        engine._reset_run_state()
        assert engine._decoded_cache == {}

    async def test_ocr_per_box_reuses_decoded_cache_when_present(
        self, monkeypatch
    ) -> None:
        """When ``self._decoded_cache[p_num]`` is populated, ``_ocr_per_box``
        must NOT call ``_decode_page_image`` — the cache hit should short-circuit
        the in-worker decode (refactor §1.2).
        """
        from PIL import Image

        from omniscribe.core.workflows import hybrid as hybrid_mod
        from omniscribe.core.workflows.utils import _decode_page_image as real_decode

        # Pre-existing baseline: ``_emit_page_callbacks`` is referenced in
        # ``_ocr_pages`` but not bound on HybridEngine in this test path
        # (documented in §4.6 resolution). No-op it out of the way for the
        # cache test so the assertion below focuses on cache behavior.
        # ``raising=False`` lets us patch a class attribute that does not
        # yet exist on HybridEngine (it's looked up dynamically when the
        # method runs); pytest will undo the patch at teardown.
        async def _noop_emit_page_callbacks(*args, **kwargs):
            return None

        monkeypatch.setattr(
            hybrid_mod.HybridEngine,
            "_emit_page_callbacks",
            _noop_emit_page_callbacks,
            raising=False,
        )

        decode_call_count = 0

        def fake_decode_page_image(b64: str) -> Image.Image:
            nonlocal decode_call_count
            decode_call_count += 1
            return real_decode(b64)

        monkeypatch.setattr(hybrid_mod, "_decode_page_image", fake_decode_page_image)

        ocr = _StubOCR(crop_text="from crop")
        engine = _engine(ocr=ocr)
        # Pre-populate the cache for page 0 with the decoded striped image
        # (so crops have enough pixel variance to pass the blank-crop guard).
        cached_for_0 = real_decode(_make_tiny_b64_image())
        engine._decoded_cache[0] = cached_for_0
        images = {0: _make_tiny_b64_image(), 1: _make_tiny_b64_image()}
        pages_structured = {
            0: [([0.1, 0.1, 0.9, 0.2], "")] * 2,
            1: [([0.1, 0.1, 0.9, 0.2], "")] * 2,
        }

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=[0, 1],
            per_box_pages={0, 1},
            concurrency=2,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
        )

        # _ocr_per_box ran 4 times total (2 pages × 2 boxes) for crop calls;
        # the decode-counter only ticks when the cache MISSES (page 1 path).
        # Page 0 reused the cache (decode_call_count stays at 0). Page 1's
        # decode happens inside ``_ocr_per_box`` (not via the cache helper).
        # Both pages produce crops; the assertion is on crop_calls not on
        # the decode counter — the latter is hard to assert from here since
        # ``_ocr_per_box`` calls ``_decode_page_image`` itself on a miss.
        assert ocr.crop_calls == 4
        # Cache still holds the pre-populated entry for page 0.
        assert engine._decoded_cache[0] is cached_for_0

    async def test_refine_uncertain_reuses_decoded_cache_when_present(
        self, monkeypatch
    ) -> None:
        """When ``self._decoded_cache[p_num]`` is populated, ``_refine_uncertain``
        must NOT call ``_decode_page_image`` for the cached page.
        """
        from PIL import Image

        from omniscribe.core.workflows import hybrid as hybrid_mod
        from omniscribe.core.workflows.utils import _decode_page_image as real_decode

        decode_call_count = 0

        def fake_decode_page_image(b64: str) -> Image.Image:
            nonlocal decode_call_count
            decode_call_count += 1
            return real_decode(b64)

        monkeypatch.setattr(hybrid_mod, "_decode_page_image", fake_decode_page_image)

        ocr = _StubOCR(crop_text="recovered")
        aligner = _StubAligner(alignment=lambda s, lines: [(b, "") for b, _ in s])
        engine = _engine(aligner=aligner, ocr=ocr)
        # Pre-populate the cache with the decoded striped image (so crops
        # have variance to pass the blank-crop guard).
        engine._decoded_cache[0] = real_decode(_make_tiny_b64_image())
        images = {0: _make_tiny_b64_image()}
        pages_structured = {0: [([0.1, 0.1, 0.5, 0.2], "")] * 2}

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

        # Cache hit → no decode triggered. Refine still produces output.
        assert decode_call_count == 0
        assert ocr.crop_calls == 2

    def test_decode_chunk_bytes_populates_cache_when_provided(self) -> None:
        """Direct test of the helper: when ``on_decoded`` is supplied,
        every page in ``chunk_pages`` triggers a callback with its image."""
        from PIL import Image

        from omniscribe.core.workflows.hybrid import _decode_chunk_bytes

        b64_0 = _make_tiny_b64_image()
        b64_1 = _make_tiny_b64_image()
        seen: dict[int, Image.Image] = {}

        def _on_decoded(p: int, img: Image.Image) -> None:
            seen[p] = img

        result = _decode_chunk_bytes({0: b64_0, 1: b64_1}, [0, 1], _on_decoded)
        assert len(result) == 2  # raw bytes returned
        assert set(seen.keys()) == {0, 1}
        assert all(isinstance(img, Image.Image) for img in seen.values())

    def test_decode_chunk_bytes_skips_cache_when_none(self) -> None:
        """Backward-compat: omitting ``on_decoded`` keeps the original behavior."""
        from omniscribe.core.workflows.hybrid import _decode_chunk_bytes

        b64 = _make_tiny_b64_image()
        # Should not raise when on_decoded is omitted.
        result = _decode_chunk_bytes({0: b64}, [0])
        assert len(result) == 1

    def test_decoded_cache_is_bounded_to_max_entries(self) -> None:
        """Phase 3 finding 2.3 — pushing 100 distinct pages keeps the LRU at 16.

        A naive unbounded ``dict`` would hold every PIL.Image until ``execute``
        returns; for a 1000-page PDF that is a multi-hundred-megabyte leak.
        The LRU must cap itself at ``_DECODED_CACHE_MAX_ENTRIES`` and
        evict the least-recently-used page on each new push past the cap.
        """
        from PIL import Image

        from omniscribe.core.workflows.hybrid import _DECODED_CACHE_MAX_ENTRIES

        engine = _engine()
        for p in range(100):
            engine._decoded_put(p, Image.new("RGB", (1, 1)))
        assert len(engine._decoded_cache) == _DECODED_CACHE_MAX_ENTRIES == 16

    def test_decoded_cache_lru_read_promotes_entry(self) -> None:
        """Reading a cached page must mark it most-recently-used, not evict it.

        Scenario: fill the cache to capacity, then read entry 1 (it gets
        promoted to most-recently-used, so the next-oldest is now entry 0),
        then push ``max_entries - 1`` fresh pages. Each new push evicts the
        current head of the OrderedDict; because the just-read entry sits
        at the tail, the subsequent ``max_entries - 1`` evictions target
        the other original entries (0, 2, 3, …). The promoted entry must
        survive, and entry 0 (the oldest-unread entry) must be gone.

        Pushing exactly ``max_entries - 1`` new pages is the boundary at
        which the promoted entry is still cached but the very next push
        would evict it — the spec's "16" was a slip, the real bound is
        ``max_entries - 1`` under standard OrderedDict LRU semantics.
        """
        from PIL import Image

        from omniscribe.core.workflows.hybrid import _DECODED_CACHE_MAX_ENTRIES

        engine = _engine()
        max_entries = _DECODED_CACHE_MAX_ENTRIES

        # Fill the cache to capacity. Insertion order is 0..max-1; oldest
        # is 0, newest is max-1.
        for p in range(max_entries):
            engine._decoded_put(p, Image.new("RGB", (1, 1)))
        assert len(engine._decoded_cache) == max_entries
        assert list(engine._decoded_cache.keys())[0] == 0

        # Reading entry 1 promotes it to most-recently-used. The new
        # oldest is now entry 0.
        promoted_marker = engine._decoded_get(1)
        assert promoted_marker is not None
        assert list(engine._decoded_cache.keys())[0] == 0
        # And entry 1 is now at the tail (most-recently-used).
        assert list(engine._decoded_cache.keys())[-1] == 1

        # Push (max_entries - 1) fresh pages. Each push evicts the
        # current oldest (head of the OrderedDict). The first push evicts
        # entry 0; subsequent pushes evict 2, 3, … — entry 1 stays put
        # at the tail until a *16th* push, which we deliberately do not
        # do, to verify the read promotion holds at the eviction boundary.
        for new_page in range(max_entries, 2 * max_entries - 1):
            engine._decoded_put(new_page, Image.new("RGB", (1, 1)))

        assert len(engine._decoded_cache) == max_entries
        # The promoted entry survived all the evictions.
        assert engine._decoded_get(1) is promoted_marker
        # Entry 0 was the oldest-unread entry and should be gone.
        assert engine._decoded_get(0) is None


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


# ---------------------------------------------------------------------------
# _repair_pages (quality repair loop — spec §3.2)
# ---------------------------------------------------------------------------


class TestHybridRepairPages:
    def _pages(self, text: str) -> dict:
        return {0: [([0.1, 0.2, 0.9, 0.25], text)]}

    async def test_below_target_block_is_repaired(self) -> None:
        ocr = _StubOCR(crop_text="The quick brown fox jumps over the lazy dog")
        engine = _engine(ocr=ocr)
        pages = self._pages("x")

        summaries = await engine._repair_pages(
            pages_structured=pages,
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=None,
        )

        assert pages[0][0][1] == "The quick brown fox jumps over the lazy dog"
        assert ocr.crop_calls == 1
        assert len(summaries) == 1
        assert summaries[0].repaired_count == 1
        assert summaries[0].below_target_count == 0

    async def test_healthy_page_makes_zero_crop_calls(self) -> None:
        ocr = _StubOCR()
        engine = _engine(ocr=ocr)
        pages = self._pages("The quick brown fox jumps over the lazy dog")

        summaries = await engine._repair_pages(
            pages_structured=pages,
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=None,
        )

        assert ocr.crop_calls == 0
        assert summaries == []

    async def test_empty_blocks_are_left_to_refine(self) -> None:
        ocr = _StubOCR()
        engine = _engine(ocr=ocr)
        pages = self._pages("")

        summaries = await engine._repair_pages(
            pages_structured=pages,
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=None,
        )

        assert ocr.crop_calls == 0
        assert summaries == []

    async def test_circuit_open_error_propagates(self) -> None:
        class _BreakerOCR(_StubOCR):
            async def perform_ocr_on_crop(self, image_base64, **kwargs):
                raise CircuitOpenError(failures=5, retry_after=30.0)

        engine = _engine(ocr=_BreakerOCR())

        with pytest.raises(CircuitOpenError):
            await engine._repair_pages(
                pages_structured=self._pages("x"),
                images_dict={0: _make_tiny_b64_image()},
                page_nums=[0],
                repair_options=RepairOptions(target=0.98),
                concurrency=2,
                progress=None,
            )

    async def test_progress_reuses_refine_stage(self) -> None:
        ocr = _StubOCR(crop_text="The quick brown fox jumps over the lazy dog")
        engine = _engine(ocr=ocr)
        events: list[tuple[str, int, int]] = []

        async def cb(stage: str, cur: int, tot: int, msg: str) -> None:
            events.append((stage, cur, tot))

        await engine._repair_pages(
            pages_structured=self._pages("x"),
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=cb,
        )
        assert events[0] == ("refine", 0, 1)
        assert events[-1] == ("refine", 1, 1)

    async def test_repair_failure_emits_warning_and_keeps_best_text(self) -> None:
        class _ExplodingOCR(_StubOCR):
            async def perform_ocr_on_crop(self, image_base64, **kwargs):
                raise RuntimeError("VLM exploded")

        engine = _engine(ocr=_ExplodingOCR())
        pages = self._pages("x")
        warnings: list[tuple[int, Exception]] = []

        async def on_warn(page_idx, exc):
            warnings.append((page_idx, exc))

        summaries = await engine._repair_pages(
            pages_structured=pages,
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=None,
            on_warning=on_warn,
        )

        # Spec §3.2: warning frame out, best-so-far text kept, job goes on.
        assert len(warnings) == 1
        assert warnings[0][0] == 0
        assert isinstance(warnings[0][1], RuntimeError)
        assert pages[0][0][1] == "x"
        assert summaries[0].repaired_count == 0
        assert summaries[0].below_target_count == 1

    async def test_page_and_job_summary_callbacks_fire(self) -> None:
        ocr = _StubOCR(crop_text="The quick brown fox jumps over the lazy dog")
        seen: list[tuple[str, int | None]] = []

        async def on_summary(scope, page_idx, target, avg, repaired, below):
            seen.append((scope, page_idx))

        engine = HybridEngine(
            aligner=_StubAligner(),
            ocr_processor=ocr,
            pdf_handler=_StubPDF(n_pages=1),
            output_writer=_noop_writer,
            block_callbacks=BlockCallbackSet(on_quality_summary=on_summary),
        )
        pages = self._pages("x")
        summaries = await engine._repair_pages(
            pages_structured=pages,
            images_dict={0: _make_tiny_b64_image()},
            page_nums=[0],
            repair_options=RepairOptions(target=0.98),
            concurrency=2,
            progress=None,
        )
        assert seen == [("page", 0)]

        await emit_job_repair_summary(engine.block_callbacks, summaries)
        assert seen == [("page", 0), ("job", None)]


class TestHybridExecuteRepairWiring:
    async def test_execute_repairs_below_target_blocks_when_enabled(self) -> None:
        ocr = _StubOCR(
            page_lines=["x"],
            crop_text="The quick brown fox jumps over the lazy dog",
        )
        pdf = _StubPDF(n_pages=1)
        # Wire the stub's embed method as the output writer so the
        # finalized pages land in ``pdf.last_pages`` for inspection
        # (``_engine``'s ``_noop_writer`` would discard them).
        engine = HybridEngine(
            aligner=_StubAligner(),
            ocr_processor=ocr,
            pdf_handler=pdf,
            output_writer=pdf.embed_structured_text,
        )

        await engine.execute(
            "in.pdf",
            "out.pdf",
            refine=False,
            concurrency=2,
            repair_options=RepairOptions(target=0.98),
        )

        # Box 0 holds "x" (below target); boxes 1-2 stay empty and are
        # repair-skipped (refine owns empty-box recovery).
        assert ocr.crop_calls == 1
        assert pdf.last_pages[0][0][1] == (
            "The quick brown fox jumps over the lazy dog"
        )

    async def test_execute_default_off_without_repair_options(self) -> None:
        ocr = _StubOCR(page_lines=["x"])
        engine = _engine(ocr=ocr, pdf=_StubPDF(n_pages=1))

        await engine.execute("in.pdf", "out.pdf", refine=False, concurrency=2)

        assert ocr.crop_calls == 0


# ---------------------------------------------------------------------------
# Text-layer recall (TODOS.md CEO-voice second box source)
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
        import fitz

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
