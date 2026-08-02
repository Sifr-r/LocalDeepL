from __future__ import annotations

import asyncio
import base64
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING

from PIL import Image

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.document import DenseMode, SpellcheckMode
from omniscribe.core.ocr import OCRProcessor
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.preprocessing import PagePreprocessingOptions, PagePreprocessor
from omniscribe.core.processors import DocumentProcessor
from omniscribe.core.routing import QualityRoutingOptions, QualityRoutingPolicy
from omniscribe.core.workflows.base import (
    AnyOutputWriter,
    EngineBase,
    PageBoxes,
    PagesData,
    ProgressCallback,
    WarningCallback,
    notify,
)
from omniscribe.utils.image import crop_for_ocr_from_image

if TYPE_CHECKING:
    from omniscribe.core.callbacks import BlockCallbackSet

from omniscribe.core.workflows.utils import (
    DETECT_CHUNK_SIZE,
    _decode_page_image,
    _drop_refined_duplicates,
    _estimate_confidence,
    _is_refinable,
    parse_page_range,
)


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
    ) -> None:
        # Phase B (review M2) — forward `block_callbacks` to the base
        # so the per-block / per-page event hook reaches `_ocr_pages`.
        # The default `None` keeps every existing call site working
        # unchanged (the in-process `OCRPipeline` user, all the
        # workflows tests).
        super().__init__(
            output_writer=output_writer,
            document_processors=document_processors,
            block_callbacks=block_callbacks,
        )
        self.aligner = aligner
        self.ocr_processor = ocr_processor
        self.pdf_handler = pdf_handler
        self.page_preprocessor = page_preprocessor

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

        # --- Phase 2: batched layout detection ---
        pages_structured = await self._detect_layout(
            images_dict=images_dict,
            page_nums=page_nums,
            progress=progress,
        )

        # Decide which pages should take the dense (per-box) path before we
        # fan out the OCR tasks — it determines how each page is dispatched.
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
            )

        # --- Phase 5: assemble, post-process, route, emit ---
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
        """Render the input to per-page images and apply optional preprocessing.

        H1 audit fix: rasterization now streams through
        :meth:`PDFHandler.convert_batches` with a bounded batch size so
        peak memory is independent of total page count. Each batch's
        PIL.Image objects are released as soon as their base64 strings
        are merged into the returned ``images_dict``.
        """
        await notify(progress, "convert", 0, 1, "Converting PDF to images...")
        images_dict: dict[int, str] = await asyncio.to_thread(
            self._collect_batched_images,
            input_path,
            dpi,
            max_image_dim,
            pages,
            rasterize_batch_size,
        )
        page_nums = sorted(images_dict.keys())
        total_pages = len(page_nums)

        if pages:
            selected = set(parse_page_range(pages, total_pages))
            page_nums = [p for p in page_nums if p in selected]
            images_dict = {
                p: image for p, image in images_dict.items() if p in selected
            }

        preprocessing_metadata: dict[int, dict[str, object]] = {}
        if (
            self.page_preprocessor is not None
            and preprocessing_options is not None
            and preprocessing_options.enabled
        ):
            await notify(
                progress, "convert", 0, 1, f"Preprocessing {len(page_nums)} pages..."
            )
            preprocessing_result = await asyncio.to_thread(
                self.page_preprocessor.preprocess,
                images_dict,
                preprocessing_options,
            )
            images_dict = preprocessing_result.images
            preprocessing_metadata = preprocessing_result.metadata
        await notify(progress, "convert", 1, 1, f"Converted {total_pages} pages.")

        return images_dict, page_nums, preprocessing_metadata

    def _collect_batched_images(
        self,
        input_path: str,
        dpi: int,
        max_image_dim: int,
        pages: str | None,
        batch_size: int,
    ) -> dict[int, str]:
        """Drive the bounded-memory batched rasterization and merge b64 strings.

        H1 audit fix: the heavy lifting of ``_convert_pages`` runs in a
        worker thread so the event loop is never blocked. ``isinstance``
        gates the new streaming API on the concrete ``PDFHandler``
        implementation so test ``MagicMock`` stubs (which auto-create
        every attribute) keep working through the legacy
        ``convert_to_images`` path they already mock.
        """
        images_dict: dict[int, str] = {}

        if isinstance(self.pdf_handler, PDFHandler):
            for batch in self.pdf_handler.convert_batches(
                input_path,
                batch_size=batch_size,
                dpi=dpi,
                pages=pages,
                max_image_dim=max_image_dim,
            ):
                for page_num, _img, b64_str in batch:
                    images_dict[page_num] = b64_str
                # Drop the batch reference so its PIL.Image objects are
                # eligible for GC before the next batch is decoded.
                # ``_img`` is intentionally unused after extraction.
                del batch
            return images_dict

        # Fallback: legacy handlers (test stubs, custom subclasses that
        # predate the H1 fix) keep working via convert_to_images.
        return self.pdf_handler.convert_to_images(
            input_path, dpi=dpi, max_image_dim=max_image_dim
        )

    async def _detect_layout(
        self,
        *,
        images_dict: dict[int, str],
        page_nums: Sequence[int],
        progress: ProgressCallback | None,
    ) -> dict[int, PageBoxes]:
        """Run batched Surya layout detection and seed each page with empty text."""
        await notify(
            progress, "detect", 0, 1, f"Detecting layout for {len(page_nums)} pages..."
        )

        batch_boxes: list[list[list[float]]] = []
        for i in range(0, len(page_nums), DETECT_CHUNK_SIZE):
            chunk_pages = page_nums[i : i + DETECT_CHUNK_SIZE]
            chunk_bytes = [base64.b64decode(images_dict[p]) for p in chunk_pages]
            chunk_boxes = await asyncio.to_thread(
                self.aligner.get_detected_boxes_batch, chunk_bytes
            )
            batch_boxes.extend(chunk_boxes)
            await notify(
                progress,
                "detect",
                min(i + DETECT_CHUNK_SIZE, len(page_nums)),
                len(page_nums),
                f"Detecting layout ({min(i + DETECT_CHUNK_SIZE, len(page_nums))}/{len(page_nums)})...",
            )

        pages_structured: dict[int, PageBoxes] = {
            p: [(box, "") for box in batch_boxes[i]] for i, p in enumerate(page_nums)
        }
        await notify(progress, "detect", 1, 1, "Layout detection complete.")
        return pages_structured

    def _select_dense_pages(
        self,
        *,
        pages_structured: PagesData,
        page_nums: Sequence[int],
        dense_mode: str,
        dense_threshold: int,
    ) -> set[int]:
        """Decide which pages take the per-box OCR path (vs full-page OCR)."""
        per_box_pages: set[int] = set()
        for p_num in page_nums:
            n_boxes = len(pages_structured[p_num])
            if dense_mode == "always" or (
                dense_mode == "auto" and n_boxes > dense_threshold
            ):
                per_box_pages.add(p_num)
        return per_box_pages

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
    ) -> None:
        """Fan out OCR across pages, dispatching sparse vs dense per page."""
        semaphore = asyncio.Semaphore(max(1, concurrency))
        total = len(page_nums)

        async def process_page(
            p_num: int,
        ) -> tuple[int, PageBoxes, Exception | None]:
            try:
                if p_num in per_box_pages:
                    aligned = await self._ocr_per_box(
                        images_dict[p_num],
                        pages_structured[p_num],
                        semaphore,
                        self_correction,
                        binarize,
                        dual_engine,
                    )
                    return p_num, aligned, None
                async with semaphore:
                    llm_lines = await self.ocr_processor.perform_ocr(
                        images_dict[p_num],
                        self_correction=self_correction,
                        binarize=binarize,
                        dual_engine=dual_engine,
                    )
                    if llm_lines:
                        aligned = await asyncio.to_thread(
                            self.aligner.align_text, pages_structured[p_num], llm_lines
                        )
                    else:
                        aligned = pages_structured[p_num]
                    return p_num, aligned, None
            except CircuitOpenError:
                raise
            except Exception as e:
                import logging

                logging.warning(f"OCR failed for page {p_num}: {type(e).__name__}: {e}")
                return p_num, pages_structured[p_num], e

        completed = 0
        ocr_label = (
            "OCR"
            if not per_box_pages
            else f"OCR ({len(per_box_pages)} dense / {total - len(per_box_pages)} sparse)"
        )
        await notify(progress, "ocr", 0, total, f"{ocr_label} (0/{total})...")
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(process_page(p)) for p in page_nums]
            for coro in asyncio.as_completed(tasks):
                p_num, aligned, page_error = await coro

                pages_structured[p_num] = aligned
                completed += 1
                # Phase B (review M2) — emit per-block and per-page
                # events through the injected callback set instead of
                # importing the WebSocket manager. The engine no longer
                # depends on `omniscribe.api`; the API layer is
                # responsible for translating these callbacks into
                # WebSocket frames (or any other transport).
                #
                # The emissions sit inside the `as_completed` loop on
                # purpose: it gives the UI a strictly monotonic per-block
                # ordering across pages, which the live bbox overlay
                # assumes. If you reorder this loop, the live UI will
                # start flashing blocks out of order.
                cb = self.block_callbacks
                if cb.on_block is not None:
                    for b_idx, (b_bbox, b_text) in enumerate(aligned):
                        if b_text and b_text.strip():
                            await cb.on_block(
                                p_num,
                                b_idx,
                                list(b_bbox),
                                b_text,
                                "text",
                                _estimate_confidence(b_text),
                            )
                if cb.on_page_complete is not None:
                    await cb.on_page_complete(p_num)

                await notify(
                    progress,
                    "ocr",
                    completed,
                    total,
                    f"{ocr_label} ({completed}/{total})",
                )
                if page_error is not None:
                    self.last_failed_pages.append(p_num)
                    if on_warning is not None:
                        await on_warning(p_num, page_error)

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
    ) -> None:
        """Crop-and-re-OCR empty boxes on the sparse pages, then dedup nearby matches."""
        sparse_structured = {
            p: pages_structured[p] for p in page_nums if p not in per_box_pages
        }
        if not sparse_structured:
            return

        await self._refine_uncertain(
            sparse_structured,
            images_dict,
            asyncio.Semaphore(max(1, concurrency)),
            progress,
            self_correction,
            binarize,
            dual_engine,
        )

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
    ) -> dict[int, list[str]]:
        """Post-process, run document processors, apply hybrid-only quality routing, emit."""
        document_result = await self._build_document_result(
            pages_data=pages_structured,
            page_nums=page_nums,
            source_path=input_path,
            source_processor="hybrid",
            spellcheck=spellcheck,
            cross_page=cross_page,
            page_metadata_overlays=preprocessing_metadata,
        )

        # Quality routing is a hybrid-only post-processor; runs after document
        # processors and before emission so it sees the cleaned-up document.
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
        if page_image is None:
            page_image = await asyncio.to_thread(_decode_page_image, image_b64)

        async def ocr_one(idx: int, bbox: list[float]) -> tuple[int, str]:
            try:
                async with semaphore:
                    if not _is_refinable(bbox):
                        return idx, ""
                    crop_b64 = await asyncio.to_thread(
                        crop_for_ocr_from_image, page_image, bbox
                    )
                    if crop_b64 is None:
                        return idx, ""
                    text = await self.ocr_processor.perform_ocr_on_crop(
                        crop_b64,
                        self_correction=self_correction,
                        binarize=binarize,
                        dual_engine=dual_engine,
                    )
                    return idx, text
            except CircuitOpenError:
                raise
            except Exception as e:
                import logging

                logging.warning(
                    f"Dense OCR failed for box {idx}: {type(e).__name__}: {e}"
                )
                return idx, ""

        results: dict[int, str] = {}
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(ocr_one(i, bbox))
                for i, (bbox, _) in enumerate(structured)
            ]
            for fut in asyncio.as_completed(tasks):
                idx, text = await fut
                results[idx] = text.strip()
        return [(bbox, results.get(i, "")) for i, (bbox, _) in enumerate(structured)]

    async def _refine_uncertain(
        self,
        sparse_structured: dict[int, PageBoxes],
        images_dict: dict[int, str],
        semaphore: asyncio.Semaphore,
        progress: ProgressCallback | None,
        self_correction: bool = False,
        binarize: bool = False,
        dual_engine: bool = False,
    ) -> None:
        targets: list[tuple[int, int, list[float]]] = []
        for p_num, aligned in sparse_structured.items():
            for idx, (bbox, text) in enumerate(aligned):
                if not text.strip() and _is_refinable(bbox):
                    targets.append((p_num, idx, bbox))

        if not targets:
            return

        total = len(targets)
        await notify(
            progress, "refine", 0, total, f"Refining {total} uncertain boxes..."
        )

        page_images: dict[int, Image.Image] = {}
        pages_needed = {p_num for p_num, _, _ in targets}
        for p_num in pages_needed:
            page_images[p_num] = await asyncio.to_thread(
                _decode_page_image, images_dict[p_num]
            )

        async def refine_one(
            p_num: int, idx: int, bbox: list[float]
        ) -> tuple[int, int, str]:
            try:
                async with semaphore:
                    crop_b64 = await asyncio.to_thread(
                        crop_for_ocr_from_image, page_images[p_num], bbox
                    )
                    if crop_b64 is None:
                        return p_num, idx, ""
                    text = await self.ocr_processor.perform_ocr_on_crop(
                        crop_b64,
                        self_correction=self_correction,
                        binarize=binarize,
                        dual_engine=dual_engine,
                    )
                    return p_num, idx, text
            except CircuitOpenError:
                raise
            except Exception as e:
                import logging

                logging.warning(
                    f"Refine failed for page {p_num} box {idx}: {type(e).__name__}: {e}"
                )
                return p_num, idx, ""

        completed = 0
        refined_indices: dict[int, set[int]] = defaultdict(set)
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(refine_one(p, i, b)) for p, i, b in targets]
            for coro in asyncio.as_completed(tasks):
                p_num, idx, text = await coro
                bbox_cur, _ = sparse_structured[p_num][idx]
                sparse_structured[p_num][idx] = (bbox_cur, text.strip())
                refined_indices[p_num].add(idx)
                completed += 1
                await notify(
                    progress,
                    "refine",
                    completed,
                    total,
                    f"Refining boxes ({completed}/{total})",
                )

        for p_num, idxs in refined_indices.items():
            _drop_refined_duplicates(sparse_structured[p_num], idxs)
