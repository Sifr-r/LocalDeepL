from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from PIL import Image

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.document import BBox, DenseMode, SpellcheckMode
from omniscribe.core.ocr import OCRProcessor
from omniscribe.core.ocr.resilience import CircuitOpenError
from omniscribe.core.ocr_quality import TrustOrchestrator
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.preprocessing import PagePreprocessingOptions, PagePreprocessor
from omniscribe.core.processors import DocumentProcessor
from omniscribe.core.routing import QualityRoutingOptions, QualityRoutingPolicy
from omniscribe.core.text_layer_recall import PdfTextLayerRecall
from omniscribe.core.text_recall import WhitespaceRecallBooster
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

logger = logging.getLogger(__name__)

# Phase 3 finding 2.3 — bound the per-page decoded-image LRU to keep
# long-document runs from holding a PIL.Image per page for the whole run.
# Invariant (CQ-4): must stay >= DETECT_CHUNK_SIZE (workflows.utils). The
# cache is populated per chunk by ``_decode_chunk_bytes`` and consumed by
# ``_apply_recall`` / ``_ocr_per_box`` within the same chunk; a smaller cap
# would evict in-flight pages and silently degrade to the fallback decode
# (still correct, slower).
_DECODED_CACHE_MAX_ENTRIES = 16


