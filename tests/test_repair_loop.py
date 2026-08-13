"""Quality repair loop (spec P1): frames, loop logic, engine + API wiring."""

from __future__ import annotations

from omniscribe.api.services.progress import FrameType, ProgressService


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
