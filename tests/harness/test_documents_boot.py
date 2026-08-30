"""Boot tests for the documents plugin in the harness tree."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_documents_routes_survive_full_boot(api_client: TestClient) -> None:
    # FastAPI >=0.141 wraps plugin routers in private _IncludedRouter
    # objects, so app.routes introspection cannot see mounted paths —
    # assert against the public /openapi.json surface instead.
    paths = set(json.loads(api_client.get("/openapi.json").text)["paths"])
    assert "/api/extract" in paths
    assert "/api/export/document" in paths
    # Health still answers after the tenth plugin mounts.
    assert api_client.get("/api/health").status_code == 200


def test_extract_route_rejects_empty_text_off_real_tree(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/extract", json={"text": "", "template": "invoice"})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
