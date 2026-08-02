"""
OCRPipeline - Web entry point and in-process programmatic orchestration.

The user-facing `omniscribe` CLI script has been deprecated; the supported
product workflow is the FastAPI Web UI and API (see `omniscribe.server`).
`OCRPipeline` remains importable for in-process programmatic use, e.g.
embedding OCR in another application or a custom worker.

Internally, `OCRPipeline` is a thin facade that delegates execution to either
`GroundedEngine` or `HybridEngine` (in `omniscribe.core.workflows`) based on
the configured components.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from omniscribe.core.document import DenseMode, SpellcheckMode
from omniscribe.core.grounded import GroundedOCRBackend
from omniscribe.core.preprocessing import PagePreprocessingOptions, PagePreprocessor
from omniscribe.core.processors import DocumentProcessor
from omniscribe.core.routing import QualityRoutingOptions
from omniscribe.core.workflows import (
    AnyOutputWriter,
    DocumentResultWriter,
    EngineBase,
    GroundedEngine,
    HybridEngine,
    ProgressCallback,
    WarningCallback,
)

if TYPE_CHECKING:
    from omniscribe.core.callbacks import BlockCallbackSet


class OCRPipeline:
    def __init__(
        self,
        aligner=None,
        ocr_processor=None,
        pdf_handler=None,
        output_writer: AnyOutputWriter | None = None,
        grounded_backend: GroundedOCRBackend | None = None,
        document_processors: Sequence[DocumentProcessor] | None = None,
        page_preprocessor: PagePreprocessor | None = None,
        block_callbacks: BlockCallbackSet | None = None,
    ):
        self.grounded_backend = grounded_backend
        if pdf_handler is None:
            raise ValueError("pdf_handler is required (used for output writing)")
        # Prefer the handler object itself when it implements the rich
        # DocumentResultWriter protocol (receives the full DocumentResult
        # without the lossy legacy conversion). Explicitly injected writers
        # always win, whether legacy callables or rich writers.
        if output_writer is None:
            if isinstance(pdf_handler, DocumentResultWriter):
                output_writer = pdf_handler
            else:
                output_writer = pdf_handler.embed_structured_text

        # Phase B (review M2) — `block_callbacks` is forwarded to the
        # engine so the WebSocket-free per-block observer path reaches
        # the inner `_ocr_pages` method. Default `None` keeps every
        # existing call site (tests, in-process programmatic use)
        # working unchanged.
        self._engine: EngineBase
        if self.grounded_backend is not None:
            self._engine = GroundedEngine(
                grounded_backend=self.grounded_backend,
                output_writer=output_writer,
                document_processors=document_processors,
                block_callbacks=block_callbacks,
            )
        else:
            if aligner is None or ocr_processor is None:
                raise ValueError(
                    "Hybrid pipeline requires both `aligner` and `ocr_processor`. "
                    "Pass a `grounded_backend=...` instead to use the grounded path."
                )
            self._engine = HybridEngine(
                aligner=aligner,
                ocr_processor=ocr_processor,
                pdf_handler=pdf_handler,
                output_writer=output_writer,
                document_processors=document_processors,
                page_preprocessor=page_preprocessor,
                block_callbacks=block_callbacks,
            )

    @property
    def last_document_result(self):
        return self._engine.last_document_result

    @property
    def last_failed_pages(self):
        return self._engine.last_failed_pages

    async def run(
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
        if self.grounded_backend is not None:
            grounded_engine = cast(GroundedEngine, self._engine)
            return await grounded_engine.execute(
                input_path=input_path,
                output_path=output_path,
                dpi=dpi,
                spellcheck=spellcheck,
                cross_page=cross_page,
                progress=progress,
                on_warning=on_warning,
            )
        else:
            try:
                normalized_dense_mode = DenseMode(dense_mode)
            except ValueError as exc:
                raise ValueError(
                    f"dense_mode must be a DenseMode or valid value; got {dense_mode!r}"
                ) from exc
            hybrid_engine = cast(HybridEngine, self._engine)
            return await hybrid_engine.execute(
                input_path=input_path,
                output_path=output_path,
                dpi=dpi,
                pages=pages,
                concurrency=concurrency,
                refine=refine,
                max_image_dim=max_image_dim,
                dense_threshold=dense_threshold,
                dense_mode=normalized_dense_mode,
                self_correction=self_correction,
                binarize=binarize,
                dual_engine=dual_engine,
                spellcheck=spellcheck,
                cross_page=cross_page,
                preprocessing_options=preprocessing_options,
                quality_routing_options=quality_routing_options,
                progress=progress,
                on_warning=on_warning,
            )
