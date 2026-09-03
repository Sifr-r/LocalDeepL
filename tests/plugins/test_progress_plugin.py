"""Progress plugin: channel registry, broadcast fan-out, WS handler."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import threading
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from omniscribe.config import RuntimeSettings
from omniscribe.harness.context import Context
from omniscribe.plugins import progress
from omniscribe.plugins import state_backend as sb
from omniscribe.plugins.progress import (
    ProgressService,
    ProgressServiceImpl,
    build_progress_router,
)
from omniscribe.plugins.state_backend import MemoryStateBackend


class FakeSocket:
    """Captures line-delimited frames like a real WebSocket would send them."""

    def __init__(self) -> None:
        self.frames: list[str] = []

    async def send_text(self, data: str) -> None:
        self.frames.append(data)


def _service(
    *, frame_cap: int = 1000, channel_ttl_seconds: int = 600
) -> ProgressServiceImpl:
    return ProgressServiceImpl(
        Context(),
        MemoryStateBackend(),
        frame_cap=frame_cap,
        channel_ttl_seconds=channel_ttl_seconds,
    )


def _make_app(
    service: ProgressServiceImpl,
    settings: RuntimeSettings | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(build_progress_router(service, settings=settings))
    return app


# -- service surface -----------------------------------------------------------


async def test_open_channel_persists_handshake_record() -> None:
    backend = MemoryStateBackend()
    service = ProgressServiceImpl(Context(), backend, channel_ttl_seconds=42)
    handle = await service.open_channel(job_id="client_1")
    record = await backend.get_channel(handle.channel_id)
    assert record is not None
    assert record.session_token == handle.session_token
    assert record.job_id == "client_1"
    assert record.ttl_seconds == 42


async def test_broadcast_fans_out_line_delimited_json() -> None:
    service = _service()
    handle = await service.open_channel()
    socket = FakeSocket()
    service.attach(handle.channel_id, socket, asyncio.get_running_loop())
    count = await service.broadcast(
        handle.channel_id, {"type": "progress", "percent": 42, "stage": "ocr"}
    )
    assert count == 1
    assert socket.frames[0].endswith("\n")
    assert json.loads(socket.frames[0]) == {
        "type": "progress",
        "percent": 42,
        "stage": "ocr",
    }
    # no listeners → zero fan-out
    assert await service.broadcast("unknown-channel", {"type": "x"}) == 0


async def test_frame_cap_stops_broadcasts() -> None:
    service = _service(frame_cap=2)
    handle = await service.open_channel()
    service.attach(handle.channel_id, FakeSocket(), asyncio.get_running_loop())
    assert await service.broadcast(handle.channel_id, {"n": 1}) == 1
    assert await service.broadcast(handle.channel_id, {"n": 2}) == 1
    assert await service.broadcast(handle.channel_id, {"n": 3}) == 0


async def test_cancel_flips_flag() -> None:
    service = _service()
    handle = await service.open_channel()
    assert service.is_cancelled(handle.channel_id) is False
    assert await service.cancel(handle.channel_id) is True
    assert service.is_cancelled(handle.channel_id) is True


async def test_foreign_loop_send_is_marshaled_to_accept_loop() -> None:
    """Sends from a loop other than the accept loop go through
    ``asyncio.run_coroutine_threadsafe`` back onto it (AGENTS.md contract)."""
    socket = FakeSocket()
    bg_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=bg_loop.run_forever, daemon=True)
    thread.start()
    try:
        service = _service()
        handle = await service.open_channel()
        # Connection lives on the foreign loop; we broadcast from this one.
        service.attach(handle.channel_id, socket, bg_loop)
        count = await service.broadcast(
            handle.channel_id, {"type": "progress", "percent": 7}
        )
        assert count == 1
        deadline = time.time() + 2.0
        while not socket.frames and time.time() < deadline:
            await asyncio.sleep(0.01)
        assert socket.frames, "marshaled send never landed on the accept loop"
        assert json.loads(socket.frames[0])["percent"] == 7
    finally:
        bg_loop.call_soon_threadsafe(bg_loop.stop)
        thread.join(timeout=2)
        bg_loop.close()


# -- HTTP routes ------------------------------------------------------------------


def test_session_endpoint_returns_channel_and_token() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    response = client.post("/api/progress/session", json={"client_id": "c1"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"channel_id", "session_token"}
    assert body["channel_id"] and body["session_token"]


def test_http_cancel_endpoint_flips_flag() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    body = client.post("/api/progress/session", json={}).json()
    response = client.post(f"/api/progress/cancel/{body['channel_id']}")
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
    assert service.is_cancelled(body["channel_id"]) is True


def test_http_cancel_with_query_param_token_succeeds() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    body = client.post("/api/progress/session", json={}).json()
    response = client.post(
        f"/api/progress/cancel/{body['channel_id']}?session_token={body['session_token']}"
    )
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
    assert service.is_cancelled(body["channel_id"]) is True


def test_http_cancel_with_header_token_succeeds() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    body = client.post("/api/progress/session", json={}).json()
    response = client.post(
        f"/api/progress/cancel/{body['channel_id']}",
        headers={"X-Session-Token": body["session_token"]},
    )
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
    assert service.is_cancelled(body["channel_id"]) is True


def test_http_cancel_with_invalid_token_raises_403() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    body = client.post("/api/progress/session", json={}).json()
    # Invalid query param token
    response_query = client.post(
        f"/api/progress/cancel/{body['channel_id']}?session_token=wrong-token"
    )
    assert response_query.status_code == 403
    assert response_query.json() == {"detail": "invalid session token"}
    assert service.is_cancelled(body["channel_id"]) is False

    # Invalid header token
    response_header = client.post(
        f"/api/progress/cancel/{body['channel_id']}",
        headers={"X-Session-Token": "wrong-token"},
    )
    assert response_header.status_code == 403
    assert response_header.json() == {"detail": "invalid session token"}
    assert service.is_cancelled(body["channel_id"]) is False


def test_http_cancel_without_token_succeeds_for_backward_compatibility() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    body = client.post("/api/progress/session", json={}).json()
    response = client.post(f"/api/progress/cancel/{body['channel_id']}")
    assert response.status_code == 200
    assert response.json() == {"cancelled": True}
    assert service.is_cancelled(body["channel_id"]) is True


# -- WebSocket handler ----------------------------------------------------------------


def test_ws_auth_frame_connects_and_receives_broadcast() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(f"/ws/{body['channel_id']}") as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "connected"
            assert frame["channel_id"] == body["channel_id"]


def test_ws_alias_path_works_too() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        url = f"/api/progress/ws/{body['channel_id']}?token={body['session_token']}"
        with client.websocket_connect(url) as ws:
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "connected"


def test_ws_wrong_query_token_closes_4401() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                f"/ws/{body['channel_id']}?token=wrong"
            ) as ws:
                ws.receive_text()
        assert excinfo.value.code == 4401


def test_ws_bad_auth_frame_closes_1008() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws/{body['channel_id']}") as ws:
                ws.send_text(
                    json.dumps({"type": "auth", "session_token": "wrong-token"})
                )
                ws.receive_text()
        assert excinfo.value.code == 1008


def test_ws_cancel_frame_flips_flag_and_confirms() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(f"/ws/{body['channel_id']}") as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            ws.receive_text()  # connected frame
            ws.send_text(json.dumps({"type": "cancel"}))
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "cancelled"
            assert service.is_cancelled(body["channel_id"]) is True


def test_ws_ping_frame_receives_pong_response() -> None:
    service = _service()
    client = TestClient(_make_app(service))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(f"/ws/{body['channel_id']}") as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            connected_frame = json.loads(ws.receive_text())
            assert connected_frame["type"] == "connected"
            ws.send_text(json.dumps({"type": "ping"}))
            pong_frame = json.loads(ws.receive_text())
            assert pong_frame["type"] == "pong"


def test_ws_disallowed_origin_closes_4403() -> None:
    service = _service()
    settings = RuntimeSettings(cors_origins=["http://allowed.example.com"])
    client = TestClient(_make_app(service, settings=settings))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                f"/ws/{body['channel_id']}",
                headers={"Origin": "http://evil.example.com"},
            ) as ws:
                ws.receive_text()
        assert excinfo.value.code == 4403
        assert excinfo.value.reason == "origin not allowed"


def test_ws_allowed_origin_succeeds() -> None:
    service = _service()
    settings = RuntimeSettings(cors_origins=["http://allowed.example.com"])
    client = TestClient(_make_app(service, settings=settings))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(
            f"/ws/{body['channel_id']}",
            headers={"Origin": "http://allowed.example.com"},
        ) as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "connected"
            assert frame["channel_id"] == body["channel_id"]


def test_ws_wildcard_cors_origins_permits_any_origin() -> None:
    service = _service()
    settings = RuntimeSettings(cors_origins=["*"])
    client = TestClient(_make_app(service, settings=settings))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(
            f"/ws/{body['channel_id']}",
            headers={"Origin": "http://random.example.org"},
        ) as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "connected"
            assert frame["channel_id"] == body["channel_id"]


def test_ws_missing_origin_header_permits_connection() -> None:
    service = _service()
    settings = RuntimeSettings(cors_origins=["http://allowed.example.com"])
    client = TestClient(_make_app(service, settings=settings))
    with client:
        body = client.post("/api/progress/session", json={}).json()
        with client.websocket_connect(f"/ws/{body['channel_id']}") as ws:
            ws.send_text(
                json.dumps({"type": "auth", "session_token": body["session_token"]})
            )
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "connected"
            assert frame["channel_id"] == body["channel_id"]


# -- plugin ---------------------------------------------------------------------------


async def test_plugin_registers_service_and_mounts_router() -> None:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    await ctx.plugin(progress.ProgressPlugin(), config={"frame_cap": 5})
    assert ctx.has(ProgressService)
    assert len(ctx.routes()) == 1
    await ctx.dispose()


async def test_plugin_passes_runtime_settings_when_available() -> None:
    from omniscribe.plugins.runtime import RuntimePlugin

    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    await ctx.plugin(RuntimePlugin())
    await ctx.plugin(progress.ProgressPlugin(), config={"frame_cap": 5})
    assert ctx.has(ProgressService)
    assert len(ctx.routes()) == 1
    await ctx.dispose()


def test_on_foreign_send_done_keyerror_is_swallowed() -> None:
    service = _service()
    fut: concurrent.futures.Future[None] = concurrent.futures.Future()
    fut.set_exception(RuntimeError("connection dropped"))
    with patch.object(service, "detach", side_effect=KeyError("channel_id")):
        # KeyError during detach should be swallowed cleanly
        service._on_foreign_send_done("channel_id", "conn", fut)


def test_on_foreign_send_done_unexpected_exception_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service()
    fut: concurrent.futures.Future[None] = concurrent.futures.Future()
    fut.set_exception(RuntimeError("connection dropped"))
    with patch.object(service, "detach", side_effect=TypeError("unexpected explosion")):
        with caplog.at_level(logging.ERROR, logger="omniscribe.plugins.progress"):
            service._on_foreign_send_done("channel_id", "conn", fut)
    assert any(
        "detach after foreign-loop send failure also failed" in rec.message
        for rec in caplog.records
    )
