from __future__ import annotations

import asyncio
import base64
import io
from collections import defaultdict
from collections.abc import Sequence

from PIL import Image

from local_deepl.core.aligner import HybridAligner
from local_deepl.core.document import DenseMode, SpellcheckMode
from local_deepl.core.ocr import OCRProcessor
from local_deepl.core.pdf import PDFHandler
from local_deepl.core.preprocessing import PagePreprocessingOptions, PagePreprocessor
from local_deepl.core.processors import DocumentProcessor
from local_deepl.core.routing import QualityRoutingOptions, QualityRoutingPolicy
from local_deepl.core.workflows.base import (
    EngineBase,
    OutputWriter,
    PageBoxes,
    PagesData,
    ProgressCallback,
    WarningCallback,
    notify,
)
from local_deepl.utils.image import crop_for_ocr_from_image


# Lightweight per-crop confidence heuristic (no new deps).
def _estimate_confidence(text: str) -> float:
    """Cheap confidence proxy for OCR output.

    Returns a value in [0, 1] based on text quality signals:
    - non-empty + alphabetic characters + multiple words => high
    - single character or empty => low
    - mostly punctuation or digits => medium
    """
    if not text or not text.strip():
        return 0.0
    stripped = text.strip()
    alpha = sum(1 for c in stripped if c.isalpha())
    if alpha == 0:
        return 0.3
    words = stripped.split()
    if len(words) >= 3:
        return 0.85
    if len(words) >= 1 and alpha >= 3:
        return 0.7
    return 0.4


# A bbox is "refinable" if it has enough normalized area to be worth a
# per-crop re-OCR pass; below these sizes the LLM round-trip costs more
# than it gains.
REFINABLE_MIN_WIDTH = 0.03
REFINABLE_MIN_HEIGHT = 0.008

# Surya layout detection is batched; this chunk size keeps memory + GPU pressure
# predictable without dominating the detect stage wall clock.
DETECT_CHUNK_SIZE = 10


def parse_page_range(page_str: str, total_pages: int) -> list[int]:
    """Parse a 1-indexed range like '1-3,5,7-9' into sorted 0-indexed pages."""
    pages: set[int] = set()
    try:
        for part in page_str.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s), int(end_s)
                for p in range(start, end + 1):
                    if 1 <= p <= total_pages:
                        pages.add(p - 1)
            else:
                p = int(part)
                if 1 <= p <= total_pages:
                    pages.add(p - 1)
    except ValueError as e:
        raise ValueError(f"Invalid page range syntax: '{page_str}'") from e
    return sorted(pages)


def _decode_page_image(image_b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")


def _normalize_for_dedup(text: str) -> str:
    return " ".join(text.lower().split())


def _drop_refined_duplicates(
    page_boxes: PageBoxes,
    refined_indices: set[int],
    *,
    radius: int = 4,
) -> None:
    for r_idx in sorted(refined_indices):
        r_bbox, r_text = page_boxes[r_idx]
        if not r_text:
            continue
        r_norm = _normalize_for_dedup(r_text)
        if not r_norm:
            continue
        lo = max(0, r_idx - radius)
        hi = min(len(page_boxes), r_idx + radius + 1)
        for o_idx in range(lo, hi):
            if o_idx == r_idx or o_idx in refined_indices:
                continue
            _, o_text = page_boxes[o_idx]
            if not o_text:
                continue
            o_norm = _normalize_for_dedup(o_text)
            if r_norm in o_norm:
                page_boxes[r_idx] = (r_bbox, "")
                break


def _is_refinable(bbox: list[float]) -> bool:
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width > REFINABLE_MIN_WIDTH and height > REFINABLE_MIN_HEIGHT


class HybridEngine(EngineBase):
    def __init__(
        self,
        aligner: HybridAligner,
        ocr_processor: OCRProcessor,
        pdf_handler: PDFHandler,
        output_writer: OutputWriter,
        document_processors: Sequence[DocumentProcessor] | None = None,
        page_preprocessor: PagePreprocessor | None = None,
    ) -> None:
        super().__init__(
            output_writer=output_writer,
            document_processors=document_processors,
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
        if dense_mode not in [m.value for m in DenseMode]:
            raise ValueError(
                f"dense_mode must be one of {[m.value for m in DenseMode]}; got {dense_mode!r}"
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
    ) -> tuple[dict[int, str], list[int], dict[int, dict[str, object]]]:
        """Render the input to per-page images and apply optional preprocessing."""
        await notify(progress, "convert", 0, 1, "Converting PDF to images...")
        images_dict = await asyncio.to_thread(
            self.pdf_handler.convert_to_images, input_path, dpi, max_image_dim
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
                # Emit per-page block events for the live bbox overlay.
                for b_idx, (b_bbox, b_text) in enumerate(aligned):
                    if b_text and b_text.strip():
                        try:
                            from local_deepl.api.routers.websocket import (
                                manager as _ws_manager,
                            )

                            await _ws_manager.send_block(
                                getattr(progress, "channel_id", None),
                                page_idx=p_num,
                                block_idx=b_idx,
                                bbox=list(b_bbox),
                                text=b_text,
                                kind="text",
                                confidence=_estimate_confidence(b_text),
                            )
                        except Exception:
                            pass
                
                # Emit page complete event
                try:
                    from local_deepl.api.routers.websocket import (
                        manager as _ws_manager,
                    )
                    await _ws_manager.send_page_complete(
                        getattr(progress, "channel_id", None),
                        page_idx=p_num,
                    )
                except Exception:
                    pass

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
    ) -> PageBoxes:
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
