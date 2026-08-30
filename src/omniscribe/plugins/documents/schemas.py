"""Request schemas for the documents plugin (extraction + export routes).

Field constraints reproduce the pre-harness contract (commit ``44ef123^``,
``api/schemas/requests.py``) so the existing Flutter client keeps working
without changes.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractionTemplate(StrEnum):
    INVOICE = "invoice"
    RESUME = "resume"
    ACADEMIC = "academic"
    TABLE = "table"
    TABLE_EXTRACTION = "table_extraction"
    CUSTOM = "custom"


class DocumentExportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
    DOCLING = "docling"
    MINERU = "mineru"


class _TrimmedModel(BaseModel):
    """Shared config: reject unknown fields, trim string values."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ExtractionRequest(_TrimmedModel):
    text: str = ""
    template: ExtractionTemplate = ExtractionTemplate.INVOICE
    custom_prompt: str = Field(default="", max_length=4000)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None


class ExportHtmlRequest(_TrimmedModel):
    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)


class ExportBlockTreeRequest(ExportHtmlRequest):
    metadata_artifact_id: str | None = Field(default=None, min_length=32, max_length=32)
    metadata_artifact_token: str | None = Field(
        default=None, min_length=32, max_length=256
    )


class DocumentExportRequest(ExportBlockTreeRequest):
    export_format: DocumentExportFormat = DocumentExportFormat.JSON


class ExportDocxRequest(_TrimmedModel):
    text: str = ""
