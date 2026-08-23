"""Quality repair loop (spec P1): frames, loop logic, engine + API wiring."""

from __future__ import annotations

import base64
import io

import pytest

from omniscribe.api.routers.websocket import ConnectionManager
from omniscribe.api.services.progress import FrameType, ProgressService
from omniscribe.core.callbacks import BlockCallbackSet
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.workflows.hybrid import HybridEngine
from omniscribe.core.workflows.repair import (
    PageRepairSummary,
    QualityRepairLoop,
    RepairOptions,
    emit_job_repair_summary,
)
from omniscribe.core.workflows.utils import _estimate_confidence
from tests.conftest import _StubOCR
from tests.core.test_pipeline import _make_tiny_b64_image, _StubAligner, _StubPDF
from tests.core.workflows.test_workflows_hybrid import _engine, _noop_writer


class TestRepairFrameBuilders:
    def test_build_block_retry_frame(self) -> None:
        frame = ProgressService.build_block_retry_frame(
            page_idx=1, block_idx=2, attempt=1, confidence=0.55, target=0.98
        )
        assert frame == {
            "type": FrameType.BLOCK_RETRY.value,
            "page_idx": 1,
            "block_idx": 2,
            "attempt": 1,
            "confidence": 0.55,
            "target": 0.98,
        }

    def test_build_block_revised_frame_mirrors_block_frame_plus_attempt(self) -> None:
        frame = ProgressService.build_block_revised_frame(
            page_idx=0,
            block_idx=3,
            attempt=2,
            bbox=[0.1, 0.2, 0.9, 0.3],
            text="revised text",
            confidence=0.99,
        )
        assert frame["type"] == FrameType.BLOCK_REVISED.value
        assert frame["attempt"] == 2
        assert frame["bbox"] == [0.1, 0.2, 0.9, 0.3]
        assert frame["text"] == "revised text"
        assert frame["kind"] == "text"
        assert frame["confidence"] == 0.99

    def test_build_quality_summary_frame_page_scope(self) -> None:
        frame = ProgressService.build_quality_summary_frame(
            scope="page",
            page_idx=4,
            target=0.98,
            avg_confidence=0.93,
            repaired_count=2,
            below_target_count=1,
        )
        assert frame["type"] == FrameType.QUALITY_SUMMARY.value
        assert frame["scope"] == "page"
        assert frame["page_idx"] == 4
        assert frame["repaired_count"] == 2

    def test_build_quality_summary_frame_job_scope_omits_page_idx(self) -> None:
        frame = ProgressService.build_quality_summary_frame(
            scope="job",
            target=0.98,
            avg_confidence=0.97,
            repaired_count=0,
            below_target_count=0,
        )
        assert frame["scope"] == "job"
        assert "page_idx" not in frame


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def send_text(self, text: str) -> None:
        # NDJSON wire format: parse the JSON line and store the dict
        # so existing test assertions keep working.
        import json

        self.sent.append(json.loads(text))


def _manager_with_channel() -> tuple[ConnectionManager, _FakeWebSocket]:
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    manager.active["test-channel"] = ws  # type: ignore[assignment]
    return manager, ws


class TestRepairSenders:
    async def test_send_block_retry(self) -> None:
        manager, ws = _manager_with_channel()
        await manager.send_block_retry(
            "test-channel",
            page_idx=0,
            block_idx=2,
            attempt=1,
            confidence=0.5,
            target=0.98,
        )
        assert ws.sent[0]["type"] == "block_retry"
        assert ws.sent[0]["attempt"] == 1

    async def test_send_block_revised(self) -> None:
        manager, ws = _manager_with_channel()
        await manager.send_block_revised(
            "test-channel",
            page_idx=0,
            block_idx=2,
            attempt=1,
            bbox=[0.1, 0.1, 0.9, 0.2],
            text="better text here now",
            confidence=0.99,
        )
        assert ws.sent[0]["type"] == "block_revised"
        assert ws.sent[0]["text"] == "better text here now"

    async def test_send_quality_summary(self) -> None:
        manager, ws = _manager_with_channel()
        await manager.send_quality_summary(
            "test-channel",
            scope="job",
            target=0.98,
            avg_confidence=0.97,
            repaired_count=3,
            below_target_count=1,
        )
        assert ws.sent[0]["type"] == "quality_summary"
        assert "page_idx" not in ws.sent[0]

    async def test_senders_drop_silently_without_channel(self) -> None:
        manager, _ = _manager_with_channel()
        await manager.send_block_retry(
            None, page_idx=0, block_idx=0, attempt=1, confidence=0.5, target=0.98
        )  # must not raise


