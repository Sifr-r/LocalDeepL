"""Pipeline construction for the OCR upload endpoint.

Extracted from ``api/routers/ocr.py`` because the pipeline factory grew to
~110 lines: it branches on ``pipeline_mode`` (hybrid vs grounded), wires
WebSocket-bound per-block callbacks, and decides whether to plug in the
TrOCR handwriting specialist. Putting it in a service keeps the router
route body focused on orchestration.

Three public surfaces:

- :func:`build_pipeline` — assembles the full :class:`OCRPipeline` for the
  current request, including the WebSocket-bound callback set.
- :func:`verify_backend_model` — pre-flight model-loaded check (issue
  #7 — see :class:`ModelNotLoadedError` for the rationale).
- :func:`build_block_callbacks` — exposed separately so test code can
  construct a callback set without spinning up a full pipeline.
"""

from __future__ import annotations

from typing import Any

from omniscribe import (
    HybridAligner,
    OCRPipeline,
    OCRProcessor,
    PDFHandler,
    PromptedGroundedOCR,
    build_document_processors,
)
from omniscribe.api.schemas import ProcessSettings
from omniscribe.core.callbacks import BlockCallbackSet
from omniscribe.core.ocr.resilience import get_default_circuit_breaker_registry
from omniscribe.core.ocr_quality import build_trust_orchestrator
from omniscribe.core.preprocessing import (
    PagePreprocessingOptions,
    PagePreprocessor,
)

# Cloud-hosted model name prefixes — model verification (LM Studio's
# ``GET /v1/models`` semantics) doesn't apply to these, so we skip it.
_CLOUD_MODEL_PREFIXES = (
    "openai/",
    "anthropic/",
    "gemini/",
    "deepseek/",
    "groq/",
    "vertex_ai/",
)


def build_pipeline(
    settings: ProcessSettings,
    progress_target: str | None = None,
    *,
    manager_send_block: Any,
    manager_send_page_complete: Any,
) -> tuple[OCRPipeline, Any]:
    """Build the OCR pipeline for a request.

    ``progress_target`` is the WebSocket channel_id this request is
    bound to (or None if the caller did not open a progress channel).
    The returned pipeline has its per-block / per-page observer hooks
    wired to the WebSocket manager, so per-block events emitted by the
    engine reach the live UI without the engine ever importing
    ``omniscribe.api``.

    Phase 2 — the trust orchestrator is built from
    ``settings.quality_options`` (which itself accepts a JSON payload
    on the form, see :class:`ProcessSettings`). When ``quality_options``
    is ``None`` or every sub-module is off, the orchestrator is
    ``None`` and the engine keeps the pre-Phase-2 byte layout.
    """
    processors = build_document_processors(
        processor.value for processor in settings.document_processors
    )
    block_callbacks = build_block_callbacks(
        progress_target=progress_target,
        manager_send_block=manager_send_block,
        manager_send_page_complete=manager_send_page_complete,
    )
    trust_orchestrator = _build_trust_orchestrator(settings.quality_options)

    if settings.pipeline_mode == "grounded":
        backend = PromptedGroundedOCR(
            api_base=settings.api_base,
            api_key=settings.api_key,
            model=settings.model,
            max_image_dim=settings.max_image_dim,
            concurrency=settings.concurrency,
        )
        pipeline = OCRPipeline(
            pdf_handler=PDFHandler(),
            grounded_backend=backend,
            document_processors=processors,
            block_callbacks=block_callbacks,
            trust_orchestrator=trust_orchestrator,
        )
    else:
        from omniscribe.core.trocr_engine import TrOCREngine

        preprocessing_options = PagePreprocessingOptions(
            enabled=settings.preprocess_pages,
            orientation_detection=settings.orientation_detection,
            deskew=settings.deskew,
            denoise=settings.denoise,
            normalize_contrast=settings.normalize_contrast,
            crop_cleanup=settings.crop_cleanup,
        )
        page_preprocessor: PagePreprocessor | None = _build_page_preprocessor(
            settings, preprocessing_options
        )

        backend = OCRProcessor(
            api_base=settings.api_base,
            api_key=settings.api_key,
            model=settings.model,
            handwriting_mode=settings.handwriting_hint,
            trocr_engine=TrOCREngine() if settings.handwriting_hint else None,
            circuit_breaker_registry=get_default_circuit_breaker_registry(),
        )
        pipeline = OCRPipeline(
            aligner=HybridAligner(),
            ocr_processor=backend,
            pdf_handler=PDFHandler(),
            document_processors=processors,
            page_preprocessor=page_preprocessor,
            block_callbacks=block_callbacks,
            trust_orchestrator=trust_orchestrator,
        )
    return pipeline, backend


