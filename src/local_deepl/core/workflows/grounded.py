from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from local_deepl.core.document import SpellcheckMode
from local_deepl.core.grounded import GroundedBlock, GroundedOCRBackend
from local_deepl.core.processors import DocumentProcessor
from local_deepl.core.workflows.base import (
    EngineBase,
    OutputWriter,
    PagesData,
    ProgressCallback,
    WarningCallback,
)

if TYPE_CHECKING:
    from local_deepl.core.callbacks import BlockCallbackSet


class GroundedEngine(EngineBase):
    def __init__(
        self,
        grounded_backend: GroundedOCRBackend,
        output_writer: OutputWriter,
        document_processors: Sequence[DocumentProcessor] | None = None,
        block_callbacks: BlockCallbackSet | None = None,
    ) -> None:
        # Phase B (review M2) — the grounded path also accepts the
        # callback set for symmetry with HybridEngine. The current
        # execute() doesn't yet emit per-block events (only the
        # generic `progress` callback); that parity work is a
        # follow-up. Wiring the parameter through now means
        # `OCRPipeline(grounded_backend=..., block_callbacks=...)`
        # doesn't have to grow a special case.
        super().__init__(
            output_writer=output_writer,
            document_processors=document_processors,
            block_callbacks=block_callbacks,
        )
        self.grounded_backend = grounded_backend

    async def execute(
        self,
        input_path: str,
        output_path: str,
        *,
        dpi: int,
        spellcheck: SpellcheckMode = SpellcheckMode.NONE,
        cross_page: bool = False,
        progress: ProgressCallback | None = None,
        on_warning: WarningCallback | None = None,
    ) -> dict[int, list[str]]:
        """
        Grounded path: the backend returns (bbox, text) pairs directly.
        No Surya, no DP, no refine — the model already knows where the text is.
        """
        self._reset_run_state()

        response = await self.grounded_backend.ocr_document(
            input_path, progress=progress, on_warning=on_warning
        )
        if response.failed_pages:
            self.last_failed_pages.extend(response.failed_pages)

        pages_data = self._accumulate_pages(response.blocks)
        page_nums = sorted(pages_data)

        # Phase E (review E.5) — `block_metadata_overlays` is the
        # shape `EngineBase._build_document_result` expects for its
        # `block_metadata_overlays` kwarg: a dict keyed by
        # `page_index`, each value a list of per-block overlay dicts
        # in the same order as the page's blocks. The grounded path
        # produces this directly from the backend response instead of
        # through the `_build_document_result` indirection; the
        # annotation here is the only place the overlay shape is
        # documented in the codebase.
        block_metadata_overlays: dict[int, list[dict[str, object]]] = {}
        for block in response.blocks:
            page_overlays = block_metadata_overlays.setdefault(block.page_index, [])
            page_overlays.append(
                {"label": block.label, "image_bytes": block.image_bytes}
            )

        document_result = await self._build_document_result(
            pages_data=pages_data,
            page_nums=page_nums,
            source_path=input_path,
            source_processor="grounded",
            spellcheck=spellcheck,
            cross_page=cross_page,
            page_metadata_overlays=None,
            block_metadata_overlays=block_metadata_overlays,
        )

        return await self._emit(
            input_path=input_path,
            output_path=output_path,
            document_result=document_result,
            dpi=dpi,
            progress=progress,
        )

    @staticmethod
    def _accumulate_pages(
        blocks: Iterable[GroundedBlock],
    ) -> PagesData:
        """Group backend blocks by page index, preserving backend ordering."""
        pages_data: PagesData = {}
        for block in blocks:
            pages_data.setdefault(block.page_index, []).append((block.bbox, block.text))
        return pages_data
