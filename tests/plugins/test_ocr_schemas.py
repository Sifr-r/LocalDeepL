"""OCR schemas: frontend FormData parsing and response shapes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from omniscribe.plugins.ocr.schemas import (
    AsyncSubmitResponse,
    JobListItemResponse,
    JobStatusResponse,
    OCRRequest,
)


def _frontend_form_fields() -> dict[str, str]:
    """The exact field set ``buildOcrFormData`` submits (all strings)."""
    return {
        "model": "allenai/olmocr-2-7b",
        "api_base": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "pipeline_mode": "hybrid",
        "dense_mode": "on",
        "spellcheck": "en-US",
        "document_processors": "reading_order,table_extraction",
        "preprocess_pages": "true",
        "orientation_detection": "true",
        "deskew": "false",
        "denoise": "true",
        "normalize_contrast": "false",
        "crop_cleanup": "false",
        "progress_channel": "chan-1",
        "progress_token": "tok-1",
    }


def test_parses_frontend_form_data_field_set() -> None:
    request = OCRRequest(**_frontend_form_fields())
    assert request.model == "allenai/olmocr-2-7b"
    assert request.pipeline_mode == "hybrid"
    assert request.document_processors == ["reading_order", "table_extraction"]
    assert request.preprocess_pages is True
    assert request.orientation_detection is True
    assert request.deskew is False
    assert request.denoise is True
    assert request.progress_channel == "chan-1"
    assert request.progress_token == "tok-1"
    assert request.spellcheck == "en-US"


def test_dense_mode_aliases_map_onto_core_spellings() -> None:
    assert OCRRequest(dense_mode="on").dense_mode_normalized == "always"
    assert OCRRequest(dense_mode="off").dense_mode_normalized == "never"
    assert OCRRequest(dense_mode="auto").dense_mode_normalized == "auto"
    assert OCRRequest(dense_mode="always").dense_mode_normalized == "always"
    # unknown values fall back to auto rather than failing the upload
    assert OCRRequest(dense_mode="bogus").dense_mode_normalized == "auto"


def test_unknown_document_processor_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown document processor"):
        OCRRequest(document_processors="reading_order,bogus_processor")


def test_quality_loop_bounds_are_enforced() -> None:
    request = OCRRequest(
        quality_loop_enabled="false", quality_target="0.9", quality_max_retries="4"
    )
    assert request.quality_loop_enabled is False
    assert request.quality_target == pytest.approx(0.9)
    assert request.quality_max_retries == 4
    with pytest.raises(ValidationError):
        OCRRequest(quality_target="1.5")
    with pytest.raises(ValidationError):
        OCRRequest(quality_target="0.4")
    with pytest.raises(ValidationError):
        OCRRequest(quality_max_retries="6")


def test_preprocessing_enabled_master_flag_wins() -> None:
    assert OCRRequest(preprocess_pages="true").preprocessing_enabled is True
    assert (
        OCRRequest(preprocess_pages="false", denoise="true").preprocessing_enabled
        is False
    )
    assert OCRRequest(denoise="true").preprocessing_enabled is True
    assert OCRRequest().preprocessing_enabled is False


def test_response_shapes_match_frontend_contracts() -> None:
    submit = AsyncSubmitResponse(job_id="j1", status_url="/api/process/status/j1")
    assert submit.model_dump() == {
        "job_id": "j1",
        "status": "pending",
        "status_url": "/api/process/status/j1",
    }

    # 2026-08-29 audit C-3 / H-3: the result token is intentionally
    # not a field on JobStatusResponse. The async client receives it
    # out-of-band via the ``job_completed`` SSE event payload.
    status = JobStatusResponse(
        job_id="j1",
        filename="a.pdf",
        status="complete",
        created_at=1.0,
        started_at=2.0,
        completed_at=3.0,
        duration_s=2.0,
        text_artifact_id="art",
        failed_pages=[2],
    )
    payload = status.model_dump()
    # frontend OcrJobStatusResponse field set
    assert set(payload) == {
        "job_id",
        "filename",
        "status",
        "created_at",
        "started_at",
        "completed_at",
        "duration_s",
        "error",
        "text_artifact_id",
        "failed_pages",
    }

    item = JobListItemResponse(id="j1", status="complete", timestamp="2026-01-01")
    assert set(item.model_dump()) == {
        "id",
        "filename",
        "model",
        "pipeline_mode",
        "pages",
        "duration_s",
        "timestamp",
        "status",
        "failed_pages",
    }