def _decode_chunk_bytes(
    images_dict: Mapping[int, str],
    chunk_pages: Sequence[int],
    on_decoded: Callable[[int, Image.Image], None] | None = None,
) -> list[bytes]:
    """Decode a batch of base64 page images to bytes (synchronous helper).

    Runs inside ``asyncio.to_thread`` so the CPU-bound decode does not block the
    event loop. See refactor §1.3 in ``docs/superpowers/specs/deep_refactor_report.md``.

    When ``on_decoded`` is provided, it is invoked with each ``(page_num, image)``
    so downstream stages (``_ocr_per_box``, ``_refine_uncertain``) can skip a
    second base64 → image decode. The callback is the LRU-aware path: the
    engine forwards ``_decoded_put`` here so the cache evicts old entries
    instead of growing unbounded. See refactor §1.2 (per-page decode cache).
    """
    result: list[bytes] = []
    for p in chunk_pages:
        b64 = images_dict[p]
        raw = base64.b64decode(b64)
        result.append(raw)
        if on_decoded is not None:
            with contextlib.suppress(Exception):
                on_decoded(p, _decode_page_image(b64))
    return result


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
        # Phase B (review M2) — forward `block_callbacks` to the base
        # so the per-block / per-page event hook reaches `_ocr_pages`.
        # The default `None` keeps every existing call site working
        # unchanged (the in-process `OCRPipeline` user, all the
        # workflows tests).
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
        # Whitespace recall (spec 2026-08-14) — merges boxes Surya missed
        # into the detection output. None keeps the legacy byte-identical
        # behavior for direct engine users and the existing tests.
        self.recall_booster = recall_booster
        # Text-layer recall (TODOS.md CEO-voice item) — second box source:
        # lines recovered from a digital PDF's embedded text layer, merged
        # after the whitespace booster so dedup sees both sources' extras.
        self.text_layer_recall = text_layer_recall
        # Phase 1.2 (per-page decode cache) — populated by `_detect_layout`
        # via `_decode_chunk_bytes` (which forwards into ``_decoded_put``),
        # consumed by `_ocr_per_box` (via the `page_image` parameter it
        # already accepts) and `_refine_uncertain`. Implemented as a
        # bounded LRU so a 1000-page run never holds a PIL.Image per page
        # for the lifetime of the request — Phase 3 finding 2.3.
        # Cleared at the top of every ``execute`` so per-run state never
        # leaks across requests. See refactor §1.2 in
        # ``docs/superpowers/specs/deep_refactor_report.md``.
        self._decoded_cache: OrderedDict[int, Image.Image] = OrderedDict()

    def _decoded_get(self, page_num: int) -> Image.Image | None:
        """Return the cached image for ``page_num`` and mark it most-recently-used.

        Returns ``None`` on a miss so callers can fall back to a fresh
        decode. Reads update the LRU ordering, matching the standard
        ``OrderedDict``-backed LRU pattern.
        """
        cached = self._decoded_cache.get(page_num)
        if cached is not None:
            self._decoded_cache.move_to_end(page_num)
        return cached

    def _decoded_put(self, page_num: int, image: Image.Image) -> None:
        """Cache ``image`` for ``page_num`` and evict the LRU entry if over capacity.

        Writes are LRU-aware: a re-put bumps the entry to most-recently-used
        and, once the cache exceeds ``_DECODED_CACHE_MAX_ENTRIES``, the
        least-recently-used entry is dropped.
        """
        self._decoded_cache[page_num] = image
        self._decoded_cache.move_to_end(page_num)
        if len(self._decoded_cache) > _DECODED_CACHE_MAX_ENTRIES:
            self._decoded_cache.popitem(last=False)

    def _reset_run_state(self) -> None:
        """Clear run-scoped state. Call at the top of every ``execute``.

        Extends :meth:`EngineBase._reset_run_state` to also drop the
        per-page decoded-image cache (see __init__ docstring; refactor
        §1.2). The cache can hold every page in a 1000-page PDF as a
        PIL.Image, so resetting it is mandatory between requests.
        """
        super()._reset_run_state()
        self._decoded_cache = OrderedDict()

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

        # Phase 3 fix (report §2.1) — the worker thread is wrapped in
        # ``asyncio.to_thread`` and is therefore not interruptible from
        # the main loop. The WebSocket cancel channel is consulted at
        # every page boundary via this callable so a user-initiated
        # cancel actually short-circuits the VLM spend instead of
        # waiting for the run to finish. The check sits here so an
        # already-cancelled request aborts *before* layout detection
        # is even started.
        if cancel_check is not None and cancel_check():
            raise OCRCancelled("OCR cancelled before layout detection.")

        # --- Phase 2: batched layout detection ---
        pages_structured = await self._detect_layout(
            images_dict=images_dict,
            page_nums=page_nums,
            progress=progress,
            input_path=input_path,
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
            cancel_check=cancel_check,
        )

        # Phase 3 fix (report §2.1) — gate the refine phase on the cancel
        # signal as well. Refine re-OCRs every empty sparse box, so
        # without this check a cancelled request would still pay for
        # the second pass on every sparse page.
        if cancel_check is not None and cancel_check():
            raise OCRCancelled("OCR cancelled after OCR loop.")

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
        # Default-off at the engine level: only callers that pass a
        # RepairOptions opt in (the API layer does; in-process OCRPipeline
        # users keep the pre-loop behavior).
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
            trust_model_id=trust_model_id,
            trust_images_dict=images_dict,
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
        input_path: str = "",
    ) -> dict[int, PageBoxes]:
        """Run batched Surya layout detection and seed each page with empty text."""
        await notify(
            progress, "detect", 0, 1, f"Detecting layout for {len(page_nums)} pages..."
        )

        batch_boxes: list[list[BBox]] = []
        booster = self.recall_booster
        recall_pages_touched = 0
        recall_boxes_added = 0
        # The booster accumulates its drop counter across ``supplement``
        # calls (it may outlive one chunk, and the engine may be reused),
        # so the run summary reads a delta. ``getattr`` keeps duck-typed
        # test boosters without the counter working.
        dropped_before = getattr(booster, "candidates_dropped", 0)
        text_layer = self.text_layer_recall
        tl_pages_touched = 0
        tl_boxes_added = 0
        tl_dropped_before = getattr(text_layer, "candidates_dropped", 0)
        # One open document per detect pass; ``open`` is a no-op (False)
        # for non-PDF inputs and env-disabled sources, and the finally
        # below releases the handle even on cancellation.
        tl_open = False
        if text_layer is not None:
            tl_open = await asyncio.to_thread(text_layer.open, input_path)
        try:
            for i in range(0, len(page_nums), DETECT_CHUNK_SIZE):
                chunk_pages = page_nums[i : i + DETECT_CHUNK_SIZE]
                # Decode base64 inside the worker thread alongside Surya inference
                # so neither the list comp nor the (possibly large) image bytes
                # block the asyncio event loop. (Refactor §1.3.) The cache write
                # below populates ``self._decoded_cache`` with a ``PIL.Image`` per
                # page so ``_ocr_per_box`` / ``_refine_uncertain`` can skip a
                # second decode. (Refactor §1.2.)
                chunk_bytes = await asyncio.to_thread(
                    _decode_chunk_bytes, images_dict, chunk_pages, self._decoded_put
                )
                chunk_boxes = await asyncio.to_thread(
                    self.aligner.get_detected_boxes_batch, chunk_bytes
                )
                if booster is not None and getattr(booster, "enabled", True):
                    # T6: a disabled booster short-circuits ``supplement`` anyway;
                    # skipping here avoids the per-page decode + thread round-trip.
                    # The T2 run summary below still emits its zero-count line.
                    chunk_boxes, touched, added = await self._apply_recall(
                        chunk_pages=chunk_pages,
                        images_dict=images_dict,
                        chunk_boxes=chunk_boxes,
                    )
                    recall_pages_touched += touched
                    recall_boxes_added += added
                if tl_open:
                    # Runs after the booster so its dedup reference includes
                    # the booster's extras — the two sources never add the
                    # same missed line twice.
                    chunk_boxes, touched, added = await self._apply_text_layer_recall(
                        chunk_pages=chunk_pages,
                        chunk_boxes=chunk_boxes,
                    )
                    tl_pages_touched += touched
                    tl_boxes_added += added
                batch_boxes.extend(chunk_boxes)
                await notify(
                    progress,
                    "detect",
                    min(i + DETECT_CHUNK_SIZE, len(page_nums)),
                    len(page_nums),
                    f"Detecting layout ({min(i + DETECT_CHUNK_SIZE, len(page_nums))}/{len(page_nums)})...",
                )
        finally:
            if tl_open and text_layer is not None:
                await asyncio.to_thread(text_layer.close)

        pages_structured: dict[int, PageBoxes] = {
            p: [(box, "") for box in batch_boxes[i]] for i, p in enumerate(page_nums)
        }
        if booster is not None:
            # T2 run summary: one INFO line per run so ops can tell whether
            # the default-ON pass is doing anything — including the
            # zero-count line when the booster is env-disabled.
            dropped = getattr(booster, "candidates_dropped", 0) - dropped_before
            logger.info(
                "Whitespace recall summary: %d box(es) added on %d of %d page(s); "
                "%d candidate(s) dropped by filters",
                recall_boxes_added,
                recall_pages_touched,
                len(page_nums),
                dropped,
            )
        if text_layer is not None:
            # Per-source tally (E7-lite): same shape as the booster summary,
            # emitted even when the source never opened (zero counts tell
            # ops the pass is wired but inactive for this input).
            tl_dropped = (
                getattr(text_layer, "candidates_dropped", 0) - tl_dropped_before
            )
            logger.info(
                "Text-layer recall summary: %d box(es) added on %d of %d page(s); "
                "%d line(s) dropped by dedup/cap",
                tl_boxes_added,
                tl_pages_touched,
                len(page_nums),
                tl_dropped,
            )
        await notify(progress, "detect", 1, 1, "Layout detection complete.")
        return pages_structured

    async def _apply_recall(
        self,
        *,
        chunk_pages: Sequence[int],
        images_dict: dict[int, str],
        chunk_boxes: list[list[BBox]],
    ) -> tuple[list[list[BBox]], int, int]:
        """Merge whitespace-recall boxes into each page's Surya boxes.

        Returns ``(merged_boxes, pages_touched, boxes_added)`` so the
        caller can build the T2 INFO run summary. Best-effort recall
        improvement: a per-page failure degrades to the original Surya
        boxes and never fails the job. Images come from the per-page
        decode cache populated by ``_decode_chunk_bytes`` in the same
        chunk; the fallback decode covers an LRU eviction.
        """
        # T6: if-guard rather than ``assert`` — asserts are stripped under
        # ``python -O``; the engine must degrade to the Surya boxes instead.
        booster = self.recall_booster
        if booster is None:
            return chunk_boxes, 0, 0
        merged: list[list[BBox]] = []
        pages_touched = 0
        boxes_added = 0
        for p_num, boxes in zip(chunk_pages, chunk_boxes, strict=False):
            try:
                image = self._decoded_get(p_num)
                if image is None:
                    image = await asyncio.to_thread(
                        _decode_page_image, images_dict[p_num]
                    )
                    self._decoded_put(p_num, image)
                extra = await asyncio.to_thread(booster.supplement, image, boxes)
                # CQ-3: force recall boxes onto the ``BBox`` tuple contract at
                # the merge boundary. ``HybridAligner`` emits tuples, so this
                # keeps the merged page homogeneous whatever container a
                # duck-typed booster returns.
                extra = [(b[0], b[1], b[2], b[3]) for b in extra]
            except Exception as e:
                logger.warning(
                    "Whitespace recall failed for page %s: %s: %s",
                    p_num,
                    type(e).__name__,
                    e,
                )
                merged.append(boxes)
                continue
            if extra:
                logger.debug(
                    "Whitespace recall added %d box(es) on page %s",
                    len(extra),
                    p_num,
                )
                pages_touched += 1
                boxes_added += len(extra)
                boxes = sorted([*boxes, *extra], key=lambda b: (b[1], b[0]))
            merged.append(boxes)
        return merged, pages_touched, boxes_added

    async def _apply_text_layer_recall(
        self,
        *,
        chunk_pages: Sequence[int],
        chunk_boxes: list[list[BBox]],
    ) -> tuple[list[list[BBox]], int, int]:
        """Merge text-layer recall boxes into each page's merged boxes.

        Second recall source (TODOS.md CEO-voice item): lines recovered
        from the input PDF's embedded text layer. Same contract as
        ``_apply_recall`` — returns ``(merged_boxes, pages_touched,
        boxes_added)``, fails open per page, and normalizes extras onto
        the ``BBox`` tuple contract at the merge boundary. The dedup
        reference is the page's current merged boxes, which already
        include any whitespace-booster extras applied in this chunk.
        """
        source = self.text_layer_recall
        if source is None:
            return chunk_boxes, 0, 0
        merged: list[list[BBox]] = []
        pages_touched = 0
        boxes_added = 0
        for p_num, boxes in zip(chunk_pages, chunk_boxes, strict=False):
            try:
                extra = await asyncio.to_thread(source.supplement, p_num, boxes)
                extra = [(b[0], b[1], b[2], b[3]) for b in extra]
            except Exception as e:
                logger.warning(
                    "Text-layer recall failed for page %s: %s: %s",
                    p_num,
                    type(e).__name__,
                    e,
                )
                merged.append(boxes)
                continue
            if extra:
                logger.debug(
                    "Text-layer recall added %d box(es) on page %s",
                    len(extra),
                    p_num,
                )
                pages_touched += 1
                boxes_added += len(extra)
                boxes = sorted([*boxes, *extra], key=lambda b: (b[1], b[0]))
            merged.append(boxes)
        return merged, pages_touched, boxes_added

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
        cancel_check: CancelCheck | None = None,
    ) -> None:
        """Fan out OCR across pages, dispatching sparse vs dense per page."""
        semaphore = asyncio.Semaphore(max(1, concurrency))
        total = len(page_nums)

        async def process_page(
            p_num: int,
        ) -> tuple[int, PageBoxes, Exception | None]:
            try:
                if p_num in per_box_pages:
                    # Refactor §1.2: reuse the PIL.Image decoded during
                    # layout detection instead of re-decoding in the worker
                    # thread. Falls back to ``None`` (and the existing
                    # in-worker decode) when ``_detect_layout`` was bypassed
                    # (e.g. in tests that call ``_ocr_pages`` directly).
                    cached_image = self._decoded_get(p_num)
                    aligned = await self._ocr_per_box(
                        images_dict[p_num],
                        pages_structured[p_num],
                        semaphore,
                        self_correction,
                        binarize,
                        dual_engine,
                        page_image=cached_image,
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
            except OCRCancelled:
                # Phase 3 fix (report §2.1) — let the cancel signal
                # propagate out of the per-page isolation block. The
                # generic ``except Exception`` below would otherwise
                # swallow it as a benign per-page failure and the
                # cancel would never reach the route handler.
                raise
            except Exception as e:
                logger.warning(
                    "OCR failed for page %s: %s: %s", p_num, type(e).__name__, e
                )
                return p_num, pages_structured[p_num], e

        completed = 0
        ocr_label = (
            "OCR"
            if not per_box_pages
            else f"OCR ({len(per_box_pages)} dense / {total - len(per_box_pages)} sparse)"
        )
        await notify(progress, "ocr", 0, total, f"{ocr_label} (0/{total})...")
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(process_page(p)) for p in page_nums]
                for coro in asyncio.as_completed(tasks):
                    # Phase 3 fix (report §2.1) — the cooperative cancel
                    # check fires *between* page completions. Catching it
                    # here (before draining the rest of the TaskGroup via
                    # ``tg.__aexit__``) keeps the engine from paying the
                    # VLM cost on remaining in-flight pages: as soon as
                    # the last dispatched page lands, the OCRCancelled
                    # we raise propagates out of ``__aexit__`` and
                    # cancels every still-in-flight child task.
                    p_num, aligned, page_error = await coro

                    pages_structured[p_num] = aligned
                    completed += 1

                    if cancel_check is not None and cancel_check():
                        raise OCRCancelled(
                            f"OCR cancelled after page {p_num} ({completed}/{total})."
                        )

                    # Phase B (review M2) — emit per-block and per-page
                    # events through the injected callback set instead of
                    # importing the WebSocket manager. The engine no
                    # longer depends on `omniscribe.api`; the API layer
                    # is responsible for translating these callbacks
                    # into WebSocket frames (or any other transport).
                    #
                    # The emissions sit inside the `as_completed` loop on
                    # purpose: it gives the UI a strictly monotonic
                    # per-block ordering across pages, which the live
                    # bbox overlay assumes. If you reorder this loop,
                    # the live UI will start flashing blocks out of
                    # order.
                    await self._emit_page_callbacks(
                        p_num,
                        aligned,
                        _estimate_confidence,
                    )

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
        except* OCRCancelled as eg:
            # Python 3.12 ``asyncio.TaskGroup`` wraps every non-Exception
            # sub-exception (including OCRCancelled, a BaseException
            # subclass) in a ``BaseExceptionGroup`` when it's raised
            # inside the group. Unwrap so the route handler's plain
            # ``except OCRCancelled`` catches it as expected.
            raise eg.exceptions[0] from None

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
            cancel_check=cancel_check,
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
        trust_model_id: str = "unknown",
        trust_images_dict: dict[int, str] | None = None,
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

        # Phase 2 — apply the OCR quality trust layer. Runs *after*
        # document processors and *before* quality routing so the trust
        # signals see the fully-cleaned text. ``_apply_trust`` is a
        # no-op when no orchestrator was injected (default), which
        # keeps the pre-Phase-2 byte layout intact.
        document_result = await self._apply_trust(
            document_result,
            model_id=trust_model_id,
            trust_images_dict=trust_images_dict,
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

        async def ocr_one(idx: int, bbox: BBox) -> tuple[int, str]:
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
                logger.warning(
                    "Dense OCR failed for box %s: %s: %s", idx, type(e).__name__, e
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
        cancel_check: CancelCheck | None = None,
    ) -> None:
        targets: list[tuple[int, int, BBox]] = []
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
            # Refactor §1.2: reuse the PIL.Image decoded during layout
            # detection (or OCR per-box) when available; otherwise fall
            # back to the original per-call decode in a worker thread.
            cached = self._decoded_get(p_num)
            page_images[p_num] = (
                cached
                if cached is not None
                else await asyncio.to_thread(_decode_page_image, images_dict[p_num])
            )

        async def refine_one(p_num: int, idx: int, bbox: BBox) -> tuple[int, int, str]:
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
            except OCRCancelled:
                # Phase 3 fix (report §2.1) — let the cancel signal
                # propagate past the per-box isolation block.
                raise
            except Exception as e:
                logger.warning(
                    "Refine failed for page %s box %s: %s: %s",
                    p_num,
                    idx,
                    type(e).__name__,
                    e,
                )
                return p_num, idx, ""

        completed = 0
        refined_indices: dict[int, set[int]] = defaultdict(set)
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(refine_one(p, i, b)) for p, i, b in targets]
                for coro in asyncio.as_completed(tasks):
                    # Phase 3 fix (report §2.1) — same cooperative cancel
                    # check as in :meth:`_ocr_pages`. Refine re-OCRs
                    # every empty box, so without this check a cancelled
                    # request would still pay for every queued box.
                    p_num, idx, text = await coro
                    bbox_cur, _ = sparse_structured[p_num][idx]
                    sparse_structured[p_num][idx] = (bbox_cur, text.strip())
                    refined_indices[p_num].add(idx)
                    completed += 1

                    if cancel_check is not None and cancel_check():
                        raise OCRCancelled(
                            f"OCR cancelled after refine box {completed}/{total}."
                        )

                    await notify(
                        progress,
                        "refine",
                        completed,
                        total,
                        f"Refining boxes ({completed}/{total})",
                    )
        except* OCRCancelled as eg:
            # See the matching note in :meth:`_ocr_pages` —
            # ``asyncio.TaskGroup`` wraps the OCRCancelled in a
            # ``BaseExceptionGroup`` in Python 3.12; unwrap so the
            # route handler's ``except OCRCancelled`` catches it.
            raise eg.exceptions[0] from None

        for p_num, idxs in refined_indices.items():
            _drop_refined_duplicates(sparse_structured[p_num], idxs)

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

        Runs after refine (empty-box recovery already happened) and before
        finalize. Only blocks whose estimated confidence is below
        ``repair_options.target`` are re-OCRed, via the same
        crop → ``perform_ocr_on_crop`` primitive refine uses. Progress
        reuses the ``refine`` stage so the pinned stage-weight bands keep
        reporting monotonically. Returns one summary per visited page.

        Repair is intentionally sequential (one block at a time): the
        accept/stall decision is inherently serial per block and repair
        calls are rare, so P1 does not fan out across pages or blocks;
        ``concurrency`` is accepted for signature parity with the other
        engine phases.
        """
        loop = QualityRepairLoop(repair_options)
        cb = self.block_callbacks

        targets = sum(
            1
            for p_num in page_nums
            for _, text in pages_structured.get(p_num, [])
            if text.strip() and _estimate_confidence(text) < repair_options.target
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

        summaries: list[PageRepairSummary] = []
        completed = 0
        for p_num in page_nums:
            aligned = pages_structured.get(p_num)
            if not aligned:
                continue

            # Refactor §1.2: reuse the decoded page image when available.
            cached = self._decoded_get(p_num)
            page_image = (
                cached
                if cached is not None
                else await asyncio.to_thread(_decode_page_image, images_dict[p_num])
            )

            async def re_ocr(
                block_idx: int,
                bbox: tuple[float, float, float, float],
                *,
                _img: Image.Image = page_image,
                _page: int = p_num,
            ) -> str:
                nonlocal completed
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
                    # Spec §3.2 graceful degradation: surface the
                    # warning frame, then re-raise so repair_page
                    # keeps the best-so-far text and the job goes on.
                    if on_warning is not None:
                        await on_warning(_page, exc)
                    raise
                completed += 1
                await notify(
                    progress,
                    "refine",
                    min(completed, targets),
                    targets,
                    f"Repairing below-target blocks ({min(completed, targets)}/{targets})",
                )
                return text

            summary = await loop.repair_page(
                page_idx=p_num,
                page_blocks=aligned,
                re_ocr=re_ocr,
                on_block_retry=cb.on_block_retry,
                on_block_revised=cb.on_block_revised,
            )
            summaries.append(summary)
            if cb.on_quality_summary is not None:
                await cb.on_quality_summary(
                    "page",
                    p_num,
                    summary.target,
                    summary.avg_confidence,
                    summary.repaired_count,
                    summary.below_target_count,
                )
        return summaries
