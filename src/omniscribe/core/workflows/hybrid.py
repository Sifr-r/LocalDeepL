from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING

from PIL import Image

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.document import BBox, DenseMode, SpellcheckMode
from omniscribe.core.imaging.page_preprocess import (
    PagePreprocessingOptions,
    PagePreprocessor,
)
from omniscribe.core.ocr import OCRProcessor
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.ocr_quality import TrustOrchestrator
from omniscribe.core.ocr_quality.routing import (
    QualityRoutingOptions,
    QualityRoutingPolicy,
)
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.processors import DocumentProcessor
from omniscribe.core.recall.text_layer import PdfTextLayerRecall
from omniscribe.core.recall.whitespace import WhitespaceRecallBooster
from omniscribe.core.workflows.base import (
    AnyOutputWriter,
    CancelCheck,
    EngineBase,
    OCRCancelled,
    PageBoxes,
    PagesData,
    ProgressCallback,
    WarningCallback,
    notify,
)
from omniscribe.core.workflows.repair import (
    PageRepairSummary,
    QualityRepairLoop,
    RepairOptions,
    emit_job_repair_summary,
)
from omniscribe.core.workflows.stages import (
    HybridConverter,
    HybridLayoutDetector,
    HybridOcrRunner,
    HybridRefiner,
    decode_chunk_bytes,
)
from omniscribe.core.workflows.utils import (
    DETECT_CHUNK_SIZE,
    _decode_page_image,
    _drop_refined_duplicates,
    _estimate_confidence,
    _is_refinable,
    parse_page_range,
    validate_bbox_coordinates,
)
from omniscribe.utils.image import crop_for_ocr_from_image

if TYPE_CHECKING:
    from omniscribe.core.callbacks import BlockCallbackSet

logger = logging.getLogger(__name__)

# Phase 3 finding 2.3 — bound the per-page decoded-image LRU to keep
# long-document runs from holding a PIL.Image per page for the whole run.
# Invariant (CQ-4): must stay >= DETECT_CHUNK_SIZE (workflows.utils).
_DECODED_CACHE_MAX_ENTRIES = 16

# Alias for backward-compatibility with existing tests and imports
_decode_chunk_bytes = decode_chunk_bytes

__all__ = [
    "DETECT_CHUNK_SIZE",
    "_DECODED_CACHE_MAX_ENTRIES",
    "HybridEngine",
    "_decode_chunk_bytes",
    "_decode_page_image",
    "_drop_refined_duplicates",
    "_estimate_confidence",
    "_is_refinable",
    "parse_page_range",
    "validate_bbox_coordinates",
]


