"""Liveness and readiness probes owned by the health plugin."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_probes_report_ok(api_client: TestClient) -> None:
    for path in ("/api/health", "/api/healthz"):
        response = api_client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_readiness_probes_flip_ready_after_boot(api_client: TestClient) -> None:
    """The lifespan marks the harness ready, so probes answer 200 inside
    the TestClient context."""
    for path in ("/ready", "/readyz"):
        response = api_client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
