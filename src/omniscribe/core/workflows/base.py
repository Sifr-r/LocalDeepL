from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PIL import Image

    from omniscribe.core.callbacks import BlockCallbackSet
    from omniscribe.core.document import (
        BBox,
        DocumentPage,
        DocumentResult,
        SpellcheckMode,
    )
    from omniscribe.core.ocr_quality import TrustOrchestrator
    from omniscribe.core.processors import DocumentProcessor

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]
WarningCallback = Callable[[int, BaseException], Awaitable[None]]
OutputWriter = Callable[[str, str, dict, int], None]


@runtime_checkable
class DocumentResultWriter(Protocol):
    """Rich output writer that receives the full DocumentResult.

    Writers implementing this protocol get access to block kinds,
    confidence, metadata, and reading order — everything the legacy
    ``{page: [(bbox, text)]}`` conversion drops. The engine prefers
    this interface when the injected writer supports it and falls back
    to the legacy 4-arg callable otherwise.
    """

    def write_document_result(
        self,
        input_path: str,
        output_path: str,
        document_result: DocumentResult,
        dpi: int,
    ) -> None: ...


#: Accepted output-writer shapes: the legacy 4-arg callable or a rich writer.
AnyOutputWriter = OutputWriter | DocumentResultWriter


async def notify(
    cb: ProgressCallback | None, stage: str, current: int, total: int, message: str
) -> None:
    if cb is not None:
        await cb(stage, current, total, message)


PageBoxes = list[tuple[tuple[float, float, float, float], str]]
PagesData = dict[int, PageBoxes]


#: Type of the optional cancel-check callable engines accept on ``execute``.
#: Returns ``True`` when the in-flight run should abort cooperatively at the
#: next page boundary. See :class:`OCRCancelled` and report finding 2.1.
CancelCheck = Callable[[], bool]


class OCRCancelled(BaseException):
    """Raised by the OCR engines when the cooperative cancel-check fires.

    Inherits from :class:`BaseException` (not :class:`Exception`) so the
    per-page isolation blocks in :meth:`HybridEngine._ocr_pages` and
    :meth:`HybridEngine._refine_pages` do not swallow the signal as a
    page-level failure. The API layer catches it and translates it into
    a 503 Service Unavailable with ``cancelled: true`` so the WebSocket
    cancel handshake actually short-circuits the VLM spend.

    Phase 3 fix for report finding 2.1 (HIGH) — see
    ``docs/superpowers/specs/deep_refactor_report.md`` §2.1.
    """


