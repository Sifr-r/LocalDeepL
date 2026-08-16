"""
WebSocket handler tests.

Two contracts pinned here:

  * ``manager.send_progress`` produces the documented JSON wire frame
    shape, including the ``warning`` flag for partial-failure frames.
  * ``BearerAuthMiddleware`` is transparent to ``ws://`` traffic -
    enabling ``OMNISCRIBE_AUTH_TOKEN`` does not break UI clients.

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
import threading
import time
from threading import get_ident
from typing import Any

import pytest

pytest.importorskip("fastapi")


def _make_stub_ws(frames: list[str]) -> Any:
    class _StubWS:
        async def accept(self):
            pass

        async def send_text(self, text: str) -> None:
            # Mirror what ConnectionManager.send does: capture the
            # full text (including the trailing newline) so tests
            # can verify the NDJSON format.
            frames.append(text)

        async def send_json(self, payload):
            # Kept for any test that bypasses ConnectionManager and
            # calls send_json directly. Not exercised by the new
            # NDJSON path but preserved for symmetry.
            frames.append(json.dumps(payload))

    return _StubWS()


def test_ws_send_progress_round_trips_through_manager():
    """``manager.send_progress`` enqueues the documented wire frame."""
    from omniscribe.api.routers.websocket import ConnectionManager

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
    # Every frame must be NDJSON-terminated so the browser can split
    # a text frame that happens to contain multiple objects. If a
    # future refactor drops the trailing newline, this test fires
    # before the regression ships.
    for frame in sent:
        assert frame.endswith("\n"), f"frame missing NDJSON terminator: {frame!r}"


def test_ws_send_uses_ndjson_format():
    """Wire format contract: every frame is one JSON object + a single
    trailing newline. This is what the browser sees on ``event.data``
    in the common (one-frame-per-message) case, and what lets it
    recover when the transport accidentally concatenates frames.
    """
    from omniscribe.api.routers.websocket import ConnectionManager

    sent: list[str] = []
    stub = _make_stub_ws(sent)

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(stub, "abcd" * 8, "efgh" * 8)
        await manager.send_progress("abcd" * 8, "first", 10, stage="convert")
        await manager.send_block_retry(
            "abcd" * 8,
            page_idx=0,
            block_idx=3,
            attempt=2,
            confidence=0.85,
            target=0.98,
        )
        await manager.send_quality_summary(
            "abcd" * 8,
            scope="page",
            target=0.98,
            avg_confidence=0.93,
            repaired_count=2,
            below_target_count=1,
            page_idx=0,
        )

    asyncio.run(_drive())

    assert len(sent) == 3
    for frame in sent:
        assert frame.endswith("\n")
        # Each frame is exactly one JSON object, no extra leading
        # or trailing whitespace beyond the single newline terminator.
        assert frame.count("\n") == 1

    # The three frames parse independently — proving the client can
    # split a concatenated text frame on ``\n`` and recover.
    parsed = [json.loads(f) for f in sent]
    assert parsed[0] == {"status": "first", "percent": 10, "stage": "convert"}
    assert parsed[1] == {
        "type": "block_retry",
        "page_idx": 0,
        "block_idx": 3,
        "attempt": 2,
        "confidence": 0.85,
        "target": 0.98,
    }
    assert parsed[2] == {
        "type": "quality_summary",
        "scope": "page",
        "target": 0.98,
        "avg_confidence": 0.93,
        "repaired_count": 2,
        "below_target_count": 1,
        "page_idx": 0,
    }


def test_ws_ndjson_recovery_from_concatenated_text_frame():
    """Browser-side simulation: if the transport concatenates two
    frames into one text payload, the NDJSON delimiter lets the
    client split and parse each independently. This is the failure
    mode that produced the browser console errors when the OCR
    pipeline fired many progress / block_retry events in a burst.
    """
    from omniscribe.api.routers.websocket import ConnectionManager

    sent: list[str] = []
    stub = _make_stub_ws(sent)

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(stub, "abcd" * 8, "efgh" * 8)
        await manager.send_progress("abcd" * 8, "a", 10, stage="convert")
        await manager.send_progress("abcd" * 8, "b", 20, stage="ocr")

    asyncio.run(_drive())

    # Simulate a buggy transport that delivers both frames in one
    # text message. The NDJSON delimiter makes that recoverable.
    concatenated = "".join(sent)
    assert concatenated.count("\n") == 2

    frames = [json.loads(line) for line in concatenated.split("\n") if line]
    assert frames == [
        {"status": "a", "percent": 10, "stage": "convert"},
        {"status": "b", "percent": 20, "stage": "ocr"},
    ]


async def test_ws_send_from_foreign_event_loop_is_marshaled_to_accept_loop():
    """Cross-loop send marshalling — regression test for wire corruption.

    ``/api/process`` runs ``pipeline.run`` under ``asyncio.run()`` in a
    worker thread (its own event loop) while progress frames are emitted
    from the main uvicorn loop. The block-level senders are awaited on
    the worker loop; before the fix they wrote to the same uvicorn
    WebSocket from two loops in two threads at once. uvicorn's wsproto
    state machine is not thread-safe, so frames interleaved byte-by-byte
    on the wire — the browser saw mangled JSON fragments ("pairge") and
    eventually "Invalid frame header".

    Contract pinned here: when ``manager.send`` is awaited on a loop
    other than the one the channel was accepted on, the underlying
    ``send_text`` must still execute on the accept loop's thread.
    """
    from omniscribe.api.routers.websocket import ConnectionManager

    sent: list[str] = []
    send_threads: list[int] = []
    accept_thread: dict[str, int] = {}

    class _RecordingWS:
        async def accept(self):
            pass

        async def send_text(self, text: str) -> None:
            send_threads.append(get_ident())
            sent.append(text)

    manager = ConnectionManager()
    channel_id = "abcd" * 8

    async def _accept():
        await manager.connect(_RecordingWS(), channel_id, "efgh" * 8)
        accept_thread["id"] = get_ident()

    def _worker_send() -> None:
        async def _send():
            await manager.send_block(
                channel_id,
                page_idx=0,
                block_idx=1,
                bbox=[0.0, 0.0, 1.0, 1.0],
                text="from worker loop",
            )

        asyncio.run(_send())

    await _accept()
    worker = threading.Thread(target=_worker_send)
    worker.start()
    deadline = time.monotonic() + 5.0
    while not sent and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    worker.join(timeout=5.0)

    # Also emit from the accept loop itself, proving the fast path still
    # works alongside marshalled sends.
    await manager.send_progress(channel_id, "from main loop", 50, stage="ocr")

    assert len(sent) == 2, "both frames must reach the socket"
    assert send_threads[0] == accept_thread["id"], (
        "send from a foreign event loop must be marshalled onto the "
        "accept loop's thread — concurrent cross-thread writes corrupt "
        "WebSocket frames on the wire"
    )
    parsed = [json.loads(frame) for frame in sent]
    assert parsed[0]["type"] == "block_complete"
    assert parsed[0]["text"] == "from worker loop"
    assert parsed[1] == {"status": "from main loop", "percent": 50, "stage": "ocr"}


def test_ws_send_progress_with_unknown_channel_is_noop():
    """Pushing to a channel that has no subscriber must not raise."""
    from omniscribe.api.routers.websocket import ConnectionManager

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
    from omniscribe.api.services.security_middleware import BearerAuthMiddleware

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
    from omniscribe.api.services.security_middleware import BearerAuthMiddleware

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
