"""POST /api/progress/session and the cancel mirror route."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_session_returns_channel_and_token(api_client: TestClient) -> None:
    response = api_client.post("/api/progress/session", json={"client_id": "c1"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"channel_id", "session_token"}
    assert body["channel_id"] and body["session_token"]


def test_two_sessions_get_distinct_channels(api_client: TestClient) -> None:
    first = api_client.post("/api/progress/session", json={}).json()
    second = api_client.post("/api/progress/session", json={}).json()
    assert first["channel_id"] != second["channel_id"]
    assert first["session_token"] != second["session_token"]


def test_cancel_endpoint_confirms(api_client: TestClient) -> None:
    body = api_client.post("/api/progress/session", json={}).json()
    response = api_client.post(f"/api/progress/cancel/{body['channel_id']}")
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
