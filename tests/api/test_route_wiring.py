"""Route wiring: namespaced aliases, job cancel, error envelope shape.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")

from omniscribe.api.routers import state
from omniscribe.api.services.uploads import api_error_response
from tests.api._safety_helpers import _api_client


def test_namespaced_ocr_and_artifact_aliases_are_registered():
    client = _api_client()

    assert client.post("/process").status_code == 422
    assert client.post("/api/process").status_code == 422
    assert client.post("/process/async").status_code == 422
    assert client.post("/api/process/async").status_code == 422
    assert client.get("/process/status/missing").status_code == 404
    assert client.get("/api/process/status/missing").status_code == 404

    def _extract_paths(routes):
        paths = set()
        for route in routes:
            if hasattr(route, "path") and route.path:
                paths.add(route.path)
            if hasattr(route, "routes"):
                paths.update(_extract_paths(route.routes))
            elif hasattr(route, "original_router") and hasattr(
                route.original_router, "routes"
            ):
                paths.update(_extract_paths(route.original_router.routes))
            elif hasattr(route, "router") and hasattr(route.router, "routes"):
                paths.update(_extract_paths(route.router.routes))
            elif hasattr(route, "app") and hasattr(route.app, "routes"):
                paths.update(_extract_paths(route.app.routes))
        return paths

    route_paths = _extract_paths(client.app.routes)
    assert {
        "/api/text/{artifact_id}",
        "/api/artifacts/text/{artifact_id}",
        "/api/metadata/{artifact_id}",
        "/api/artifacts/metadata/{artifact_id}",
        "/api/export/{artifact_id}",
        "/api/artifacts/export/{artifact_id}",
    } <= route_paths


def test_namespaced_text_artifact_aliases_share_legacy_handler():
    handle = asyncio.run(state.text_artifacts.create({1: ["alias text"]}))
    client = _api_client()
    headers = {"Authorization": f"Bearer {handle.token}"}
    try:
        legacy = client.get(f"/text/{handle.artifact_id}", headers=headers)
        canonical = client.get(f"/api/text/{handle.artifact_id}", headers=headers)
        frontend = client.get(
            f"/api/artifacts/text/{handle.artifact_id}", headers=headers
        )
        assert (
            legacy.status_code == canonical.status_code == frontend.status_code == 200
        )
        assert legacy.json() == canonical.json() == frontend.json()
    finally:
        asyncio.run(state.text_artifacts.delete(handle.artifact_id, handle.token))


def test_cancel_unknown_background_ocr_job_returns_404():
    response = _api_client().post("/api/jobs/missing/cancel")
    assert response.status_code == 404
    assert response.json() == {"error": "Job not found"}


def test_api_error_response_envelope_shape():
    # Without detail: opaque 500-style — no extra keys.
    response = api_error_response(500, "Server exploded.")
    assert response.status_code == 500
    assert response.body == b'{"error":"Server exploded."}'

    # With detail: structured extra context follows ``error``.
    response = api_error_response(422, "Bad shape.", detail={"field": "missing"})
    assert response.status_code == 422
    assert response.body == b'{"error":"Bad shape.","detail":{"field":"missing"}}'

    # Status code is preserved through the helper.
    response = api_error_response(403, "Forbidden.")
    assert response.status_code == 403
    assert response.body == b'{"error":"Forbidden."}'
