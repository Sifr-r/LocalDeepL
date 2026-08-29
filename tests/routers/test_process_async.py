"""POST /api/process/async — queue submission and worker lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import artifact_token_from_events, upload, wait_status


def test_async_submit_returns_202_and_completes(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    assert submit.status_code == 202
    body = submit.json()
    assert body["status"] == "pending"
    job_id = body["job_id"]
    assert body["status_url"] == f"/api/process/status/{job_id}"

    # 2026-08-29 audit C-3 / H-3: the status response carries the
    # artifact id but not the secret token. The token is delivered
    # out-of-band via the ``job_completed`` SSE event.
    done = wait_status(api_client, job_id, "complete")
    assert done["filename"] == "a.pdf"
    assert done["text_artifact_id"]
    assert "text_artifact_token" not in done
    assert "text_artifact_url" not in done

    token = artifact_token_from_events(api_client, job_id)
    assert token
    result = api_client.get(f"/api/jobs/{job_id}/result", params={"token": token})
    assert result.status_code == 200


def test_async_failure_maps_to_error_status(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    fake_pipeline["fail"] = True
    submit = api_client.post("/api/process/async", **upload())
    assert submit.status_code == 202
    failed = wait_status(api_client, submit.json()["job_id"], "error")
    assert failed["error"] == "vlm exploded"
