"""Token-bound progress WebSocket channels: auth frames and cancel guard.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("fastapi")

from omniscribe.api.routers import websocket
from tests.api._safety_helpers import _api_client


def _wait_for_ws_authorization(
    channel_id: str, token: str, timeout: float = 5.0
) -> None:
    """Poll until the server honors a WS auth frame.

    The TestClient runs the app on a portal thread; the auth frame is
    processed asynchronously and the handshake sends no ack frame to
    synchronize on, so an immediate ``is_authorized`` assertion races
    the server. Polling makes the success path deterministic while the
    rejection paths stay synchronous (the 1008 close round-trips).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if websocket.manager.is_authorized(channel_id, token):
            return
        time.sleep(0.01)
    raise AssertionError(f"WS channel {channel_id!r} was never authorized")


def test_progress_session_uses_token_bound_websocket_channels():
    client = _api_client()

    session_response = client.post(
        "/api/progress/session", json={"client_id": "visible-client"}
    )
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["channel_id"] != "visible-client"
    assert session["session_token"] != "visible-client"

    # The token travels in the first inbound frame, never in the URL.
    with client.websocket_connect(f"/ws/{session['channel_id']}") as ws:
        ws.send_text(
            json.dumps({"type": "auth", "session_token": session["session_token"]})
        )
        _wait_for_ws_authorization(session["channel_id"], session["session_token"])
        assert not websocket.manager.is_authorized(session["channel_id"], "A" * 32)


def test_ws_handshake_rejects_wrong_unminted_and_silent_tokens():
    """The connect-time binding must reject tokens the server never
    minted and tokens that don't match the channel's minted pair — and
    a connection that never sends the auth frame must not be honored.
    """
    from starlette.websockets import WebSocketDisconnect

    client = _api_client()
    session = client.post("/api/progress/session", json={}).json()
    channel_id = session["channel_id"]
    token = session["session_token"]

    # 1) Wrong token for a minted channel -> 1008 close, never authorized.
    with pytest.raises(WebSocketDisconnect) as wrong_token:
        with client.websocket_connect(f"/ws/{channel_id}") as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": "B" * len(token)})
            )
            ws.receive_text()
    assert wrong_token.value.code == 1008
    assert not websocket.manager.is_authorized(channel_id, "B" * len(token))

    # 2) Channel the server never minted -> 1008 close.
    with pytest.raises(WebSocketDisconnect) as unminted:
        with client.websocket_connect(f"/ws/{'C' * 43}") as ws:
            ws.send_text(json.dumps({"type": "auth", "session_token": token}))
            ws.receive_text()
    assert unminted.value.code == 1008
    assert not websocket.manager.is_authorized("C" * 43, token)

    # 3) Non-auth first frame (e.g. a cancel smuggled before auth) ->
    #    1008 close and the cancel flag is NOT set.
    with pytest.raises(WebSocketDisconnect) as silent:
        with client.websocket_connect(f"/ws/{channel_id}") as ws:
            ws.send_text(json.dumps({"type": "cancel"}))
            ws.receive_text()
    assert silent.value.code == 1008
    assert not websocket.manager.is_cancelled(channel_id)

    # The minted pair survives failed attempts: the legitimate client
    # can still connect with the correct first frame.
    with client.websocket_connect(f"/ws/{channel_id}") as ws:
        ws.send_text(json.dumps({"type": "auth", "session_token": token}))
        _wait_for_ws_authorization(channel_id, token)


def test_progress_cancel_requires_session_token_header():
    """``/api/progress/cancel/{channel_id}`` must reject any request that
    does not present the ``X-Progress-Token`` header (or presents a token
    that does not match the channel). Without this guard, any
    authenticated user can cancel any other user's channel by guessing
    the channel_id."""
    client = _api_client()
    session = client.post("/api/progress/session", json={"client_id": "x"}).json()
    channel_id = session["channel_id"]
    token = session["session_token"]

    # The session token is only registered in ``manager._tokens`` once
    # a websocket connects and authenticates (the channel lifecycle is
    # connect → auth-frame → register-token → cancel-flag). Open a stub
    # websocket first so the manager has the binding in place.
    with client.websocket_connect(f"/ws/{channel_id}") as ws:
        ws.send_text(json.dumps({"type": "auth", "session_token": token}))
        # 1) No header → 403, cancel flag NOT set.
        no_header = client.post(f"/api/progress/cancel/{channel_id}")
        assert no_header.status_code == 403
        assert "X-Progress-Token" in no_header.json()["error"]
        assert not websocket.manager.is_cancelled(channel_id)

        # 2) Wrong token → 403, cancel flag NOT set.
        bad_token = client.post(
            f"/api/progress/cancel/{channel_id}",
            headers={"X-Progress-Token": "B" * len(token)},
        )
        assert bad_token.status_code == 403
        assert not websocket.manager.is_cancelled(channel_id)

        # 3) Correct token → 200, cancel flag set.
        ok = client.post(
            f"/api/progress/cancel/{channel_id}",
            headers={"X-Progress-Token": token},
        )
        assert ok.status_code == 200
        assert ok.json() == {"status": "cancel_requested"}
        assert websocket.manager.is_cancelled(channel_id)
