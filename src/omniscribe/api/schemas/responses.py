from __future__ import annotations

from typing import Any

from pydantic import BaseModel, RootModel


class ProcessResponse(BaseModel):
    job_id: str
    status: str


class OCRStatusResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    duration_s: float | None = None
    error: str | None = None
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    text_artifact_url: str | None = None
    failed_pages: list[int] | None = None


class JobRecordResponse(BaseModel):
    id: str
    filename: str
    model: str
    pipeline_mode: str
    pages: str | None = None
    duration_s: float
    timestamp: str
    status: str
    failed_pages: list[int] | None = None


class JobListResponse(RootModel[list[JobRecordResponse]]):
    pass


class ClearJobsResponse(BaseModel):
    status: str


class ConfigResponse(BaseModel):
    api_base: str
    api_key: str
    model: str
    concurrency: int
    dpi: int
    dense_mode: str
    dense_threshold: int
    max_image_dim: int
    refine: bool
    verify_model: bool
    pipeline_mode: str
    self_correction: bool
    binarize: bool
    dual_engine: bool
    spellcheck: str
    cross_page: bool
    preprocess_pages: bool
    orientation_detection: bool
    deskew: bool
    denoise: bool
    normalize_contrast: bool
    crop_cleanup: bool
    quality_routing: bool
    document_processors: list[str]


class OCRConfigResponse(BaseModel):
    """OCR-namespace runtime configuration.

    Mirrors the legacy :class:`ConfigResponse` field set, plus the namespaced
    ``ocr_*`` backend triple and the masked ``ocr_auth_token`` slot used by
    the per-service auth endpoint.
    """

    ocr_api_base: str
    ocr_api_key: str
    ocr_model: str
    ocr_provider: str | None = None
    ocr_auth_token: str | None = None
    concurrency: int
    dpi: int
    dense_mode: str
    dense_threshold: int
    max_image_dim: int
    refine: bool
    verify_model: bool
    pipeline_mode: str
    self_correction: bool
    binarize: bool
    dual_engine: bool
    spellcheck: str
    cross_page: bool
    preprocess_pages: bool
    orientation_detection: bool
    deskew: bool
    denoise: bool
    normalize_contrast: bool
    crop_cleanup: bool
    quality_routing: bool
    document_processors: list[str] = []


class TranslationConfigResponse(BaseModel):
    """Translation/extraction-namespace runtime configuration.

    Mirrors the legacy :class:`ConfigResponse` field set, plus the namespaced
    ``translation_*`` backend triple, the masked ``translation_auth_token``
    slot, and the per-namespace translation knobs.
    """

    translation_api_base: str
    translation_api_key: str
    translation_model: str
    translation_provider: str | None = None
    translation_auth_token: str | None = None
    sliding_window_words: int = 80
    dual_translate: bool = False


class NamespacedModelsResponse(BaseModel):
    """Combined per-namespace model listing.

    ``models`` is the union of the OCR and translation lists (legacy
    callers). ``ocr`` and ``translation`` carry each namespace's own list.
    Either side may carry an ``error`` message if model discovery failed
    for that backend only — the other namespace's list is still returned.
    """

    models: list[str] = []
    ocr: list[str] = []
    translation: list[str] = []
    ocr_error: str | None = None
    translation_error: str | None = None


class ModelsResponse(BaseModel):
    """Single-namespace model listing.

    Carries the legacy flat shape used by ``GET /api/models/ocr`` and
    ``GET /api/models/translation`` as well as the legacy single
    ``GET /api/models`` endpoint.
    """

    models: list[str]
    error: str | None = None


class ExtractionResponse(BaseModel):
    extracted_data: Any


class TranslationResponse(BaseModel):
    translated_text: str


class AsyncTranslationResponse(BaseModel):
    job_id: str
    status: str


class TranslationJobStatusResponse(BaseModel):
    job_id: str
    state: str
    status: str | None = None
    info: Any | None = None
    result: Any | None = None
    error: str | None = None


class GlossaryResponse(BaseModel):
    entries: Any = None


class TreeTranslationResponse(BaseModel):
    status: str
    tree: dict[str, Any] | None = None
    page_count: int | None = None
    block_count: int | None = None
    translated_pages: dict[str, Any] | None = None


class NLLBTranslationResponse(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str


class TranscriptionConfigResponse(BaseModel):
    """Transcription-namespace runtime configuration."""

    transcription_api_base: str
    transcription_api_key: str
    transcription_model: str
    transcription_engine: str
    transcription_auth_token: str | None = None
    language: str | None = None
    prompt: str | None = None
    temperature: float = 0.0


class TranscriptionJobResponse(BaseModel):
    """Response returned upon transcription execution."""

    text: str
    language: str | None = None
    duration: float | None = None
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    metadata_artifact_id: str | None = None
    metadata_artifact_token: str | None = None
    job_id: str | None = None
    segments: list[dict[str, Any]] = []


class HealthResponse(BaseModel):
    """Liveness probe payload. Always ``{"status": "ok"}`` when the worker is alive."""

    status: str


class ReadinessArtifactCounts(BaseModel):
    """Per-store entry counts surfaced by the readiness probe."""

    text_entries: int
    metadata_entries: int
    export_entries: int


class ReadinessResponse(BaseModel):
    """Readiness probe payload.

    ``status`` is ``"ok"`` when every checked subsystem is healthy and
    ``"degraded"`` otherwise. ``reasons`` lists the failing subsystems
    so operators can inspect the JSON without reading logs.
    """

    status: str
    artifacts: ReadinessArtifactCounts
    ocr_job_queue_running: bool
    reasons: list[str] | None = None


__all__ = [
    "AsyncTranslationResponse",
    "ClearJobsResponse",
    "ConfigResponse",
    "ExtractionResponse",
    "GlossaryResponse",
    "HealthResponse",
    "JobListResponse",
    "JobRecordResponse",
    "ModelsResponse",
    "NLLBTranslationResponse",
    "NamespacedModelsResponse",
    "OCRConfigResponse",
    "OCRStatusResponse",
    "ProcessResponse",
    "ReadinessArtifactCounts",
    "ReadinessResponse",
    "TranscriptionConfigResponse",
    "TranscriptionJobResponse",
    "TranslationConfigResponse",
    "TranslationJobStatusResponse",
    "TranslationResponse",
    "TreeTranslationResponse",
]
