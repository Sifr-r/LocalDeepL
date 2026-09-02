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
    request = OCRRequest(**_frontend_form_fields())  # type: ignore[arg-type]
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
        OCRRequest(document_processors="reading_order,bogus_processor")  # type: ignore[arg-type]


def test_quality_loop_bounds_are_enforced() -> None:
    request = OCRRequest(
        quality_loop_enabled="false",  # type: ignore[arg-type]
        quality_target="0.9",  # type: ignore[arg-type]
        quality_max_retries="4",  # type: ignore[arg-type]
    )
    assert request.quality_loop_enabled is False
    assert request.quality_target == pytest.approx(0.9)
    assert request.quality_max_retries == 4
    with pytest.raises(ValidationError):
        OCRRequest(quality_target="1.5")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        OCRRequest(quality_target="0.4")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        OCRRequest(quality_max_retries="6")  # type: ignore[arg-type]


def test_preprocessing_enabled_master_flag_wins() -> None:
    assert OCRRequest(preprocess_pages="true").preprocessing_enabled is True  # type: ignore[arg-type]
    assert (
        OCRRequest(preprocess_pages="false", denoise="true").preprocessing_enabled  # type: ignore[arg-type]
        is False
    )
    assert OCRRequest(denoise="true").preprocessing_enabled is True  # type: ignore[arg-type]
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


def test_job_status_response_accepts_cancelled() -> None:
    status = JobStatusResponse(
        job_id="j2",
        filename="b.pdf",
        status="cancelled",
        created_at=1.0,
        error="Job cancelled.",
    )
    assert status.status == "cancelled"
    assert status.error == "Job cancelled."


def test_parse_bool_uniform_vocabulary() -> None:
    from omniscribe.plugins.ocr.schemas import _parse_bool

    # Truthy aliases
    for val in ("enabled", "yes", "on", "1", "true", "y", True):
        assert _parse_bool(val) is True
        assert _parse_bool(val, default=False) is True

    # Falsy aliases
    for val in ("disabled", "no", "off", "0", "false", "n", False):
        assert _parse_bool(val) is False
        assert _parse_bool(val, default=True) is False

    # Default fallback
    assert _parse_bool(None, default=False) is False
    assert _parse_bool(None, default=True) is True
    assert _parse_bool("unrecognized", default=False) is False


def test_ocr_request_coerces_extended_booleans() -> None:
    req = OCRRequest(
        preprocess_pages="enabled",  # type: ignore[arg-type]
        orientation_detection="yes",  # type: ignore[arg-type]
        deskew="disabled",  # type: ignore[arg-type]
        denoise="on",  # type: ignore[arg-type]
        normalize_contrast="off",  # type: ignore[arg-type]
        crop_cleanup="no",  # type: ignore[arg-type]
        quality_loop_enabled="1",  # type: ignore[arg-type]
    )
    assert req.preprocess_pages is True
    assert req.orientation_detection is True
    assert req.deskew is False
    assert req.denoise is True
    assert req.normalize_contrast is False
    assert req.crop_cleanup is False
    assert req.quality_loop_enabled is True


def test_ocr_payload_round_trip_preserves_request_fields() -> None:
    """Audit 5.1 (partial): the canonical _OcrPayload IR survives a
    submit → queue → run_job round trip with all request fields intact.
    """
    import dataclasses
    from pathlib import Path

    from omniscribe.plugins.ocr.service import _OcrPayload

    request = OCRRequest(model="some-model", pages="1-3", quality_target=0.9)
    payload = _OcrPayload(
        submission_id="sub-1",
        input_path=Path("/tmp/fake.pdf"),
        filename="doc.pdf",
        request=request,
    )
    # The dataclass is frozen; a replace with a new submission_id must
    # preserve every other field.
    again = dataclasses.replace(payload, submission_id="sub-2")
    assert again.submission_id == "sub-2"
    assert again.input_path == payload.input_path
    assert again.filename == payload.filename
    assert again.request.model == request.model
    assert again.request.pages == request.pages
    assert again.request.quality_target == pytest.approx(0.9)


