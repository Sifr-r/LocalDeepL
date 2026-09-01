"""Unit tests for documents plugin request schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from omniscribe.plugins.documents.schemas import (
    DocumentExportFormat,
    DocumentExportRequest,
    ExportBlockTreeRequest,
    ExportDocxRequest,
    ExportHtmlRequest,
    ExtractionRequest,
    ExtractionTemplate,
)

ARTIFACT_ID = "a" * 32
ARTIFACT_TOKEN = "b" * 43


def test_extraction_template_enum_values() -> None:
    assert {member.value for member in ExtractionTemplate} == {
        "invoice",
        "resume",
        "academic",
        "table",
        "table_extraction",
        "custom",
    }


def test_document_export_format_enum_values() -> None:
    assert {member.value for member in DocumentExportFormat} == {
        "json",
        "markdown",
        "text",
        "docling",
        "mineru",
    }


def test_extraction_request_defaults() -> None:
    body = ExtractionRequest()
    assert body.text == ""
    assert body.template is ExtractionTemplate.INVOICE
    assert body.custom_prompt == ""
    assert body.api_base is None
    assert body.api_key is None
    assert body.model is None


def test_extraction_request_rejects_unknown_template() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(text="x", template="nonsense")  # type: ignore[arg-type]


def test_extraction_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(text="x", bogus="1")  # type: ignore[call-arg]


def test_custom_prompt_max_length() -> None:
    assert ExtractionRequest(template="custom", custom_prompt="x" * 4000).custom_prompt  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ExtractionRequest(template="custom", custom_prompt="x" * 4001)  # type: ignore[arg-type]


def test_strings_are_trimmed() -> None:
    body = ExtractionRequest(text="  hello  ", api_base="  http://x  ")
    assert body.text == "hello"
    assert body.api_base == "http://x"


def test_artifact_id_must_be_32_chars() -> None:
    with pytest.raises(ValidationError):
        ExportHtmlRequest(text_artifact_id="short", text_artifact_token=ARTIFACT_TOKEN)
    request = ExportHtmlRequest(
        text_artifact_id=ARTIFACT_ID, text_artifact_token=ARTIFACT_TOKEN
    )
    assert request.text_artifact_id == ARTIFACT_ID


def test_artifact_token_bounds() -> None:
    with pytest.raises(ValidationError):
        ExportHtmlRequest(text_artifact_id=ARTIFACT_ID, text_artifact_token="t" * 31)
    with pytest.raises(ValidationError):
        ExportHtmlRequest(text_artifact_id=ARTIFACT_ID, text_artifact_token="t" * 257)


def test_document_export_request_defaults_to_json() -> None:
    body = DocumentExportRequest(
        text_artifact_id=ARTIFACT_ID, text_artifact_token=ARTIFACT_TOKEN
    )
    assert body.export_format is DocumentExportFormat.JSON


def test_blocktree_metadata_fields_optional() -> None:
    body = ExportBlockTreeRequest(
        text_artifact_id=ARTIFACT_ID, text_artifact_token=ARTIFACT_TOKEN
    )
    assert body.metadata_artifact_id is None
    assert body.metadata_artifact_token is None


def test_export_docx_request_text_default() -> None:
    assert ExportDocxRequest().text == ""
