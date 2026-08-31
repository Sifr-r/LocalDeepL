"""Boot tests for the transcribe + glossary plugins in the harness tree."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_phase_c_routes_survive_full_boot(api_client: TestClient) -> None:
    # FastAPI >=0.141 hides mounted plugin routes from app.routes —
    # assert against the public /openapi.json surface instead.
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/transcribe" in paths
    assert "/api/config/transcription" in paths
    assert "/api/glossary/import" in paths
    assert "/api/glossary/library" in paths
    assert api_client.get("/api/health").status_code == 200


def test_transcribe_rejects_missing_file_off_booted_app(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/transcribe")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


def test_glossary_rejects_malformed_json_off_booted_app(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/glossary/import", json={"bogus": True})
    assert response.status_code == 422
