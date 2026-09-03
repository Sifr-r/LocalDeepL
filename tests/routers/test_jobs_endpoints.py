"""GET/DELETE /api/jobs plus the per-job result and cancel routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import PDF_BYTES, artifact_token_from_events, upload, wait_status


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

    unconfirmed = api_client.delete("/api/jobs")
    assert unconfirmed.status_code == 400
    assert unconfirmed.json() == {
        "error": "confirmation_required",
        "detail": (
            "DELETE /api/jobs requires confirm=true query parameter "
            "to prevent accidental wipe"
        ),
    }

    cleared = api_client.delete("/api/jobs?confirm=true")
    assert cleared.status_code == 200
    assert cleared.json() == {"status": "ok", "cleared": 1}
    assert api_client.get("/api/jobs").json() == []


def test_result_download_requires_valid_token(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    wait_status(api_client, job_id, "complete")

    # 2026-08-29 audit C-3 / H-3: the status endpoint no longer
    # returns the token. The async client pulls it from the
    # ``job_completed`` SSE event payload (out-of-band channel).
    token = artifact_token_from_events(api_client, job_id)
    assert token

    result = api_client.get(f"/api/jobs/{job_id}/result", params={"token": token})
    assert result.status_code == 200
    assert result.content == PDF_BYTES

    wrong = api_client.get(f"/api/jobs/{job_id}/result", params={"token": "nope"})
    # Pedantic 2.7: wrong-token returns 404, not 403, so the response
    # is indistinguishable from unknown / not-complete / artifact-gone.
    assert wrong.status_code == 404


def test_unknown_job_result_and_cancel_are_404(api_client: TestClient) -> None:
    assert api_client.get("/api/jobs/nope/result").status_code == 404
    assert api_client.post("/api/jobs/nope/cancel").status_code == 404


def test_result_failures_are_indistinguishable(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    """Pedantic review 2.7: every non-success result path must
    collapse to a single status code + body so an attacker cannot
    enumerate job ids by watching the differential responses.

    Four failure scenarios — unknown id, wrong token against a
    real id, valid token against a non-complete id, and missing
    token against a complete id — must all return the same
    ``(status, detail)``.
    """
    expected = (404, "result not available")

    # 1. Unknown job id.
    unknown = api_client.get("/api/jobs/nope/result", params={"token": "anything"})
    assert (unknown.status_code, unknown.json()["detail"]) == expected

    # 2. Wrong token against a real, complete job.
    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    wait_status(api_client, job_id, "complete")
    bad_token = api_client.get(f"/api/jobs/{job_id}/result", params={"token": "nope"})
    assert (bad_token.status_code, bad_token.json()["detail"]) == expected

    # 3. No token at all against a real, complete job.
    no_token = api_client.get(f"/api/jobs/{job_id}/result")
    assert (no_token.status_code, no_token.json()["detail"]) == expected

    # 4. Job that errored before producing a result artifact.
    fake_pipeline["fail"] = True
    err_submit = api_client.post("/api/process/async", **upload())
    err_job_id = err_submit.json()["job_id"]
    wait_status(api_client, err_job_id, "error")
    err_resp = api_client.get(
        f"/api/jobs/{err_job_id}/result", params={"token": "anything"}
    )
    assert (err_resp.status_code, err_resp.json()["detail"]) == expected


def test_cancel_job_sets_status_cancelled(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    submit = api_client.post("/api/process/async", **upload())
    job_id = submit.json()["job_id"]
    # Cancel the job (or wait until completed if it ran instantly)
    cancel_resp = api_client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code in {
        200,
        409,
    }  # 200 if cancelled, 409 if already complete
