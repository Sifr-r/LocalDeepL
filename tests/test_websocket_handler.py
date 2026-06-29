"""
WebSocket handler tests.

Two contracts pinned here:

  * ``manager.send_progress`` produces the documented JSON wire frame
    shape, including the ``warning`` flag for partial-failure frames.
  * ``BearerAuthMiddleware`` is transparent to ``ws://`` traffic -
    enabling ``LOCAL_DEEPL_AUTH_TOKEN`` does not break UI clients.

Negative handshake tests live in ``test_api_safety.py`` as
``test_progress_session_uses_token_bound_websocket_channels``: that
test asserts the manager's per-channel token binding, which is the
real security boundary for WS. The WS HTTP upgrade itself does not
authenticate (the manager accepts then compares on ``send_progress``)
- these tests document that behaviour rather than fight it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("fastapi")


def _make_stub_ws(frames: list[str]) -> Any:
    class _StubWS:
        async def accept(self):
            pass

        async def send_json(self, payload):
            frames.append(json.dumps(payload))

    return _StubWS()


def test_ws_send_progress_round_trips_through_manager():
    """``manager.send_progress`` enqueues the documented wire frame."""
    from local_deepl.api.routers.websocket import ConnectionManager

    sent: list[str] = []
    stub = _make_stub_ws(sent)

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(stub, "abcd" * 8, "efgh" * 8)
        await manager.send_progress("abcd" * 8, "started", 5, stage="convert")
        await manager.send_progress(
            "abcd" * 8,
            "OCR failed for page 3",
            0,
            stage="ocr",
            warning=True,
        )

    asyncio.run(_drive())

    assert json.loads(sent[0]) == {
        "status": "started",
        "percent": 5,
        "stage": "convert",
    }
    assert json.loads(sent[1]) == {
        "status": "OCR failed for page 3",
        "percent": 0,
        "stage": "ocr",
        "warning": True,
    }


def test_ws_send_progress_with_unknown_channel_is_noop():
    """Pushing to a channel that has no subscriber must not raise."""
    from local_deepl.api.routers.websocket import ConnectionManager

    captured: dict[str, Any] = {}

    class _Capture:
        async def accept(self):
            pass

        async def send_json(self, payload):
            captured["called"] = True

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(_Capture(), "abcd" * 8, "efgh" * 8)
        await manager.send_progress("deadbeef" * 4, "ignored", 0)

    asyncio.run(_drive())
    assert "called" not in captured


def test_bearer_middleware_is_transparent_to_websocket_scope():
    """Set ``Authorization: Bearer x`` on a WS scope - middleware passes through."""
    from local_deepl.api.services.security_middleware import BearerAuthMiddleware

    forward_called = {"yes": False}
    forwarded_scope: dict[str, Any] = {}

    async def _forward_app(scope, receive, send):
        forward_called["yes"] = True
        forwarded_scope.update(scope)

    middleware = BearerAuthMiddleware(_forward_app, expected_token="s3cret")
    ws_scope = {
        "type": "websocket",
        "headers": [(b"authorization", b"Bearer wrong-token")],
        "client": ("127.0.0.1", 1234),
    }

    async def _noop_receive():
        return {"type": "websocket.connect"}

    async def _noop_send(_msg):
        pass

    asyncio.run(middleware(ws_scope, _noop_receive, _noop_send))

    assert forward_called["yes"], "websocket scope must pass through untouched"
    assert forwarded_scope["type"] == "websocket"


def test_bearer_middleware_rejects_http_without_token():
    """Sanity: the same middleware still rejects HTTP without a token."""
    from local_deepl.api.services.security_middleware import BearerAuthMiddleware

    captured_status: list[int] = []

    async def _noop_app(scope, receive, send):
        captured_status.append(200)

    middleware = BearerAuthMiddleware(_noop_app, expected_token="s3cret")
    http_scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }

    async def _noop_receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _capture_send(msg):
        if msg["type"] == "http.response.start":
            captured_status.append(msg["status"])

    asyncio.run(middleware(http_scope, _noop_receive, _capture_send))
    assert captured_status == [401]
