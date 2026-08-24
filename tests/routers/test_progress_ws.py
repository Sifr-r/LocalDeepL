"""WebSocket progress attach: first-frame auth, query-token alias, close codes."""

from __future__ import annotations

import json

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient


def _open_session(api_client: TestClient) -> dict[str, str]:
    return api_client.post("/api/progress/session", json={}).json()


def test_ws_first_frame_auth_receives_connected(api_client: TestClient) -> None:
    session = _open_session(api_client)
    with api_client.websocket_connect(f"/ws/{session['channel_id']}") as ws:
        ws.send_text(
            json.dumps({"type": "auth", "session_token": session["session_token"]})
        )
        frame = json.loads(ws.receive_text())
        assert frame["type"] == "connected"
        assert frame["channel_id"] == session["channel_id"]


def test_ws_query_token_alias_path_works(api_client: TestClient) -> None:
    session = _open_session(api_client)
    url = f"/api/progress/ws/{session['channel_id']}?token={session['session_token']}"
    with api_client.websocket_connect(url) as ws:
        frame = json.loads(ws.receive_text())
        assert frame["type"] == "connected"


def test_ws_rejected_auth_frame_closes_1008(api_client: TestClient) -> None:
    session = _open_session(api_client)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with api_client.websocket_connect(f"/ws/{session['channel_id']}") as ws:
            ws.send_text(json.dumps({"type": "auth", "session_token": "wrong-token"}))
            ws.receive_text()
    assert excinfo.value.code == 1008


def test_ws_wrong_query_token_closes_4401(api_client: TestClient) -> None:
    session = _open_session(api_client)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with api_client.websocket_connect(
            f"/ws/{session['channel_id']}?token=wrong"
        ) as ws:
            ws.receive_text()
    assert excinfo.value.code == 4401
