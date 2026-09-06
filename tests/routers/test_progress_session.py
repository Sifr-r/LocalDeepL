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


def test_cancel_endpoint_requires_session_token(api_client: TestClient) -> None:
    """Audit S6: the cancel handler is a denial-of-service surface
    against an in-progress job. An unauthenticated request must NOT
    cancel a channel; the new contract is 401 + a hint pointing at
    the X-Session-Token header / session_token query param.
    """
    body = api_client.post("/api/progress/session", json={}).json()
    response = api_client.post(f"/api/progress/cancel/{body['channel_id']}")
    assert response.status_code == 401
    assert "session token required" in response.json()["detail"]


def test_cancel_endpoint_succeeds_with_valid_token(api_client: TestClient) -> None:
    body = api_client.post("/api/progress/session", json={}).json()
    response = api_client.post(
        f"/api/progress/cancel/{body['channel_id']}",
        headers={"X-Session-Token": body["session_token"]},
    )
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
