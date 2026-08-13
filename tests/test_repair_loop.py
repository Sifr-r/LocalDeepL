"""Quality repair loop (spec P1): frames, loop logic, engine + API wiring."""

from __future__ import annotations

from omniscribe.api.routers.websocket import ConnectionManager
from omniscribe.api.services.progress import FrameType, ProgressService
from omniscribe.core.callbacks import BlockCallbackSet
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