class TestRepairCallbackSet:
    def test_new_fields_default_to_none(self) -> None:
        cb = BlockCallbackSet()
        assert cb.on_block_retry is None
        assert cb.on_block_revised is None
        assert cb.on_quality_summary is None

    def test_positional_construction_still_works(self) -> None:
        async def on_block(*args): ...
        async def on_page(*args): ...

        cb = BlockCallbackSet(on_block, on_page)
        assert cb.on_block is on_block
        assert cb.on_page_complete is on_page
        assert cb.on_block_retry is None


class TestEstimateConfidenceCeiling:
    def test_well_formed_multiword_text_clears_default_target(self) -> None:
        assert (
            _estimate_confidence("The quick brown fox jumps over the lazy dog") >= 0.98
        )

    def test_valid_numeric_expressions_clear_target(self) -> None:
        assert _estimate_confidence("12 34 56 78") >= 0.98
        assert _estimate_confidence("$1,234.50") >= 0.98
        assert _estimate_confidence("+1 (555) 123-4567") >= 0.98

    def test_mixed_noise_text_stays_at_intermediate_band(self) -> None:
        # 4 words but low alpha ratio -> 0.85 band, still repair-worthy.
        assert _estimate_confidence("a1 b2 c3 d4") == 0.85

    def test_existing_bands_unchanged(self) -> None:
        assert _estimate_confidence("") == 0.0
        assert _estimate_confidence("   ") == 0.0
        assert _estimate_confidence("~^&*") == 0.3
        assert _estimate_confidence("12345") == 0.99
        assert _estimate_confidence("ab") == 0.4
        assert _estimate_confidence("hello there") == 0.7


class TestQualityRepairLoop:
    async def test_blocks_at_or_above_target_are_not_repaired(self) -> None:
        loop = QualityRepairLoop(RepairOptions(target=0.98))
        blocks = [((0.1, 0.1, 0.9, 0.2), "The quick brown fox jumps over the lazy dog")]

        async def re_ocr(block_idx, bbox):
            raise AssertionError("re_ocr must not run for healthy blocks")

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert summary.repaired_count == 0
        assert summary.below_target_count == 0
        assert summary.block_count == 1

    async def test_below_target_block_is_repaired_and_revised_event_fires(self) -> None:
        loop = QualityRepairLoop(RepairOptions(target=0.98))
        blocks = [((0.1, 0.1, 0.9, 0.2), "x")]
        retries: list[tuple[int, int]] = []
        revisions: list[str] = []

        async def re_ocr(block_idx, bbox):
            return "The quick brown fox jumps over the lazy dog"

        async def on_retry(page_idx, block_idx, attempt, confidence, target):
            retries.append((block_idx, attempt))

        async def on_revised(
            page_idx, block_idx, attempt, bbox, text, kind, confidence
        ):
            revisions.append(text)

        summary = await loop.repair_page(
            page_idx=0,
            page_blocks=blocks,
            re_ocr=re_ocr,
            on_block_retry=on_retry,
            on_block_revised=on_revised,
        )
        assert blocks[0][1] == "The quick brown fox jumps over the lazy dog"
        assert retries == [(0, 1)]
        assert revisions == ["The quick brown fox jumps over the lazy dog"]
        assert summary.repaired_count == 1
        assert summary.below_target_count == 0

    async def test_empty_blocks_are_skipped_and_excluded_from_stats(self) -> None:
        loop = QualityRepairLoop(RepairOptions(target=0.98))
        blocks = [((0.1, 0.1, 0.9, 0.2), ""), ((0.1, 0.3, 0.9, 0.4), "   ")]

        async def re_ocr(block_idx, bbox):
            raise AssertionError("empty blocks must not be repaired")

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert summary.block_count == 0
        assert summary.avg_confidence == 1.0

    async def test_stall_guard_rejects_non_improvement(self) -> None:
        loop = QualityRepairLoop(RepairOptions(target=0.98, max_retries=3))
        # "two words" estimates 0.7; the retry returns same-band text (0.7),
        # which is not an improvement -> the loop stops after one attempt.
        blocks = [((0.1, 0.1, 0.9, 0.2), "two words")]
        calls = 0

        async def re_ocr(block_idx, bbox):
            nonlocal calls
            calls += 1
            return "other phrase"

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert calls == 1
        assert blocks[0][1] == "two words"
        assert summary.repaired_count == 0
        assert summary.below_target_count == 1

    async def test_respects_max_retries(self) -> None:
        loop = QualityRepairLoop(RepairOptions(target=0.98, max_retries=2))
        blocks = [((0.1, 0.1, 0.9, 0.2), "x")]  # estimates 0.4
        responses = iter(["two words", "a1 b2 c3 d4", "never reached"])
        calls = 0

        async def re_ocr(block_idx, bbox):
            nonlocal calls
            calls += 1
            return next(responses)

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert calls == 2
        assert blocks[0][1] == "a1 b2 c3 d4"  # best accepted revision wins
        assert summary.repaired_count == 1
        assert summary.below_target_count == 1

    async def test_circuit_open_error_propagates(self) -> None:
        loop = QualityRepairLoop(RepairOptions())
        blocks = [((0.1, 0.1, 0.9, 0.2), "x")]

        async def re_ocr(block_idx, bbox):
            raise CircuitOpenError(failures=5, retry_after=30.0)

        with pytest.raises(CircuitOpenError):
            await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)

    async def test_generic_re_ocr_error_fails_open(self) -> None:
        loop = QualityRepairLoop(RepairOptions())
        blocks = [((0.1, 0.1, 0.9, 0.2), "x")]

        async def re_ocr(block_idx, bbox):
            raise RuntimeError("boom")

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert blocks[0][1] == "x"
        assert summary.repaired_count == 0
        assert summary.below_target_count == 1

    async def test_disabled_options_are_a_noop(self) -> None:
        loop = QualityRepairLoop(RepairOptions(enabled=False))
        blocks = [((0.1, 0.1, 0.9, 0.2), "x")]

        async def re_ocr(block_idx, bbox):
            raise AssertionError("disabled loop must not re-OCR")

        summary = await loop.repair_page(page_idx=0, page_blocks=blocks, re_ocr=re_ocr)
        assert summary.repaired_count == 0
        assert summary.block_count == 0


