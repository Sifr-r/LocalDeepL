"""Boot tests for the translate plugin in the harness tree."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_translate_routes_survive_full_boot(api_client: TestClient) -> None:
    # FastAPI >=0.141 hides mounted plugin routes from app.routes —
    # assert against the public /openapi.json surface instead.
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/translate" in paths
    assert "/api/translate/async" in paths
    assert api_client.get("/api/health").status_code == 200


def test_translate_route_rejects_bad_body_off_real_tree(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/translate", json={"target_language": "French"})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