class EngineBase:
    """
    Base class for OCR workflows (Hybrid and Grounded).

    Provides three pieces of shared machinery:

    1. Run-scoped state (``last_document_result``, ``last_failed_pages``) reset
       at the top of every ``execute`` call via :meth:`_reset_run_state`.
    2. Text-only post-processing helpers (``_cross_page_merge``,
       ``_run_spellcheck``).
    3. The post-process → assemble → emit pipeline (:meth:`_build_document_result`
       and :meth:`_emit`) that both engines route their final pages through so
       the output-writing code path lives in exactly one place.

    Subclasses are expected to accept ``output_writer`` and
    ``document_processors`` in their ``__init__`` and forward them via
    ``super().__init__(...)``.
    """

    def __init__(
        self,
        output_writer: AnyOutputWriter,
        document_processors: Sequence[DocumentProcessor] | None = None,
        block_callbacks: BlockCallbackSet | None = None,
        trust_orchestrator: TrustOrchestrator | None = None,
    ) -> None:
        self.output_writer = output_writer
        self.document_processors: tuple[DocumentProcessor, ...] = tuple(
            document_processors or ()
        )
        # Phase B (review M2) — the engine no longer imports the
        # WebSocket manager. Per-block / per-page events flow through
        # the injected callback set; the API layer wires those to
        # whatever transport the deployment uses. `None` means "no
        # observers," which is the right default for in-process
        # programmatic use of `OCRPipeline` (no WebSocket, no
        # listeners, pure engine output).
        from omniscribe.core.callbacks import BlockCallbackSet

        self.block_callbacks: BlockCallbackSet = (
            block_callbacks if block_callbacks is not None else BlockCallbackSet()
        )
        # Phase 2 — the OCR quality trust layer (design §11.2). ``None``
        # means the layer is off; engines treat that as a true no-op
        # (identity passthrough, identical bytes to the pre-Phase-2
        # path). See :func:`omniscribe.core.ocr_quality.build_trust_orchestrator`
        # for the factory. Subclasses drive ``_apply_trust`` (the
        # default is a no-op identity; the engines below override).
        self.trust_orchestrator: TrustOrchestrator | None = trust_orchestrator

        # State populated after a run. Reset by ``_reset_run_state`` at the top
        # of each ``execute``; lifting into the base keeps ``OCRPipeline`` honest
        # about which attributes belong to the engine contract.
        self.last_document_result: DocumentResult | None = None
        self.last_failed_pages: list[int] = []

    def _reset_run_state(self) -> None:
        """Clear run-scoped state. Call at the top of every ``execute``."""
        self.last_document_result = None
        self.last_failed_pages = []

    async def _apply_trust(
        self,
        document_result: DocumentResult,
        *,
        model_id: str,
        trust_images_dict: dict[int, str] | None = None,
    ) -> DocumentResult:
        """Apply the trust layer to ``document_result``.

        If ``trust_images_dict`` is provided, page images are decoded on-demand for
        pages present in the map. The orchestrator is invoked fail-open per page.
        """
        if self.trust_orchestrator is None or not document_result.pages:
            return document_result

        from omniscribe.core.document import DocumentResult
        from omniscribe.core.image_utils import decode_base64_image

        scored_pages: list[DocumentPage] = []
        for page in document_result.pages:
            page_image: Image.Image | None = None
            if trust_images_dict and page.page_index in trust_images_dict:
                try:
                    page_image = decode_base64_image(trust_images_dict[page.page_index])
                except Exception:
                    page_image = None

            try:
                new_blocks = self.trust_orchestrator(
                    list(page.blocks),
                    page_image,
                    model_id=model_id,
                    page_size=None,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "trust orchestrator failed on page %d; falling back: %s",
                    page.page_index,
                    exc,
                )
                new_blocks = list(page.blocks)
            scored_pages.append(dataclasses.replace(page, blocks=list(new_blocks)))

        return DocumentResult(
            pages=scored_pages,
            source_path=document_result.source_path,
            tree=document_result.tree,
        )

    def _cross_page_merge(
        self,
        pages_structured: PagesData,
        page_nums: Sequence[int],
    ) -> None:
        """
        Post-processing step that inspects the end of each page and merges
        trailing sentences without terminal punctuation into the first line of the
        subsequent page.
        """
        page_list = list(page_nums)
        for i in range(len(page_list) - 1):
            p1 = page_list[i]
            p2 = page_list[i + 1]

            p1_boxes = pages_structured.get(p1, [])
            last_idx = -1
            for idx in range(len(p1_boxes) - 1, -1, -1):
                if p1_boxes[idx][1].strip():
                    last_idx = idx
                    break

            p2_boxes = pages_structured.get(p2, [])
            first_idx = -1
            for idx in range(len(p2_boxes)):
                if p2_boxes[idx][1].strip():
                    first_idx = idx
                    break

            if last_idx != -1 and first_idx != -1:
                _last_bbox, last_text = p1_boxes[last_idx]
                first_bbox, first_text = p2_boxes[first_idx]

                last_text_stripped = last_text.strip()
                # If the last box's text does not end with sentence-ending punctuation, merge them.
                if last_text_stripped and last_text_stripped[-1] not in (".", "!", "?"):
                    merged_text = last_text_stripped + " " + first_text.strip()
                    p2_boxes[first_idx] = (first_bbox, merged_text)
                    p1_boxes[last_idx] = (_last_bbox, "")

    async def _emit_page_callbacks(
        self,
        page_index: int,
        page_blocks: Sequence[tuple[BBox, str]],
        confidence_estimator: Callable[[str], float | None] | None = None,
    ) -> None:
        """Drive per-block and per-page observer callbacks for a single page."""
        cb = self.block_callbacks
        if cb.on_block is None and cb.on_page_complete is None:
            return

        for block_idx, (bbox, text) in enumerate(page_blocks):
            if cb.on_block is not None and text and text.strip():
                conf = (
                    confidence_estimator(text)
                    if confidence_estimator is not None
                    else None
                )
                await cb.on_block(
                    page_index,
                    block_idx,
                    list(bbox),
                    text,
                    "text",
                    conf,
                )
        if cb.on_page_complete is not None:
            await cb.on_page_complete(page_index)

    async def _run_spellcheck(
        self,
        pages_structured: PagesData,
        page_nums: Sequence[int],
        lang: str,
    ) -> None:
        """
        Post-processing step that runs spelling auto-correction on each page.
        """
        from omniscribe.core.postprocess import DictionaryPostProcessor

        processor = DictionaryPostProcessor(lang)
        await processor.ensure_loaded()
        for p in page_nums:
            corrected: PageBoxes = []
            for bbox, text in pages_structured[p]:
                if text:
                    corrected.append((bbox, processor.correct_text(text)))
                else:
                    corrected.append((bbox, text))
            pages_structured[p] = corrected

    async def _build_document_result(
        self,
        *,
        pages_data: PagesData,
        page_nums: Sequence[int],
        source_path: str,
        source_processor: str,
        spellcheck: SpellcheckMode,
        cross_page: bool,
        page_metadata_overlays: dict[int, dict[str, object]] | None = None,
        block_metadata_overlays: dict[int, list[dict[str, object]]] | None = None,
    ) -> DocumentResult:
        """Apply text-only post-processing and run document processors.

        Returns the resulting :class:`DocumentResult`. The caller is responsible
        for any engine-specific mutations (e.g. hybrid's quality-routing step)
        before handing the result to :meth:`_emit`.
        """
        from omniscribe.core.document import DocumentResult
        from omniscribe.core.processors import run_document_processors

        # Text-only passes first — they mutate ``pages_data`` in place.
        if cross_page:
            self._cross_page_merge(pages_data, page_nums)

        if spellcheck and spellcheck != "none":
            await self._run_spellcheck(pages_data, page_nums, spellcheck)

        document_result = DocumentResult.from_pages_data(
            pages_data, source_path=source_path, source_processor=source_processor
        )

        if page_metadata_overlays:
            for page in document_result.pages:
                metadata = page_metadata_overlays.get(page.page_index)
                if metadata:
                    page.metadata.update(metadata)

        if block_metadata_overlays:
            for page in document_result.pages:
                block_overlays = block_metadata_overlays.get(page.page_index)
                if block_overlays:
                    # `strict=True`: the engine guarantees the
                    # backend emits one overlay per block, so
                    # length mismatches are a real bug and should
                    # surface loudly rather than silently drop the
                    # tail of either sequence.
                    for block, meta in zip(page.blocks, block_overlays, strict=True):
                        block.metadata.update(meta)

        return await run_document_processors(document_result, self.document_processors)

    async def _emit(
        self,
        *,
        input_path: str,
        output_path: str,
        document_result: DocumentResult,
        dpi: int,
        progress: ProgressCallback | None,
    ) -> dict[int, list[str]]:
        """Write the final PDF and return the ``{page: [lines]}`` view.

        This is the single place where ``last_document_result`` is assigned and
        the output writer is invoked; both engines route through it so the
        end-of-pipeline contract lives in exactly one method.

        When the injected writer implements :class:`DocumentResultWriter` the
        full ``DocumentResult`` is passed through losslessly; legacy 4-arg
        callable writers receive the ``to_pages_data()`` conversion instead.
        """
        self.last_document_result = document_result
        pages_data = document_result.to_pages_data()
        page_nums = sorted(pages_data)

        pages_text: dict[int, list[str]] = {}
        for p in page_nums:
            pages_text[p] = [text for _, text in pages_data[p] if text.strip()]

        await notify(progress, "embed", 0, 1, "Writing output...")
        writer = self.output_writer
        if isinstance(writer, DocumentResultWriter):
            await asyncio.to_thread(
                writer.write_document_result,
                input_path,
                output_path,
                document_result,
                dpi,
            )
        else:
            await asyncio.to_thread(writer, input_path, output_path, pages_data, dpi)
        await notify(progress, "embed", 1, 1, "Done.")
        return pages_text
