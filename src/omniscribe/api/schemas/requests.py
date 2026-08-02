from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from omniscribe.core.document import DenseMode, PipelineMode, SpellcheckMode


class DocumentProcessorName(StrEnum):
    READING_ORDER = "reading_order"
    QUALITY_ANALYSIS = "quality_analysis"
    STRUCTURE_ANALYSIS = "structure_analysis"
    SECTION_ANALYSIS = "section_analysis"
    LAYOUT_ENRICHMENT = "layout_enrichment"
    TABLE_EXTRACTION = "table_extraction"


class ExtractionTemplate(StrEnum):
    INVOICE = "invoice"
    RESUME = "resume"
    ACADEMIC = "academic"
    CUSTOM = "custom"


class DocumentExportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
    DOCLING = "docling"
    MINERU = "mineru"


_PAGE_RANGE_RE = re.compile(
    r"^\s*\d+\s*(?:-\s*\d+\s*)?(?:,\s*\d+\s*(?:-\s*\d+\s*)?)*\s*$"
)


def _reject_bool_for_int(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("must be an integer")
    return value


def _reject_string_for_config_number(value: Any) -> Any:
    if isinstance(value, str):
        raise ValueError("must be a JSON number")
    return _reject_bool_for_int(value)


def _reject_string_for_config_bool(value: Any) -> Any:
    if not isinstance(value, bool):
        raise ValueError("must be a JSON boolean")
    return value


def _non_empty_string(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a non-empty string")
    return value.strip()


def _validate_optional_string(value: Any) -> Any:
    if value is None:
        return value
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value.strip()


def _parse_document_processors(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    concurrency: int | None = Field(default=None, ge=1, le=64)
    dpi: int | None = Field(default=None, ge=10, le=600)
    dense_mode: DenseMode | None = None
    dense_threshold: int | None = Field(default=None, ge=0, le=10_000)
    max_image_dim: int | None = Field(default=None, ge=100, le=4096)
    refine: bool | None = None
    verify_model: bool | None = None
    pipeline_mode: PipelineMode | None = None
    self_correction: bool | None = None
    binarize: bool | None = None
    dual_engine: bool | None = None
    spellcheck: SpellcheckMode | None = None
    cross_page: bool | None = None
    preprocess_pages: bool | None = None
    orientation_detection: bool | None = None
    deskew: bool | None = None
    denoise: bool | None = None
    normalize_contrast: bool | None = None
    crop_cleanup: bool | None = None
    quality_routing: bool | None = None
    handwriting_hint: bool | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    document_processors: list[DocumentProcessorName] | None = None

    @field_validator("api_base", "api_key", "model", mode="before")
    @classmethod
    def validate_strings(cls, value: Any) -> Any:
        if value is None:
            return value
        return _non_empty_string(value)

    @field_validator(
        "concurrency",
        "dpi",
        "dense_threshold",
        "max_image_dim",
        mode="before",
    )
    @classmethod
    def validate_config_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _reject_string_for_config_number(value)

    @field_validator(
        "refine",
        "verify_model",
        "self_correction",
        "binarize",
        "dual_engine",
        "cross_page",
        "preprocess_pages",
        "orientation_detection",
        "deskew",
        "denoise",
        "normalize_contrast",
        "crop_cleanup",
        "quality_routing",
        mode="before",
    )
    @classmethod
    def validate_config_booleans(cls, value: Any) -> Any:
        if value is None:
            return value
        return _reject_string_for_config_bool(value)

    @field_validator("document_processors", mode="before")
    @classmethod
    def validate_document_processors(cls, value: Any) -> Any:
        return _parse_document_processors(value)


class ProcessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_base: str
    api_key: str
    model: str
    pipeline_mode: PipelineMode
    dpi: int = Field(ge=10, le=600)
    concurrency: int = Field(ge=1, le=64)
    dense_mode: DenseMode
    dense_threshold: int = Field(ge=0, le=10_000)
    pages: str | None = None
    refine: bool
    max_image_dim: int = Field(ge=100, le=4096)
    self_correction: bool
    binarize: bool
    dual_engine: bool
    spellcheck: SpellcheckMode
    cross_page: bool
    preprocess_pages: bool
    orientation_detection: bool
    deskew: bool
    denoise: bool
    normalize_contrast: bool
    crop_cleanup: bool
    quality_routing: bool
    handwriting_hint: bool = False
    confidence_threshold: float = 0.75
    document_processors: list[DocumentProcessorName] = Field(default_factory=list)
    chunk_pages: int | None = Field(default=None, ge=1, le=500)

    @field_validator("api_base", "api_key", "model", mode="before")
    @classmethod
    def validate_strings(cls, value: Any) -> Any:
        return _non_empty_string(value)

    @field_validator(
        "dpi", "concurrency", "dense_threshold", "max_image_dim", mode="before"
    )
    @classmethod
    def validate_form_numbers(cls, value: Any) -> Any:
        return _reject_bool_for_int(value)

    @field_validator("pages", mode="before")
    @classmethod
    def validate_pages(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not _PAGE_RANGE_RE.match(value):
            raise ValueError("must be a comma-separated page range such as 1-3,5")
        return value.strip()

    @field_validator("document_processors", mode="before")
    @classmethod
    def validate_document_processors(cls, value: Any) -> Any:
        return _parse_document_processors(value)


class TranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    target_language: str = Field(default="Spanish", min_length=1, max_length=80)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    glossary: list[dict[str, object]] | None = None
    glossary_text: str | None = None
    sliding_window_words: int = Field(default=80, ge=0, le=2000)
    dual_translate: bool = False
    second_api_base: str | None = None
    second_api_key: str | None = None
    second_model: str | None = None

    @field_validator(
        "text", "target_language", "api_base", "api_key", "model", mode="before"
    )
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[dict[str, object]] | None = None
    text: str | None = None

    @field_validator("text", mode="before")
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class TreeTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)
    target_language: str = Field(default="English", min_length=1, max_length=80)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    glossary: list[dict[str, object]] | None = None
    dual_translate: bool = False
    channel_id: str | None = None

    @field_validator("target_language", "api_base", "api_key", "model", mode="before")
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class ExportHtmlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)

    @field_validator("text_artifact_id", "text_artifact_token", mode="before")
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class ExportBlockTreeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)
    metadata_artifact_id: str | None = Field(default=None, min_length=32, max_length=32)
    metadata_artifact_token: str | None = Field(
        default=None, min_length=32, max_length=256
    )


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    template: ExtractionTemplate = ExtractionTemplate.INVOICE
    custom_prompt: str = Field(default="", max_length=4000)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None

    @field_validator(
        "text", "custom_prompt", "api_base", "api_key", "model", mode="before"
    )
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class ExportDocxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""

    @field_validator("text", mode="before")
    @classmethod
    def validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class DocumentExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)
    export_format: DocumentExportFormat = DocumentExportFormat.JSON
    metadata_artifact_id: str | None = Field(default=None, min_length=32, max_length=32)
    metadata_artifact_token: str | None = Field(
        default=None, min_length=32, max_length=256
    )


