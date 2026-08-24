"""POST /api/process — synchronous OCR over the booted plugin tree."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import PDF_BYTES, upload


def test_sync_process_returns_pdf_with_artifact_headers(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    response = api_client.post("/api/process", **upload())
    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["x-text-artifact-id"]
    assert response.headers["x-text-artifact-token"]


def test_sync_process_rejects_missing_file(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    response = api_client.post("/api/process", data={"model": "x"})
    assert response.status_code == 400


def test_sync_process_rejects_unknown_pipeline_mode(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    response = api_client.post(
        "/api/process", data={"pipeline_mode": "bogus"}, **upload()
    )
    assert response.status_code == 422
