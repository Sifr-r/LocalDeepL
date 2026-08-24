"""POST /api/process/async — queue submission and worker lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import upload, wait_status


def test_async_submit_returns_202_and_completes(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    assert submit.status_code == 202
    body = submit.json()
    assert body["status"] == "pending"
    job_id = body["job_id"]
    assert body["status_url"] == f"/api/process/status/{job_id}"

    done = wait_status(api_client, job_id, "complete")
    assert done["filename"] == "a.pdf"
    assert done["text_artifact_id"]
    assert done["text_artifact_token"]
    assert done["text_artifact_url"] == (
        f"/api/jobs/{job_id}/result?token={done['text_artifact_token']}"
    )


def test_async_failure_maps_to_error_status(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    fake_pipeline["fail"] = True
    submit = api_client.post("/api/process/async", **upload())
    assert submit.status_code == 202
    failed = wait_status(api_client, submit.json()["job_id"], "error")
    assert failed["error"] == "vlm exploded"