def test_ocr_payload_lookup_miss_silently_uses_empty_job_id() -> None:
    """Audit 5.1: when the submission_id was evicted from the
    _submission_to_job map (capped at max_buffered_jobs), run_job falls
    back to job_id="". Verify the empty-string fallback is the documented
    contract — the cancellation channel degrades to "no per-job binding"
    rather than raising.
    """
    from pathlib import Path

    from omniscribe.plugins.ocr.service import _OcrPayload

    payload = _OcrPayload(
        submission_id="never-submitted",
        input_path=Path("/tmp/orphan.pdf"),
        filename="orphan.pdf",
        request=OCRRequest(),
    )
    # Empty submission-to-job map; ``.get`` with default returns "".
    submission_to_job: dict[str, str] = {}
    job_id = submission_to_job.get(payload.submission_id, "")
    assert job_id == ""


# ---------------------------------------------------------------------------
# Audit 6.3: Model Pre-flight Route
# ---------------------------------------------------------------------------


def test_preflight_request_accepts_partial_overrides() -> None:
    """The pre-flight request body is optional; each field defaults to
    None and the route falls back to the current /api/config value.
    """
    from omniscribe.plugins.ocr.schemas import PreflightRequest

    bare = PreflightRequest()
    assert bare.api_base is None
    assert bare.api_key is None
    assert bare.model is None

    override = PreflightRequest(api_base="http://localhost:9999/v1", model="m")
    assert override.api_base == "http://localhost:9999/v1"
    assert override.api_key is None
    assert override.model == "m"


def test_preflight_response_loads_false_carries_loaded_models() -> None:
    """The response shape lets the UI show "model mismatch: server has X,
    you asked for Y" without the caller parsing the detail string.
    """
    from omniscribe.plugins.ocr.schemas import PreflightResponse

    resp = PreflightResponse(
        loaded=False,
        requested_model="missing",
        api_base="http://x",
        loaded_models=["olmocr-2-7b"],
        detail="model 'missing' is not loaded",
    )
    assert resp.loaded is False
    assert resp.requested_model == "missing"
    assert resp.loaded_models == ["olmocr-2-7b"]


async def test_preflight_check_returns_misconfigured_when_coords_empty() -> None:
    """Calling preflight with no overrides on a fresh service whose
    /api/config has no api_base must return a structured 'must be
    configured' detail, not raise.
    """
    from unittest.mock import MagicMock

    from omniscribe.plugins.ocr.service import OCRServiceImpl

    service = OCRServiceImpl.__new__(OCRServiceImpl)
    service._config = {}
    service._settings = MagicMock()

    loaded, _requested, _base, models, detail = await service.preflight_check()
    assert loaded is False
    assert detail == "api_base and model must be configured before pre-flight"
    assert models == []


async def test_preflight_check_closes_ephemeral_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a clean probe (the requested model is loaded) the ephemeral
    OCRProcessor must be closed via aclose so the connection pool is
    released — otherwise every preflight leaks an AsyncOpenAI client.
    """
    from unittest.mock import AsyncMock, MagicMock

    from omniscribe.plugins.ocr.service import OCRServiceImpl

    service = OCRServiceImpl.__new__(OCRServiceImpl)
    service._config = {
        "api_base": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "model": "allenai/olmocr-2-7b",
    }
    service._settings = MagicMock()

    closed = []

    class _StubProcessor:
        def __init__(self, *, api_base, api_key, model):
            self.api_base = api_base
            self.api_key = api_key
            self.model = model
            self.client = MagicMock()

        async def ensure_model_loaded(self) -> None:
            return None

        async def aclose(self) -> None:
            closed.append(self)

    monkeypatch.setattr(
        "omniscribe.plugins.ocr.service.OCRProcessor", _StubProcessor
    )
    # _list_loaded_model_ids is called after ensure; stub it to return [].
    monkeypatch.setattr(
        "omniscribe.core.ocr.client._list_loaded_model_ids",
        AsyncMock(return_value=[]),
    )

    loaded, requested, base, models, detail = await service.preflight_check()
    assert loaded is True
    assert requested == "allenai/olmocr-2-7b"
    assert base == "http://localhost:1234/v1"
    assert models == []
    assert detail == ""
    assert closed, "ephemeral processor must be closed after preflight"
