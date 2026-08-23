"""WebSocket message size cap (P2 audit #12).

The receive loop in ``omniscribe.api.routers.websocket`` had no
per-message size limit: a client could send a multi-GB string and
exhaust server memory before the application layer saw it. The fix
caps each inbound frame at ``MAX_WS_MESSAGE_BYTES`` (64 KiB) and closes
the socket with WS 1009 (message too big) on overflow.

This test pins the public contract: an oversized frame after a valid
auth handshake causes the server to close with code 1009.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from omniscribe.api.routers import websocket
from omniscribe.api.routers.websocket import MAX_WS_MESSAGE_BYTES


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(websocket.router)
    return TestClient(app)


def test_oversized_message_closes_with_code_1009() -> None:
    """A frame larger than ``MAX_WS_MESSAGE_BYTES`` after a valid auth
    handshake causes the server to close the WebSocket with code 1009
    (message too big).

    The cap is on UTF-8 bytes — we send ASCII so ``len(s) == byte_len``.
    """
    client = _client()
    # Mint a channel/token pair through the same HTTP route the UI uses,
    # then open the WebSocket and complete the auth handshake so the
    # receive loop is in the post-registration state where the cap lives.
    session = client.post("/api/progress/session", json={}).json()
    channel_id = session["channel_id"]
    token = session["session_token"]

    big = "x" * (MAX_WS_MESSAGE_BYTES + 1)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{channel_id}") as ws:
            ws.send_text(json.dumps({"type": "auth", "session_token": token}))
            # Now the receive loop is running and waiting for inbound
            # control frames. Send the oversized payload — the server
            # must close with 1009 before parsing it.
            ws.send_text(big)
            ws.receive_text()
    assert exc_info.value.code == 1009