def _build_trust_orchestrator(quality_options: Any) -> Any:
    """Factory wrapper exposed as a module-private hook for tests.

    The real construction logic lives in
    :func:`omniscribe.core.ocr_quality.build_trust_orchestrator`;
    we re-export it here so tests can monkeypatch the factory's
    namespace (``test_api_quality_options.py``) without dipping into
    the trust-layer package itself.
    """
    return build_trust_orchestrator(quality_options)


def _build_page_preprocessor(
    settings: ProcessSettings,
    preprocessing_options: PagePreprocessingOptions,
) -> PagePreprocessor | None:
    """Pick the page preprocessor for this request, if any.

    ``handwriting_hint`` swaps the local preprocessor for a specialized
    handwriting preprocessor (or composites both). When the user
    requests neither, we don't pay the cost of instantiating either.
    """
    if settings.handwriting_hint:
        from omniscribe.core.preprocessing import (
            CompositePagePreprocessor,
            HandwritingPagePreprocessor,
            LocalPagePreprocessor,
        )

        if preprocessing_options.enabled:
            return CompositePagePreprocessor(
                [HandwritingPagePreprocessor(), LocalPagePreprocessor()]
            )
        return HandwritingPagePreprocessor()
    if preprocessing_options.enabled:
        from omniscribe.core.preprocessing import LocalPagePreprocessor

        return LocalPagePreprocessor()
    return None


def build_block_callbacks(
    *,
    progress_target: str | None,
    manager_send_block: Any,
    manager_send_page_complete: Any,
) -> BlockCallbackSet:
    """Construct the engine-side callbacks bridged to the WebSocket manager.

    Both inner closures are no-ops when no progress channel is bound
    (i.e. an API caller that did not open a WS gets the pure engine
    output, no per-block traffic).
    """

    async def _on_block(
        page_idx: int,
        block_idx: int,
        bbox: list[float],
        text: str,
        kind: str,
        confidence: float | None,
    ) -> None:
        if progress_target is None:
            return
        await manager_send_block(
            progress_target,
            page_idx=page_idx,
            block_idx=block_idx,
            bbox=bbox,
            text=text,
            kind=kind,
            confidence=confidence,
        )

    async def _on_page_complete(page_idx: int) -> None:
        if progress_target is None:
            return
        await manager_send_page_complete(progress_target, page_idx=page_idx)

    return BlockCallbackSet(
        on_block=_on_block,
        on_page_complete=_on_page_complete,
    )


async def verify_backend_model(
    backend: Any,
    model: str,
    *,
    verify_model: bool,
) -> None:
    """Pre-flight model-loaded check.

    Calls ``backend.ensure_model_loaded()`` when verification is enabled.
    Cloud-hosted models (OpenAI, Anthropic, Gemini, DeepSeek, Groq,
    Vertex AI) skip this check — they don't expose ``GET /v1/models``
    in the LM Studio shape. Verification is also auto-disabled when the
    api-base points to ``api.openai.com``.
    """
    is_cloud = (
        any(model.startswith(prefix) for prefix in _CLOUD_MODEL_PREFIXES)
        or "api.openai.com" in backend.api_base
    )
    if is_cloud:
        verify_model = False

    if verify_model:
        await backend.ensure_model_loaded()


__all__ = [
    "build_block_callbacks",
    "build_pipeline",
    "verify_backend_model",
]