def _tiny_jpeg_b64(width: int = 100, height: int = 100) -> str:
    from PIL import Image

    img = Image.new("RGB", (width, height), "white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestPromptedGroundedOCRCrop:
    async def test_ocr_crop_calls_vlm_with_crop_prompt(self, monkeypatch) -> None:
        from omniscribe.core.grounded import prompted as prompted_mod

        backend = prompted_mod.PromptedGroundedOCR(
            api_base="http://repair-test.local/v1", model="repair-model"
        )
        monkeypatch.setattr(
            prompted_mod,
            "_rasterize_to_jpeg_pages",
            lambda path, dim, dpi: [(_tiny_jpeg_b64(), 100, 100)],
        )
        captured: dict = {}

        async def fake_call_llm(**kwargs):
            captured["messages"] = kwargs["messages"]
            return "  recovered line  "

        monkeypatch.setattr(prompted_mod, "call_llm", fake_call_llm)

        text = await backend.ocr_crop("dummy.pdf", 0, (0.2, 0.2, 0.8, 0.4))
        assert text == "recovered line"
        assert (
            captured["messages"][0]["content"][0]["text"]
            == prompted_mod.CROP_OCR_PROMPT
        )

    async def test_ocr_crop_rejects_out_of_range_page(self, monkeypatch) -> None:
        from omniscribe.core.grounded import prompted as prompted_mod

        backend = prompted_mod.PromptedGroundedOCR(
            api_base="http://repair-test.local/v1", model="repair-model"
        )
        monkeypatch.setattr(
            prompted_mod,
            "_rasterize_to_jpeg_pages",
            lambda path, dim, dpi: [(_tiny_jpeg_b64(), 100, 100)],
        )
        with pytest.raises(ValueError, match="out of range"):
            await backend.ocr_crop("dummy.pdf", 3, (0.2, 0.2, 0.8, 0.4))

    async def test_ocr_crop_returns_empty_for_degenerate_bbox(
        self, monkeypatch
    ) -> None:
        from omniscribe.core.grounded import prompted as prompted_mod

        backend = prompted_mod.PromptedGroundedOCR(
            api_base="http://repair-test.local/v1", model="repair-model"
        )
        monkeypatch.setattr(
            prompted_mod,
            "_rasterize_to_jpeg_pages",
            lambda path, dim, dpi: [(_tiny_jpeg_b64(), 100, 100)],
        )
        assert await backend.ocr_crop("dummy.pdf", 0, (0.5, 0.5, 0.5, 0.5)) == ""

    async def test_ocr_crop_rejects_negative_page(self, monkeypatch) -> None:
        from omniscribe.core.grounded import prompted as prompted_mod

        backend = prompted_mod.PromptedGroundedOCR(
            api_base="http://repair-test.local/v1", model="repair-model"
        )
        monkeypatch.setattr(
            prompted_mod,
            "_rasterize_to_jpeg_pages",
            lambda path, dim, dpi: [(_tiny_jpeg_b64(), 100, 100)],
        )
        with pytest.raises(ValueError, match="out of range"):
            await backend.ocr_crop("dummy.pdf", -1, (0.2, 0.2, 0.8, 0.4))

    async def test_raster_cache_shared_across_crop_calls(self, monkeypatch) -> None:
        """Audit P2-9: repair crops must reuse the main-pass rasterization."""
        from omniscribe.core.grounded import prompted as prompted_mod

        backend = prompted_mod.PromptedGroundedOCR(
            api_base="http://repair-test.local/v1", model="repair-model"
        )
        calls: list[str] = []

        def counting_raster(path, dim, dpi):
            calls.append(path)
            return [(_tiny_jpeg_b64(), 100, 100)]

        monkeypatch.setattr(prompted_mod, "_rasterize_to_jpeg_pages", counting_raster)

        async def fake_call_llm(**kwargs):
            return "  recovered line  "

        monkeypatch.setattr(prompted_mod, "call_llm", fake_call_llm)

        await backend.ocr_crop("dummy.pdf", 0, (0.2, 0.2, 0.8, 0.4))
        await backend.ocr_crop("dummy.pdf", 0, (0.1, 0.1, 0.5, 0.5))

        assert len(calls) == 1, "second crop re-rasterized the document"


class TestCropNormalizedGeometry:
    def test_padding_and_size(self) -> None:
        from PIL import Image

        from omniscribe.core.grounded.prompted import _crop_normalized

        b64 = _tiny_jpeg_b64(100, 100)
        out = _crop_normalized(b64, (0.2, 0.2, 0.8, 0.4), 100, 100)
        assert out is not None
        img = Image.open(io.BytesIO(base64.b64decode(out)))
        # F1.17 audit fix: padding is now ``DEFAULT_CROP_PADDING`` (0.5%)
        # shared with the hybrid path, not 5% (the pre-fix grounded-only
        # value). With 0.5% padding on this 100x100 image:
        #   pad_x = 0.005 * 0.6 = 0.003 -> x: 19..80 (width 61)
        #   pad_y = 0.005 * 0.2 = 0.001 -> y: 19..40 (height 21)
        # The previous 5% test value was (66, 22). The shape of the
        # assertion (exact pixel dimensions) is what we want to pin;
        # the values change with the unified padding.
        assert img.size == (61, 21)

    def test_edge_hugging_bbox_is_clamped(self) -> None:
        from PIL import Image

        from omniscribe.core.grounded.prompted import _crop_normalized

        b64 = _tiny_jpeg_b64(100, 100)
        out = _crop_normalized(b64, (0.0, 0.0, 0.99, 0.99), 100, 100)
        assert out is not None
        img = Image.open(io.BytesIO(base64.b64decode(out)))
        # padded box would exceed the page; clamping keeps it inside
        assert img.size[0] <= 100 and img.size[1] <= 100
        assert img.size[0] >= 99 and img.size[1] >= 98


class TestEmitJobRepairSummary:
    async def test_block_weighted_average_across_pages(self) -> None:
        seen: list[tuple] = []

        async def on_summary(scope, page_idx, target, avg, repaired, below):
            seen.append((scope, page_idx, target, avg, repaired, below))

        cb = BlockCallbackSet(on_quality_summary=on_summary)
        summaries = [
            PageRepairSummary(
                page_idx=0,
                target=0.98,
                block_count=3,
                avg_confidence=0.9,
                repaired_count=1,
                below_target_count=0,
            ),
            PageRepairSummary(
                page_idx=1,
                target=0.98,
                block_count=1,
                avg_confidence=0.5,
                repaired_count=0,
                below_target_count=1,
            ),
        ]

        await emit_job_repair_summary(cb, summaries)

        # (3*0.9 + 1*0.5) / 4 = 0.8
        assert seen == [("job", None, 0.98, pytest.approx(0.8), 1, 1)]

    async def test_empty_summaries_are_a_noop(self) -> None:
        seen: list[tuple] = []

        async def on_summary(*args):
            seen.append(args)

        cb = BlockCallbackSet(on_quality_summary=on_summary)
        await emit_job_repair_summary(cb, [])
        assert seen == []

    async def test_none_callbacks_or_missing_observer_are_noops(self) -> None:
        summaries = [
            PageRepairSummary(
                page_idx=0,
                target=0.98,
                block_count=1,
                avg_confidence=0.9,
                repaired_count=0,
                below_target_count=0,
            )
        ]
        await emit_job_repair_summary(None, summaries)  # must not raise
        await emit_job_repair_summary(BlockCallbackSet(), summaries)  # no observer


class TestChunkFramesChaptersSchema:
    def test_chunk_init_frame_defaults_empty_chapters(self) -> None:
        frame = ProgressService.build_chunk_init_frame(total_chunks=3)
        assert frame["chapters"] == []

    def test_chunk_init_frame_passes_chapters_through(self) -> None:
        chapters = [{"title": "Intro", "start_page": 1, "end_page": 4}]
        frame = ProgressService.build_chunk_init_frame(
            total_chunks=2, chapters=chapters
        )
        assert frame["chapters"] == chapters

    def test_chunk_complete_frame_defaults_empty_chapters(self) -> None:
        frame = ProgressService.build_chunk_complete_frame(
            chunk_idx=1,
            total_chunks=2,
            page_range="1-25",
            source_pages=[0, 1],
            text_chars_so_far=100,
        )
        assert frame["chapters"] == []

    def test_chunk_complete_frame_passes_chapters_through(self) -> None:
        chapters = [{"title": "Methods", "start_page": 5, "end_page": 9}]
        frame = ProgressService.build_chunk_complete_frame(
            chunk_idx=1,
            total_chunks=2,
            page_range="1-25",
            source_pages=[0, 1],
            text_chars_so_far=100,
            chapters=chapters,
        )
        assert frame["chapters"] == chapters


class TestRepairNoneConfidence:
    """F1.8 audit fix (HIGH): a custom confidence estimator may return
    ``None`` ("I don't know"). The repair loop must coerce ``None`` to
    ``0.0`` (worst-case confidence) rather than crashing on
    ``None <= conf`` ordering.

    The protocol type now allows ``Callable[[str], float | None]``;
    both the outer estimate and the per-attempt estimate get
    coerced. The loop must still drive the page through repair and
    emit a summary without raising.
    """

    async def test_repair_loop_with_none_returning_estimator_does_not_crash(
        self,
    ) -> None:
        # Custom estimator that returns None for "I don't know".
        def none_estimator(_text: str) -> float | None:
            return None

        async def re_ocr(_block_idx: int, _bbox: tuple) -> str:
            return "irrelevant"

        loop = QualityRepairLoop(
            options=RepairOptions(target=0.98, max_retries=2),
            confidence_estimator=none_estimator,
        )
        page_blocks = [
            ((0.1, 0.1, 0.9, 0.2), "low quality text"),
        ]
        summary = await loop.repair_page(
            page_idx=0,
            page_blocks=page_blocks,
            re_ocr=re_ocr,
        )
        # The page was processed without raising; the block counts.
        assert summary.block_count == 1
        # ``None`` was coerced to 0.0 (worst case), so the block is
        # below target and ``below_target_count`` is 1.
        assert summary.below_target_count == 1
        # ``repaired_count`` is 0 because the loop never produced a
        # higher-confidence replacement (every estimate was 0.0).
        assert summary.repaired_count == 0


# ---------------------------------------------------------------------------
# HybridEngine._repair_pages wiring (moved from test_workflows_hybrid.py —
# Phase 4.2)
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
