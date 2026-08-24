"""GET /api/process/status/{job_id} — the frontend polling contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import upload, wait_status

_STATUS_KEYS = {
    "job_id",
    "filename",
    "status",
    "created_at",
    "started_at",
    "completed_at",
    "duration_s",
    "error",
    "text_artifact_id",
    "text_artifact_token",
    "text_artifact_url",
    "failed_pages",
}


def test_unknown_job_status_is_404(api_client: TestClient) -> None:
    response = api_client.get("/api/process/status/does-not-exist")
    assert response.status_code == 404


def test_status_response_matches_frontend_contract(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    done = wait_status(api_client, job_id, "complete")
    assert set(done) == _STATUS_KEYS
    assert done["job_id"] == job_id
    assert done["status"] in {"pending", "processing", "complete", "error"}
    assert done["completed_at"] is not None
    assert done["duration_s"] is not None
    assert done["error"] is None
