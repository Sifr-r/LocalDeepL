"""Tests for ``GET /api/jobs/{job_id}/result`` (Phase D2.1).

The route streams the searchable PDF produced by a completed
``POST /api/process/async`` job. The acceptance contract:

- 404 when the job_id is unknown (never submitted or already evicted).
- 409 when the job exists but is not yet COMPLETE (PENDING,
  PROCESSING, ERROR).
- 403 when the access token is missing or does not match the
  record's ``text_artifact_token`` (constant-time compare).
- 410 when the job is COMPLETE but the underlying output file has
  been removed from disk (e.g. cleanup ran after the record).
- 200 with the PDF body and ``Content-Type: application/pdf`` when
  the token matches and the file is on disk.

Tests run against the live ``state.ocr_job_queue`` singleton
created by :mod:`omniscribe.api.routers.state` so the route's
``state.ocr_job_queue.get(...)`` call hits the same instance the
production handler does.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import jobs
from omniscribe.api.routers import state as router_state
from omniscribe.api.services.ocr.jobs import (
    OCRJobQueue,
    OCRJobRecord,
    OCRJobStatus,
)


@pytest.fixture
def fresh_queue():
    """Replace the shared queue with a fresh instance for one test.

    The module-level singleton carries state across tests (the worker
    coroutine, the records dict). Restoring the original on teardown
    keeps :func:`test_state_module_is_singleton_boundary` happy — that
    test asserts ``state.ocr_job_queue is state.backend.ocr_job_queue``
    and would fail if a leftover ``OCRJobQueue()`` from this fixture
    were still bound to the module.
    """
    original = router_state.ocr_job_queue
    queue = OCRJobQueue()
    router_state.ocr_job_queue = queue
    try:
        yield queue
    finally:
        router_state.ocr_job_queue = original


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(jobs.router)
    return TestClient(app)


def _seed_completed_job(
    queue: OCRJobQueue,
    tmp_path: Path,
    *,
    filename: str = "doc.pdf",
    token: str = "test-token-secret",
) -> tuple[str, Path]:
    """Materialise a COMPLETE record pointing at a real PDF on disk.

    Returns ``(job_id, pdf_path)`` so the caller can assert against
    the same file the route should stream.
    """
    job_id = f"job-{int(time.time() * 1000)}"
    pdf_path = tmp_path / "result.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% fake PDF for tests\n%%EOF\n")
    record = OCRJobRecord(
        job_id=job_id,
        filename=filename,
        status=OCRJobStatus.COMPLETE,
        created_at=time.monotonic(),
        started_at=time.monotonic(),
        completed_at=time.monotonic(),
        duration_s=1.0,
        text_artifact_id="aid-test",
        text_artifact_token=token,
        output_pdf_path=str(pdf_path),
        failed_pages=[],
    )
    queue._records[job_id] = record  # type: ignore[attr-defined]
    return job_id, pdf_path


def _peek_first_id(queue: OCRJobQueue) -> str:
    """Return the first job_id in the queue (test helper)."""
    if not queue._records:  # type: ignore[attr-defined]
        raise AssertionError("queue is empty")
    return next(iter(queue._records))  # type: ignore[attr-defined]


def test_job_result_unknown_id_returns_404(fresh_queue, tmp_path: Path) -> None:
    client = _build_client()
    response = client.get("/api/jobs/missing-id/result")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"error": "Job not found"}


def test_job_result_pending_returns_409(fresh_queue, tmp_path: Path) -> None:
    fresh_queue._records["pending-1"] = OCRJobRecord(  # type: ignore[attr-defined]
        job_id="pending-1", filename="x.pdf", status=OCRJobStatus.PENDING
    )
    client = _build_client()
    response = client.get("/api/jobs/pending-1/result")
    assert response.status_code == HTTPStatus.CONFLICT
    body = response.json()
    assert body["error"] == "Job is not complete"
    assert body["status"] == "pending"


def test_job_result_processing_returns_409(fresh_queue, tmp_path: Path) -> None:
    fresh_queue._records["processing-1"] = OCRJobRecord(  # type: ignore[attr-defined]
        job_id="processing-1", filename="x.pdf", status=OCRJobStatus.PROCESSING
    )
    client = _build_client()
    response = client.get("/api/jobs/processing-1/result")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["status"] == "processing"


def test_job_result_error_returns_409(fresh_queue, tmp_path: Path) -> None:
    fresh_queue._records["error-1"] = OCRJobRecord(  # type: ignore[attr-defined]
        job_id="error-1",
        filename="x.pdf",
        status=OCRJobStatus.ERROR,
        error="engine raised",
    )
    client = _build_client()
    response = client.get("/api/jobs/error-1/result")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["status"] == "error"


def test_job_result_completed_without_token_returns_403(
    fresh_queue, tmp_path: Path
) -> None:
    _seed_completed_job(fresh_queue, tmp_path)
    client = _build_client()
    job_id = _peek_first_id(fresh_queue)
    response = client.get(f"/api/jobs/{job_id}/result")
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {"error": "Result access denied"}


def test_job_result_completed_with_wrong_token_returns_403(
    fresh_queue, tmp_path: Path
) -> None:
    _seed_completed_job(fresh_queue, tmp_path, token="correct-token")
    client = _build_client()
    job_id = _peek_first_id(fresh_queue)
    response = client.get(
        f"/api/jobs/{job_id}/result",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_job_result_completed_with_correct_token_returns_pdf(
    fresh_queue, tmp_path: Path
) -> None:
    job_id, pdf_path = _seed_completed_job(
        fresh_queue, tmp_path, filename="report.pdf", token="good-token"
    )
    client = _build_client()
    response = client.get(
        f"/api/jobs/{job_id}/result",
        headers={"Authorization": "Bearer good-token"},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == pdf_path.read_bytes()


def test_job_result_completed_with_query_token_returns_pdf(
    fresh_queue, tmp_path: Path
) -> None:
    """``?token=`` is the legacy artifact-download convention; the
    result route accepts the same query-param shape so a browser
    link (or curl) works without setting a header."""
    job_id, pdf_path = _seed_completed_job(fresh_queue, tmp_path, token="query-token")
    client = _build_client()
    response = client.get(f"/api/jobs/{job_id}/result?token=query-token")
    assert response.status_code == HTTPStatus.OK
    assert response.content == pdf_path.read_bytes()


def test_job_result_completed_but_file_missing_returns_410(
    fresh_queue, tmp_path: Path
) -> None:
    """The 24h retention sweeper drops the on-disk PDF; the record
    may still be in memory. The route must report 410 Gone, not 500."""
    job_id, pdf_path = _seed_completed_job(fresh_queue, tmp_path, token="t")
    pdf_path.unlink()
    client = _build_client()
    response = client.get(
        f"/api/jobs/{job_id}/result",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == HTTPStatus.GONE
    assert response.json() == {"error": "Result file no longer available"}


def test_job_result_content_disposition_uses_filename(
    fresh_queue, tmp_path: Path
) -> None:
    job_id, _ = _seed_completed_job(
        fresh_queue, tmp_path, filename="quarterly-report.pdf", token="t"
    )
    client = _build_client()
    response = client.get(
        f"/api/jobs/{job_id}/result",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == HTTPStatus.OK
    # FastAPI's FileResponse sets a Content-Disposition header with
    # the original filename (preserving the user's intent).
    disposition = response.headers.get("content-disposition", "")
    assert "quarterly-report.ocr.pdf" in disposition
