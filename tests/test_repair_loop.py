"""Quality repair loop (spec P1): frames, loop logic, engine + API wiring."""

from __future__ import annotations

import base64
import io

import pytest

from omniscribe.api.routers.websocket import ConnectionManager
from omniscribe.api.services.progress import FrameType, ProgressService
from omniscribe.core.callbacks import BlockCallbackSet
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.workflows.repair import (
    PageRepairSummary,
    QualityRepairLoop,
    RepairOptions,
    emit_job_repair_summary,
)
from omniscribe.core.workflows.utils import _estimate_confidence


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

    def test_digit_heavy_multiword_text_stays_below_target(self) -> None:
        assert _estimate_confidence("12 34 56 78") < 0.98

    def test_mixed_noise_text_stays_at_intermediate_band(self) -> None:
        # 4 words but low alpha ratio -> 0.85 band, still repair-worthy.
        assert _estimate_confidence("a1 b2 c3 d4") == 0.85

    def test_existing_bands_unchanged(self) -> None:
        assert _estimate_confidence("") == 0.0
        assert _estimate_confidence("   ") == 0.0
        assert _estimate_confidence("12345") == 0.3
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


class TestCropNormalizedGeometry:
    def test_padding_and_size(self) -> None:
        from PIL import Image

        from omniscribe.core.grounded.prompted import _crop_normalized

        b64 = _tiny_jpeg_b64(100, 100)
        out = _crop_normalized(b64, (0.2, 0.2, 0.8, 0.4), 100, 100)
        assert out is not None
        img = Image.open(io.BytesIO(base64.b64decode(out)))
        # pad_x = 0.05 * 0.6 = 0.03 -> x: 17..83; pad_y = 0.05 * 0.2 = 0.01 -> y: 19..41
        assert img.size == (66, 22)

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
