"""GET/DELETE /api/jobs plus the per-job result and cancel routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import PDF_BYTES, upload, wait_status


def test_jobs_list_is_bare_array_and_clear_works(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    assert api_client.get("/api/jobs").json() == []

    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    wait_status(api_client, job_id, "complete")

    items = api_client.get("/api/jobs").json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["id"] == job_id
    assert items[0]["filename"] == "a.pdf"
    assert items[0]["status"] == "complete"
    assert items[0]["timestamp"]

    cleared = api_client.delete("/api/jobs")
    assert cleared.status_code == 200
    assert cleared.json() == {"status": "ok", "cleared": 1}
    assert api_client.get("/api/jobs").json() == []


def test_result_download_requires_valid_token(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    done = wait_status(api_client, job_id, "complete")

    result = api_client.get(
        f"/api/jobs/{job_id}/result", params={"token": done["text_artifact_token"]}
    )
    assert result.status_code == 200
    assert result.content == PDF_BYTES

    wrong = api_client.get(f"/api/jobs/{job_id}/result", params={"token": "nope"})
    assert wrong.status_code == 403


def test_unknown_job_result_and_cancel_are_404(api_client: TestClient) -> None:
    assert api_client.get("/api/jobs/nope/result").status_code == 404
    assert api_client.post("/api/jobs/nope/cancel").status_code == 404
