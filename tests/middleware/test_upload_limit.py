"""Tests for ASGI upload size limiting middleware (Wave 14: API, Middleware & Security Hardening)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from omniscribe.middleware.upload_limit import (
    UploadSizeLimitMiddleware,
)

# ---------------------------------------------------------------------------
# Scope helper
# ---------------------------------------------------------------------------


def _scope(
    path: str = "/api/process",
    method: str = "POST",
    scope_type: str = "http",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    return {
        "type": scope_type,
        "method": method,
        "path": path,
        "headers": headers or [],
    }


# ---------------------------------------------------------------------------
# ASGI Test Driver & Recorder
# ---------------------------------------------------------------------------


class _CallRecorder:
    def __init__(self, incoming_chunks: list[bytes] | None = None) -> None:
        self.upstream_called = False
        self.sent_start: dict[str, Any] | None = None
        self.sent_bodies: list[bytes] = []
        self.received_chunks: list[bytes] = []
        self._chunks = list(incoming_chunks or [b""])
        self._chunk_idx = 0

    async def downstream(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.upstream_called = True
        while True:
            msg = await receive()
            if msg.get("type") == "http.disconnect":
                break
            body = msg.get("body", b"")
            self.received_chunks.append(body)
            if not msg.get("more_body", False):
                break

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"status":"ok"}',
            }
        )

    async def receive(self) -> dict[str, Any]:
        if self._chunk_idx < len(self._chunks):
            chunk = self._chunks[self._chunk_idx]
            self._chunk_idx += 1
            more = self._chunk_idx < len(self._chunks)
            return {"type": "http.request", "body": chunk, "more_body": more}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.sent_start = message
        elif message["type"] == "http.response.body":
            self.sent_bodies.append(message.get("body", b""))


async def _drive(
    middleware: UploadSizeLimitMiddleware,
    recorder: _CallRecorder,
    scope: dict[str, Any],
) -> _CallRecorder:
    recorder.upstream_called = False
    recorder.sent_start = None
    recorder.sent_bodies = []
    await middleware(scope, recorder.receive, recorder.send)
    return recorder


# ---------------------------------------------------------------------------
# Content-Length check tests
# ---------------------------------------------------------------------------


async def test_content_length_under_limit_passes_through() -> None:
    recorder = _CallRecorder(incoming_chunks=[b"small payload"])
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"13")]
    rec = await _drive(middleware, recorder, _scope(headers=headers))

    assert rec.upstream_called is True
    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 200
    assert b"".join(rec.sent_bodies) == b'{"status":"ok"}'


async def test_content_length_exact_limit_passes_through() -> None:
    recorder = _CallRecorder(incoming_chunks=[b"x" * 100])
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"100")]
    rec = await _drive(middleware, recorder, _scope(headers=headers))

    assert rec.upstream_called is True
    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 200


async def test_content_length_exceeding_limit_returns_413_immediately() -> None:
    recorder = _CallRecorder(incoming_chunks=[b"oversized data"])
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"101")]
    rec = await _drive(middleware, recorder, _scope(headers=headers))

    assert rec.upstream_called is False
    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 413

    resp_headers = dict(rec.sent_start["headers"])
    assert resp_headers[b"content-type"] == b"application/json"

    body = json.loads(b"".join(rec.sent_bodies).decode("utf-8"))
    assert body == {
        "error": "payload_too_large",
        "detail": "Request body exceeds maximum allowed size of 100 bytes",
    }


async def test_invalid_content_length_header_falls_back_to_streaming() -> None:
    # Malformed Content-Length is ignored in header check, but streaming catches size
    recorder = _CallRecorder(incoming_chunks=[b"x" * 150])
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"not-a-number")]
    rec = await _drive(middleware, recorder, _scope(headers=headers))

    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 413


# ---------------------------------------------------------------------------
# Streaming accumulation tests
# ---------------------------------------------------------------------------


async def test_streaming_accumulation_under_limit() -> None:
    # 3 chunks of 30 bytes = 90 bytes (limit 100)
    chunks = [b"a" * 30, b"b" * 30, b"c" * 30]
    recorder = _CallRecorder(incoming_chunks=chunks)
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    rec = await _drive(middleware, recorder, _scope())

    assert rec.upstream_called is True
    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 200
    assert len(rec.received_chunks) == 3


async def test_streaming_accumulation_exceeds_limit() -> None:
    # Chunk 1: 60 bytes (ok), Chunk 2: 60 bytes -> 120 total > 100 -> 413
    chunks = [b"a" * 60, b"b" * 60]
    recorder = _CallRecorder(incoming_chunks=chunks)
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    rec = await _drive(middleware, recorder, _scope())

    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 413

    body = json.loads(b"".join(rec.sent_bodies).decode("utf-8"))
    assert body == {
        "error": "payload_too_large",
        "detail": "Request body exceeds maximum allowed size of 100 bytes",
    }


async def test_streaming_accumulation_when_content_length_lied() -> None:
    # Client sent Content-Length: 50, but actually streams 150 bytes
    chunks = [b"a" * 50, b"b" * 60]
    recorder = _CallRecorder(incoming_chunks=chunks)
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"50")]
    rec = await _drive(middleware, recorder, _scope(headers=headers))

    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 413

    body = json.loads(b"".join(rec.sent_bodies).decode("utf-8"))
    assert body["error"] == "payload_too_large"


# ---------------------------------------------------------------------------
# Method and Scope exemptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
async def test_exempt_methods_ignore_large_content_length(method: str) -> None:
    recorder = _CallRecorder(incoming_chunks=[b""])
    middleware = UploadSizeLimitMiddleware(recorder.downstream, max_bytes=100)

    headers = [(b"content-length", b"99999999")]
    rec = await _drive(middleware, recorder, _scope(method=method, headers=headers))

    assert rec.upstream_called is True
    assert rec.sent_start is not None
    assert rec.sent_start["status"] == 200


async def test_non_http_scope_passed_through() -> None:
    called = False

    async def app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    middleware = UploadSizeLimitMiddleware(app, max_bytes=100)
    recorder = _CallRecorder()
    await middleware({"type": "websocket"}, recorder.receive, recorder.send)

    assert called is True


# ---------------------------------------------------------------------------
# FastAPI / TestClient integration
# ---------------------------------------------------------------------------


def test_fastapi_upload_limit_integration() -> None:
    app = FastAPI()
    app.add_middleware(UploadSizeLimitMiddleware, max_bytes=200)

    @app.post("/upload")
    async def upload_endpoint(request: Request) -> dict[str, Any]:
        data = await request.body()
        return {"received": len(data)}

    @app.get("/upload")
    async def get_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)

    # 1. Under limit
    res = client.post("/upload", content=b"a" * 150)
    assert res.status_code == 200
    assert res.json() == {"received": 150}

    # 2. Over limit via Content-Length
    res_large = client.post("/upload", content=b"a" * 300)
    assert res_large.status_code == 413
    assert res_large.json() == {
        "error": "payload_too_large",
        "detail": "Request body exceeds maximum allowed size of 200 bytes",
    }

    # 3. GET request exempt
    res_get = client.get("/upload", headers={"content-length": "5000"})
    assert res_get.status_code == 200
    assert res_get.json() == {"status": "ok"}