class HybridEngine(EngineBase):
    def __init__(
        self,
        aligner: HybridAligner,
        ocr_processor: OCRProcessor,
        pdf_handler: PDFHandler,
        output_writer: AnyOutputWriter,
        document_processors: Sequence[DocumentProcessor] | None = None,
        page_preprocessor: PagePreprocessor | None = None,
        block_callbacks: BlockCallbackSet | None = None,
        trust_orchestrator: TrustOrchestrator | None = None,
        recall_booster: WhitespaceRecallBooster | None = None,
        text_layer_recall: PdfTextLayerRecall | None = None,
    ) -> None:
        super().__init__(
            output_writer=output_writer,
            document_processors=document_processors,
            block_callbacks=block_callbacks,
            trust_orchestrator=trust_orchestrator,
        )
        self.aligner = aligner
        self.ocr_processor = ocr_processor
        self.pdf_handler = pdf_handler
        self.page_preprocessor = page_preprocessor
        self.recall_booster = recall_booster
        self.text_layer_recall = text_layer_recall
        self._decoded_cache: OrderedDict[int, Image.Image] = OrderedDict()

        self.converter = HybridConverter(
            pdf_handler=self.pdf_handler,
            page_preprocessor=self.page_preprocessor,
        )
        self.layout_detector = HybridLayoutDetector(
            aligner=self.aligner,
            recall_booster=self.recall_booster,
            text_layer_recall=self.text_layer_recall,
        )
        self.ocr_runner = HybridOcrRunner(
            aligner=self.aligner,
            ocr_processor=self.ocr_processor,
            block_callbacks=self.block_callbacks,
            last_failed_pages=self.last_failed_pages,
        )
        self.refiner = HybridRefiner(
            ocr_processor=self.ocr_processor,
        )

    def _decoded_get(self, page_num: int) -> Image.Image | None:
        """Return the cached image for ``page_num`` and mark it most-recently-used."""
        cached = self._decoded_cache.get(page_num)
        if cached is not None:
            self._decoded_cache.move_to_end(page_num)
        return cached

    def _decoded_put(self, page_num: int, image: Image.Image) -> None:
        """Cache ``image`` for ``page_num`` and evict the LRU entry if over capacity."""
        self._decoded_cache[page_num] = image
        self._decoded_cache.move_to_end(page_num)
        if len(self._decoded_cache) > _DECODED_CACHE_MAX_ENTRIES:
            self._decoded_cache.popitem(last=False)

    def _reset_run_state(self) -> None:
        """Clear run-scoped state. Call at the top of every ``execute``."""
        super()._reset_run_state()
        self._decoded_cache = OrderedDict()
        self.ocr_runner.last_failed_pages = self.last_failed_pages

    async def execute(
        self,
        input_path: str,
        output_path: str,
        *,
        dpi: int = 200,
        pages: str | None = None,
        concurrency: int = 1,
        refine: bool = True,
        max_image_dim: int = 1024,
        dense_threshold: int = 60,
        dense_mode: DenseMode = DenseMode.AUTO,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
        spellcheck: SpellcheckMode = SpellcheckMode.NONE,
        cross_page: bool = False,
        preprocessing_options: PagePreprocessingOptions | None = None,
        quality_routing_options: QualityRoutingOptions | None = None,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
        trust_model_id: str = "unknown",
        trust_images_dict: dict[int, str] | None = None,
        repair_options: RepairOptions | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> dict[int, list[str]]:
        if not isinstance(dense_mode, DenseMode):
            raise ValueError(
                f"dense_mode must be a DenseMode instance; got {dense_mode!r}"
            )

        self._reset_run_state()

        # --- Phase 1: convert + optional preprocessing ---
        images_dict, page_nums, preprocessing_metadata = await self._convert_pages(
            input_path=input_path,
            dpi=dpi,
            max_image_dim=max_image_dim,
            pages=pages,
            preprocessing_options=preprocessing_options,
            progress=progress,
        )

        # --- Phase 2: batched layout detection (cancel-gate lives inside) ---
        pages_structured = await self._detect_layout(
            images_dict=images_dict,
            page_nums=page_nums,
            progress=progress,
            input_path=input_path,
            cancel_check=cancel_check,
        )

        per_box_pages = self._select_dense_pages(
            pages_structured=pages_structured,
            page_nums=page_nums,
            dense_mode=dense_mode,
            dense_threshold=dense_threshold,
        )

        # --- Phase 3: concurrent OCR (sparse + dense) ---
        await self._ocr_pages(
            images_dict=images_dict,
            pages_structured=pages_structured,
            page_nums=page_nums,
            per_box_pages=per_box_pages,
            concurrency=concurrency,
            self_correction=self_correction,
            binarize=binarize,
            dual_engine=dual_engine,
            progress=progress,
            on_warning=on_warning,
            cancel_check=cancel_check,
        )

        # --- Phase 4: refine empty boxes on the sparse pages ---
        if refine:
            await self._refine_pages(
                pages_structured=pages_structured,
                images_dict=images_dict,
                page_nums=page_nums,
                per_box_pages=per_box_pages,
                concurrency=concurrency,
                self_correction=self_correction,
                binarize=binarize,
                dual_engine=dual_engine,
                progress=progress,
                cancel_check=cancel_check,
            )

        # --- Phase 4b: quality repair of below-target blocks (spec §3.2) ---
        if repair_options is not None and repair_options.enabled:
            repair_summaries = await self._repair_pages(
                pages_structured=pages_structured,
                images_dict=images_dict,
                page_nums=page_nums,
                repair_options=repair_options,
                concurrency=concurrency,
                progress=progress,
                on_warning=on_warning,
            )
            await emit_job_repair_summary(self.block_callbacks, repair_summaries)

        # --- Phase 5: assemble, post-process, route, emit (cancel-gate lives inside) ---
        return await self._finalize(
            input_path=input_path,
            output_path=output_path,
            pages_structured=pages_structured,
            page_nums=page_nums,
            preprocessing_metadata=preprocessing_metadata,
            spellcheck=spellcheck,
            cross_page=cross_page,
            quality_routing_options=quality_routing_options,
            dpi=dpi,
            progress=progress,
            trust_model_id=trust_model_id,
            trust_images_dict=images_dict,
            cancel_check=cancel_check,
        )

    async def _convert_pages(
        self,
        *,
        input_path: str,
        dpi: int,
        max_image_dim: int,
        pages: str | None,
        preprocessing_options: PagePreprocessingOptions | None,
        progress: ProgressCallback | None,
        rasterize_batch_size: int = 8,
    ) -> tuple[dict[int, str], list[int], dict[int, dict[str, object]]]:
        self.converter.pdf_handler = self.pdf_handler
        self.converter.page_preprocessor = self.page_preprocessor
        return await self.converter.convert_pages(
            input_path=input_path,
            dpi=dpi,
            max_image_dim=max_image_dim,
            pages=pages,
            preprocessing_options=preprocessing_options,
            progress=progress,
            rasterize_batch_size=rasterize_batch_size,
        )

    async def _detect_layout(
        self,
        *,
        images_dict: dict[int, str],
        page_nums: Sequence[int],
        progress: ProgressCallback | None,
        input_path: str = "",
        cancel_check: CancelCheck | None = None,
    ) -> dict[int, PageBoxes]:
        # Audit catalog: between-phase cancel checks used to live in
        # execute(); folded into the next-phase helper so execute() is
        # a clean phase driver.
        if cancel_check is not None and cancel_check():
            raise OCRCancelled("OCR cancelled before layout detection.")
        self.layout_detector.aligner = self.aligner
        self.layout_detector.recall_booster = self.recall_booster
        self.layout_detector.text_layer_recall = self.text_layer_recall
        return await self.layout_detector.detect_layout(
            images_dict=images_dict,
            page_nums=page_nums,
            progress=progress,
            input_path=input_path,
            decoded_put=self._decoded_put,
            decoded_get=self._decoded_get,
        )

    async def _apply_recall(
        self,
        *,
        chunk_pages: Sequence[int],
        images_dict: dict[int, str],
        chunk_boxes: list[list[BBox]],
    ) -> tuple[list[list[BBox]], int, int]:
        self.layout_detector.recall_booster = self.recall_booster
        return await self.layout_detector.apply_recall(
            chunk_pages=chunk_pages,
            images_dict=images_dict,
            chunk_boxes=chunk_boxes,
            decoded_get=self._decoded_get,
            decoded_put=self._decoded_put,
        )

    async def _apply_text_layer_recall(
        self,
        *,
        chunk_pages: Sequence[int],
        chunk_boxes: list[list[BBox]],
    ) -> tuple[list[list[BBox]], int, int]:
        self.layout_detector.text_layer_recall = self.text_layer_recall
        return await self.layout_detector.apply_text_layer_recall(
            chunk_pages=chunk_pages,
            chunk_boxes=chunk_boxes,
        )

    def _select_dense_pages(
        self,
        *,
        pages_structured: PagesData,
        page_nums: Sequence[int],
        dense_mode: str,
        dense_threshold: int,
    ) -> set[int]:
        return self.layout_detector.select_dense_pages(
            pages_structured=pages_structured,
            page_nums=page_nums,
            dense_mode=dense_mode,
            dense_threshold=dense_threshold,
        )

    async def _ocr_pages(
        self,
        *,
        images_dict: dict[int, str],
        pages_structured: dict[int, PageBoxes],
        page_nums: Sequence[int],
        per_box_pages: set[int],
        concurrency: int,
        self_correction: bool,
        binarize: bool,
        dual_engine: bool,
        progress: ProgressCallback | None,
        on_warning: WarningCallback | None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.ocr_runner.aligner = self.aligner
        self.ocr_runner.ocr_processor = self.ocr_processor
        self.ocr_runner.block_callbacks = self.block_callbacks
        self.ocr_runner.last_failed_pages = self.last_failed_pages
        return await self.ocr_runner.ocr_pages(
            images_dict=images_dict,
            pages_structured=pages_structured,
            page_nums=page_nums,
            per_box_pages=per_box_pages,
            concurrency=concurrency,
            self_correction=self_correction,
            binarize=binarize,
            dual_engine=dual_engine,
            progress=progress,
            on_warning=on_warning,
            cancel_check=cancel_check,
            decoded_get=self._decoded_get,
            emit_page_callbacks=self._emit_page_callbacks,
        )

    async def _ocr_per_box(
        self,
        image_b64: str,
        structured: PageBoxes,
        semaphore: asyncio.Semaphore,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
        page_image: Image.Image | None = None,
    ) -> PageBoxes:
        self.ocr_runner.ocr_processor = self.ocr_processor
        return await self.ocr_runner.ocr_per_box(
            image_b64=image_b64,
            structured=structured,
            semaphore=semaphore,
            self_correction=self_correction,
            binarize=binarize,
            dual_engine=dual_engine,
            page_image=page_image,
        )

    async def _refine_pages(
        self,
        *,
        pages_structured: dict[int, PageBoxes],
        images_dict: dict[int, str],
        page_nums: Sequence[int],
        per_box_pages: set[int],
        concurrency: int,
        self_correction: bool,
        binarize: bool,
        dual_engine: bool,
        progress: ProgressCallback | None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.refiner.ocr_processor = self.ocr_processor
        return await self.refiner.refine_pages(
            pages_structured=pages_structured,
            images_dict=images_dict,
            page_nums=page_nums,
            per_box_pages=per_box_pages,
            concurrency=concurrency,
            self_correction=self_correction,
            binarize=binarize,
            dual_engine=dual_engine,
            progress=progress,
            cancel_check=cancel_check,
            decoded_get=self._decoded_get,
        )

    async def _refine_uncertain(
        self,
        sparse_structured: dict[int, PageBoxes],
        images_dict: dict[int, str],
        semaphore: asyncio.Semaphore,
        progress: ProgressCallback | None,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.refiner.ocr_processor = self.ocr_processor
        return await self.refiner.refine_uncertain(
            sparse_structured=sparse_structured,
            images_dict=images_dict,
            semaphore=semaphore,
            progress=progress,
            self_correction=self_correction,
            binarize=binarize,
            dual_engine=dual_engine,
            cancel_check=cancel_check,
            decoded_get=self._decoded_get,
        )

    def _count_repair_targets(
        self,
        *,
        page_nums: Sequence[int],
        pages_structured: dict[int, PageBoxes],
        target: float,
    ) -> int:
        """Count non-empty blocks whose estimated confidence is below ``target``.

        Audit catalog: extracted from the inline ``sum(...)`` at the
        top of ``_repair_pages`` so the parent function is a clean
        phase driver.
        """
        return sum(
            1
            for p_num in page_nums
            for _, text in pages_structured.get(p_num, [])
            if text.strip() and _estimate_confidence(text) < target
        )

    async def _repair_single_page(
        self,
        *,
        p_num: int,
        aligned: list,
        page_image: Image.Image,
        loop: QualityRepairLoop,
        cb: BlockCallbackSet,
        completed_box: list[int],
        targets: int,
        on_warning: WarningCallback | None,
        progress: ProgressCallback | None,
    ) -> PageRepairSummary:
        """Re-OCR one page's below-target blocks; emit per-page summary.

        ``completed_box`` is a single-element mutable counter shared
        across the per-page loop (audit catalog: nonlocal ``completed``
        carried the global count for the progress emit; the list
        pattern is the same one the OCR quality orchestrator uses
        for ``fallback_used_box``).
        """
        async def re_ocr(
            block_idx: int,
            bbox: tuple[float, float, float, float],
            *,
            _img: Image.Image = page_image,
            _page: int = p_num,
        ) -> str:
            crop_b64 = await asyncio.to_thread(
                crop_for_ocr_from_image, _img, list(bbox)
            )
            if crop_b64 is None:
                return ""
            try:
                text = await self.ocr_processor.perform_ocr_on_crop(crop_b64)
            except CircuitOpenError:
                raise
            except Exception as exc:
                if on_warning is not None:
                    await on_warning(_page, exc)
                raise
            completed_box[0] += 1
            await notify(
                progress,
                "refine",
                min(completed_box[0], targets),
                targets,
                f"Repairing below-target blocks ({min(completed_box[0], targets)}/{targets})",
            )
            return text

        summary = await loop.repair_page(
            page_idx=p_num,
            page_blocks=aligned,
            re_ocr=re_ocr,
            on_block_retry=cb.on_block_retry,
            on_block_revised=cb.on_block_revised,
        )
        if cb.on_quality_summary is not None:
            await cb.on_quality_summary(
                "page",
                p_num,
                summary.target,
                summary.avg_confidence,
                summary.repaired_count,
                summary.below_target_count,
            )
        return summary

    async def _repair_pages(
        self,
        *,
        pages_structured: dict[int, PageBoxes],
        images_dict: dict[int, str],
        page_nums: Sequence[int],
        repair_options: RepairOptions,
        concurrency: int,
        progress: ProgressCallback | None,
        on_warning: WarningCallback | None = None,
    ) -> list[PageRepairSummary]:
        """Phase 4b — re-OCR non-empty blocks below the quality target.

        Audit catalog: split the 94-LOC body into
        :meth:`_count_repair_targets` + :meth:`_repair_single_page` so
        this function is a clean phase driver. The shared
        ``completed`` counter is carried via a single-element list.
        """
        loop = QualityRepairLoop(repair_options)
        cb = self.block_callbacks

        targets = self._count_repair_targets(
            page_nums=page_nums,
            pages_structured=pages_structured,
            target=repair_options.target,
        )
        if not targets:
            return []
        await notify(
            progress,
            "refine",
            0,
            targets,
            f"Repairing {targets} below-target blocks...",
        )

        completed_box = [0]
        summaries: list[PageRepairSummary] = []
        for p_num in page_nums:
            aligned = pages_structured.get(p_num)
            if not aligned:
                continue

            cached = self._decoded_get(p_num)
            page_image = (
                cached
                if cached is not None
                else await asyncio.to_thread(_decode_page_image, images_dict[p_num])
            )

            summary = await self._repair_single_page(
                p_num=p_num,
                aligned=aligned,
                page_image=page_image,
                loop=loop,
                cb=cb,
                completed_box=completed_box,
                targets=targets,
                on_warning=on_warning,
                progress=progress,
            )
            summaries.append(summary)
        return summaries

    async def _finalize(
        self,
        *,
        input_path: str,
        output_path: str,
        pages_structured: dict[int, PageBoxes],
        page_nums: Sequence[int],
        preprocessing_metadata: dict[int, dict[str, object]],
        spellcheck: SpellcheckMode,
        cross_page: bool,
        quality_routing_options: QualityRoutingOptions | None,
        dpi: int,
        progress: ProgressCallback | None,
        trust_model_id: str = "unknown",
        trust_images_dict: dict[int, str] | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> dict[int, list[str]]:
        """Post-process, run document processors, apply hybrid-only quality routing, emit.

        ``cancel_check`` is consulted at entry — it acts as the
        post-OCR cancel gate that used to live inline in
        :meth:`execute` (audit catalog). Any later phase that wants to
        short-circuit (refine / repair) does its own per-chunk check
        via the underlying runner.
        """
        if cancel_check is not None and cancel_check():
            raise OCRCancelled("OCR cancelled after OCR loop.")
        document_result = await self._build_document_result(
            pages_data=pages_structured,
            page_nums=page_nums,
            source_path=input_path,
            source_processor="hybrid",
            spellcheck=spellcheck,
            cross_page=cross_page,
            page_metadata_overlays=preprocessing_metadata,
        )

        document_result = await self._apply_trust(
            document_result,
            model_id=trust_model_id,
            trust_images_dict=trust_images_dict,
        )

        if quality_routing_options is not None and quality_routing_options.enabled:
            document_result = QualityRoutingPolicy().apply(
                document_result, quality_routing_options
            )

        return await self._emit(
            input_path=input_path,
            output_path=output_path,
            document_result=document_result,
            dpi=dpi,
            progress=progress,
            page_nums=list(page_nums),
        )