class GlossaryFormat(StrEnum):
    CSV = "csv"
    TSV = "tsv"
    XLIFF = "xliff"
    TBX = "tbx"
    TMX = "tmx"
    GIT_GLOSSARY = "git_glossary"
    SQL_TABLE = "sql_table"
    JSON_PAIRS = "json_pairs"


class GlossaryImportSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: GlossaryFormat
    text: str | None = None
    inline_bytes_b64: str | None = None
    url: str | None = None
    git_url: str | None = None
    git_ref: str | None = "HEAD"
    git_path: str | None = "GLOSSARY.md"
    git_credentials: str | None = None
    sql_dsn: str | None = None
    sql_source_table: str | None = None
    sql_target_table: str | None = None
    sql_source_col: str | None = "source"
    sql_target_col: str | None = "target"
    sql_where: str | None = None
    encoding: str | None = None
    max_entries: int | None = Field(default=None, ge=1, le=1_000_000)
    name: str | None = Field(default=None, max_length=200)

    @field_validator("name", "encoding", "git_ref", "git_path", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: GlossaryImportSource
    channel_id: str | None = None
    session_token: str | None = None

    @field_validator("channel_id", "session_token", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Any:
        return _validate_optional_string(value)


class GlossaryListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    format: GlossaryFormat
    source_uri: str | None = None
    encoding: str | None = None
    entry_count: int = Field(ge=0)
    enabled: bool = True
    priority: int = 0
    group: str = "default"


class GlossaryToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class GlossaryReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_ids: list[str] = Field(min_length=0, max_length=200)


class GlossaryPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    enabled_glossaries: list[str] = Field(default_factory=list)


class GlossaryImportJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glossary_id: str | None = None
    job_id: str | None = None
    format: GlossaryFormat
    name: str
    entry_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    queued: bool = False


# ---------------------------------------------------------------------------
# Per-namespace runtime config (OAuth-style split)
# ---------------------------------------------------------------------------


_OCR_CONFIG_KEYS: tuple[str, ...] = (
    "ocr_api_base",
    "ocr_api_key",
    "ocr_model",
    "ocr_provider",
)
_TRANSLATION_CONFIG_KEYS: tuple[str, ...] = (
    "translation_api_base",
    "translation_api_key",
    "translation_model",
    "translation_provider",
    "sliding_window_words",
    "dual_translate",
)


class OcrConfigUpdate(BaseModel):
    """Per-namespace OCR runtime config.

    Mirrors the legacy ``ConfigUpdate`` shape but only accepts the
    ``ocr_*`` keys so the contract is "what you POST is what you
    GET" — unrelated keys cannot accidentally mutate the translation
    or shared config.
    """

    model_config = ConfigDict(extra="forbid")

    ocr_api_base: str | None = Field(default=None, min_length=1, max_length=512)
    ocr_api_key: str | None = Field(default=None, max_length=512)
    ocr_model: str | None = Field(default=None, min_length=1, max_length=256)
    ocr_provider: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator(
        "ocr_api_base", "ocr_api_key", "ocr_model", "ocr_provider", mode="before"
    )
    @classmethod
    def _validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)

    @property
    def stored_keys(self) -> tuple[str, ...]:
        return _OCR_CONFIG_KEYS


class TranslationConfigUpdate(BaseModel):
    """Per-namespace translation runtime config."""

    model_config = ConfigDict(extra="forbid")

    translation_api_base: str | None = Field(default=None, min_length=1, max_length=512)
    translation_api_key: str | None = Field(default=None, max_length=512)
    translation_model: str | None = Field(default=None, min_length=1, max_length=256)
    translation_provider: str | None = Field(default=None, min_length=1, max_length=64)
    sliding_window_words: int | None = Field(default=None, ge=0, le=2000)
    dual_translate: bool | None = None

    @field_validator(
        "translation_api_base",
        "translation_api_key",
        "translation_model",
        "translation_provider",
        mode="before",
    )
    @classmethod
    def _validate_optional_strings(cls, value: Any) -> Any:
        return _validate_optional_string(value)

    @field_validator("sliding_window_words", mode="before")
    @classmethod
    def _validate_window(cls, value: Any) -> Any:
        if value is None:
            return value
        return _reject_string_for_config_number(value)

    @field_validator("dual_translate", mode="before")
    @classmethod
    def _validate_dual(cls, value: Any) -> Any:
        if value is None:
            return value
        return _reject_string_for_config_bool(value)

    @property
    def stored_keys(self) -> tuple[str, ...]:
        return _TRANSLATION_CONFIG_KEYS


def _validate_auth_token_value(value: str | None) -> str | None:
    """Pydantic validator for ``AuthTokenUpdate``.

    Returns the trimmed token (or None for ``None``). Raises
    ``ValueError`` (mapped to 422 by FastAPI) for placeholder values
    or tokens shorter than :data:`MIN_AUTH_TOKEN_LENGTH`. The full
    placeholder denylist also lives in
    :mod:`omniscribe.api.services.security_config`; this validator
    mirrors the production rule so the same error envelope is shown
    whether the token came from the env or from a runtime POST.
    """
    from omniscribe.api.services.security_config import (
        MIN_AUTH_TOKEN_LENGTH,
        PLACEHOLDER_AUTH_TOKENS,
    )

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) < MIN_AUTH_TOKEN_LENGTH:
        raise ValueError(
            f"auth_token must be at least {MIN_AUTH_TOKEN_LENGTH} characters"
        )
    if stripped.lower() in PLACEHOLDER_AUTH_TOKENS:
        raise ValueError(
            "auth_token is a well-known placeholder; use a real, high-entropy secret."
        )
    return stripped


class AuthTokenUpdate(BaseModel):
    """Request body for ``POST /api/config/{ocr,translation}/auth``.

    A ``None`` value clears the namespace token. The server refuses
    placeholder / short values with a 422 envelope; the runtime
    denylist is identical to the boot-time
    ``SecuritySettings.from_env`` check.
    """

    model_config = ConfigDict(extra="forbid")

    auth_token: str | None = None

    @field_validator("auth_token", mode="before")
    @classmethod
    def _validate(cls, value: Any) -> Any:
        return _validate_auth_token_value(value)
