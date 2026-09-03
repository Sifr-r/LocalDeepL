"""OCR request/response schemas.

``OCRRequest`` parses the exact FormData field set the frontend's
``buildOcrFormData`` sends. Response models mirror the frontend types:
``AsyncSubmitResponse`` ↔ ``processOcrAsync`` return shape and
``JobStatusResponse`` ↔ ``OcrJobStatusResponse``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from omniscribe.utils.env import parse_bool

PipelineMode = Literal["hybrid", "grounded"]

#: Frontend dense toggles ("on"/"off") plus the core enum spellings.
_DENSE_MODE_ALIASES = {
    "on": "always",
    "off": "never",
    "auto": "auto",
    "always": "always",
    "never": "never",
}

_VALID_PROCESSORS = {
    "reading_order",
    "quality_analysis",
    "structure_analysis",
    "section_analysis",
    "layout_enrichment",
    "table_extraction",
}


def _parse_bool(value: Any, default: bool = False) -> Any:
    return parse_bool(value, default=default)


class OCRRequest(BaseModel):
    """One OCR upload's options, parsed from multipart form fields."""

    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    pipeline_mode: PipelineMode = "hybrid"
    dense_mode: str = "auto"
    spellcheck: str | None = None
    document_processors: list[str] = Field(default_factory=list)
    pages: str | None = None
    preprocess_pages: bool | None = None
    orientation_detection: bool = False
    deskew: bool = False
    denoise: bool = False
    normalize_contrast: bool = False
    crop_cleanup: bool = False
    progress_channel: str | None = None
    progress_token: str | None = None
    quality_loop_enabled: bool | None = None
    quality_target: float = Field(default=0.85, ge=0.5, le=1.0)
    quality_max_retries: int = Field(default=2, ge=0, le=5)

    @field_validator("document_processors", mode="before")
    @classmethod
    def _split_processors(cls, value: object) -> object:
        if isinstance(value, str):
            names = [item.strip() for item in value.split(",") if item.strip()]
            unknown = sorted(set(names) - _VALID_PROCESSORS)
            if unknown:
                raise ValueError(f"unknown document processor(s): {', '.join(unknown)}")
            return names
        return value

    @field_validator(
        "preprocess_pages",
        "orientation_detection",
        "deskew",
        "denoise",
        "normalize_contrast",
        "crop_cleanup",
        "quality_loop_enabled",
        mode="before",
    )
    @classmethod
    def _coerce_bool(cls, value: object) -> object:
        if isinstance(value, str):
            return _parse_bool(value)
        return value

    @property
    def dense_mode_normalized(self) -> str:
        """Map the frontend toggle onto the core DenseMode spellings."""
        return _DENSE_MODE_ALIASES.get(str(self.dense_mode).strip().lower(), "auto")

    @property
    def preprocessing_enabled(self) -> bool:
        """Master flag wins; otherwise any per-page toggle implies enabled."""
        if self.preprocess_pages is not None:
            return self.preprocess_pages
        return any(
            (
                self.orientation_detection,
                self.deskew,
                self.denoise,
                self.normalize_contrast,
                self.crop_cleanup,
            )
        )


class AsyncSubmitResponse(BaseModel):
    """Shape the frontend's ``processOcrAsync`` expects."""

    job_id: str
    status: Literal["pending", "processing", "complete", "error", "cancelled"] = "pending"
    status_url: str


class JobStatusResponse(BaseModel):
    """Mirrors the frontend ``OcrJobStatusResponse`` contract.

    Security note (2026-08-29 audit C-3 / H-3): the result ``token`` is
    intentionally **not** in this response. The unauthenticated
    ``GET /api/process/status/{job_id}`` + ``GET /api/jobs`` chain would
    otherwise let any caller fetch another user's OCR'd PDF without the
    constant-time gate at ``fetch_result``. The async client obtains the
    token from the ``job_completed`` SSE event payload (the out-of-band
    channel, parallel to the sync path's ``X-Text-Artifact-Token``
    response header). Only ``text_artifact_id`` is safe to expose — it's
    the opaque handle, not the secret.
    """

    job_id: str
    filename: str = ""
    status: Literal["pending", "processing", "complete", "error", "cancelled"]
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    duration_s: float | None = None
    error: str | None = None
    text_artifact_id: str | None = None
    failed_pages: list[int] = Field(default_factory=list)


class JobListItemResponse(BaseModel):
    """Mirrors the frontend ``JobRecordResponse`` contract."""

    id: str
    filename: str = ""
    model: str = ""
    pipeline_mode: str = ""
    pages: str | None = None
    duration_s: float = 0.0
    timestamp: str = ""
    status: str
    failed_pages: list[int] = Field(default_factory=list)


class PreflightRequest(BaseModel):
    """Audit 6.3: optional overrides for the model pre-flight route.

    All fields default to the current ``/api/config`` value, so a bare
    ``GET /api/process/preflight`` preflights the active LLM endpoint.
    Pass overrides (e.g. for a multi-tenant install where the operator
    wants to probe a candidate model before swapping the live one).
    """

    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None


class PreflightResponse(BaseModel):
    """Result of :meth:`OCRService.preflight_check`.

    ``loaded`` is the single source of truth for the UI badge; the
    ``requested_model`` / ``loaded_models`` pair lets the operator see
    exactly which models are present on the server.
    """

    loaded: bool
    requested_model: str
    api_base: str
    loaded_models: list[str] = Field(default_factory=list)
    detail: str = ""


__all__ = [
    "AsyncSubmitResponse",
    "JobListItemResponse",
    "JobStatusResponse",
    "OCRRequest",
    "PipelineMode",
    "PreflightRequest",
    "PreflightResponse",
]
