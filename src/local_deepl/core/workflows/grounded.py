from __future__ import annotations

from collections.abc import Iterable, Sequence

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


class GroundedEngine(EngineBase):
    def __init__(
        self,
        grounded_backend: GroundedOCRBackend,
        output_writer: OutputWriter,
        document_processors: Sequence[DocumentProcessor] | None = None,
    ) -> None:
        super().__init__(
            output_writer=output_writer,
            document_processors=document_processors,
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

        block_metadata_overlays = {}
        for block in response.blocks:
            page_overlays = block_metadata_overlays.setdefault(block.page_index, [])
            page_overlays.append({"label": block.label, "image_bytes": block.image_bytes})

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
