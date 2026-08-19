"""Comprehensive unit tests for security middleware components.

Covers:
- RateLimitMiddleware: sliding window, 429 status, LRU eviction on MAX_TRACKED_IPS,
  trusted proxy XFF parsing, WebSocket and non-HTTP handling.
- BearerAuthMiddleware: global and subsystem tokens, route precedence, health probe
  exemptions, path normalization, and homoglyph/non-ASCII rejection.
- MaxUploadSizeMiddleware: Content-Length fast path, chunked accumulation, deadline
  timeout, and non-HTTP pass-through.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
from collections import OrderedDict
from typing import Any

from omniscribe.api.services.security_middleware import (
    BearerAuthMiddleware,
    MaxUploadSizeMiddleware,
    RateLimitMiddleware,
)

# ---------------------------------------------------------------------------
# Test Helpers & ASGI Stubs
# ---------------------------------------------------------------------------


class _RecordingApp:
    """ASGI app that records invocations, drains request body, and returns a 200 response."""

    def __init__(self, status: int = 200, body: bytes = b"ok") -> None:
        self.called = False
        self.last_scope: dict[str, Any] | None = None
        self.status = status
        self.body = body

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.called = True
        self.last_scope = scope
        if scope.get("type") == "http":
            while True:
                msg = await receive()
                if msg.get("type") != "http.request":
                    break
                if not msg.get("more_body", False):
                    break
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status,
                    "headers": [
                        (b"content-type", b"text/plain"),
                        (b"content-length", str(len(self.body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": self.body,
                    "more_body": False,
                }
            )


class _CaptureSend:
    """Captures ASGI send events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.status: int | None = None
        self.headers: list[tuple[bytes, bytes]] = []
        self.body: bytes = b""

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        if event.get("type") == "http.response.start":
            self.status = event.get("status")
            self.headers = event.get("headers", [])
        elif event.get("type") == "http.response.body":
            self.body += event.get("body", b"")

    @property
    def json_body(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8")) if self.body else {}


async def _empty_receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _http_scope(
    path: str = "/",
    client_ip: str = "127.0.0.1",
    headers: list[tuple[bytes, bytes]] | None = None,
    raw_path: bytes | None = None,
    scope_type: str = "http",
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": scope_type,
        "method": "GET",
        "path": path,
        "client": (client_ip, 12345),
        "headers": headers or [],
    }
    if raw_path is not None:
        scope["raw_path"] = raw_path
    return scope


# ---------------------------------------------------------------------------
# RateLimitMiddleware Tests
# ---------------------------------------------------------------------------


class _FakeClock:
    """Controllable clock for deterministic rate limiter testing."""

    def __init__(self, initial: float = 1000.0) -> None:
        self._time = initial

    def __call__(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


def test_rate_limit_allows_under_cap():
    """Requests under per_minute succeed."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=3, clock=clock)

    for _ in range(3):
        send = _CaptureSend()
        asyncio.run(
            middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send)
        )
        assert send.status == 200
        assert app.called is True


def test_rate_limit_rejects_with_429_when_cap_exceeded():
    """Request exceeding per_minute receives 429 and error envelope."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=2, clock=clock)

    # 2 requests succeed
    for _ in range(2):
        send = _CaptureSend()
        asyncio.run(
            middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send)
        )
        assert send.status == 200

    # 3rd request rejected
    app.called = False
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send))
    assert send.status == 429
    assert send.json_body == {"error": "Rate limit exceeded"}
    assert app.called is False


def test_rate_limit_sliding_window_eviction():
    """Advancing clock beyond WINDOW_SECONDS allows new requests."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=2, clock=clock)

    # Hit cap at t=1000
    for _ in range(2):
        send = _CaptureSend()
        asyncio.run(
            middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send)
        )
        assert send.status == 200

    # 3rd fails at t=1000
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send))
    assert send.status == 429

    # Advance clock by 61 seconds (past 60s window)
    clock.advance(61.0)

    # Now request succeeds again
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope(client_ip="192.168.1.1"), _empty_receive, send))
    assert send.status == 200


def test_rate_limit_uses_ordered_dict():
    """self._hits is an instance of collections.OrderedDict."""
    middleware = RateLimitMiddleware(app=_RecordingApp(), per_minute=10)
    assert isinstance(middleware._hits, OrderedDict)


def test_rate_limit_lru_eviction_when_max_tracked_ips_exceeded():
    """When MAX_TRACKED_IPS is exceeded, the least recently used IP is evicted."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=10, clock=clock)

    # Set capacity to 3 for testing
    middleware.MAX_TRACKED_IPS = 3

    # Add 3 IPs in order: IP1, IP2, IP3
    for ip in ["10.0.0.1", "10.0.0.2", "10.0.0.3"]:
        send = _CaptureSend()
        asyncio.run(middleware(_http_scope(client_ip=ip), _empty_receive, send))
        assert send.status == 200

    assert list(middleware._hits.keys()) == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    # Re-access IP1 -> moves to end (MRU): order is now IP2, IP3, IP1
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope(client_ip="10.0.0.1"), _empty_receive, send))
    assert list(middleware._hits.keys()) == ["10.0.0.2", "10.0.0.3", "10.0.0.1"]

    # Add 4th IP (IP4) -> exceeds MAX_TRACKED_IPS (3). IP2 (LRU) is evicted!
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope(client_ip="10.0.0.4"), _empty_receive, send))
    assert send.status == 200

    assert len(middleware._hits) == 3
    assert "10.0.0.2" not in middleware._hits
    assert list(middleware._hits.keys()) == ["10.0.0.3", "10.0.0.1", "10.0.0.4"]


def test_rate_limit_sweeps_stale_entries_first():
    """Stale entries (older than cutoff) are swept before LRU popping."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=10, clock=clock)
    middleware.MAX_TRACKED_IPS = 2

    # IP1 at t=1000
    asyncio.run(
        middleware(_http_scope(client_ip="10.0.0.1"), _empty_receive, _CaptureSend())
    )
    # IP2 at t=1000
    asyncio.run(
        middleware(_http_scope(client_ip="10.0.0.2"), _empty_receive, _CaptureSend())
    )

    # Advance clock by 65 seconds so IP1 and IP2 become stale
    clock.advance(65.0)

    # Request from IP3 -> IP1 and IP2 are stale and swept away
    asyncio.run(
        middleware(_http_scope(client_ip="10.0.0.3"), _empty_receive, _CaptureSend())
    )

    assert "10.0.0.3" in middleware._hits
    assert "10.0.0.1" not in middleware._hits
    assert "10.0.0.2" not in middleware._hits


def test_rate_limit_websocket_upgrade_is_rate_limited():
    """WebSocket requests (scope type == 'websocket') are rate-limited."""
    clock = _FakeClock(1000.0)
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=1, clock=clock)

    ws_scope = _http_scope(client_ip="10.0.0.1", scope_type="websocket")

    # 1st WS request succeeds
    send = _CaptureSend()
    asyncio.run(middleware(ws_scope, _empty_receive, send))
    assert app.called is True

    # 2nd WS request rejected
    app.called = False
    send = _CaptureSend()
    asyncio.run(middleware(ws_scope, _empty_receive, send))
    assert send.status == 429
    assert app.called is False


def test_rate_limit_lifespan_passes_untracked():
    """Lifespan events pass through without hitting the rate limiter."""
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=1)

    lifespan_scope = {"type": "lifespan"}
    send = _CaptureSend()
    asyncio.run(middleware(lifespan_scope, _empty_receive, send))
    assert app.called is True
    assert len(middleware._hits) == 0


def test_rate_limit_xff_trusted_proxy():
    """X-Forwarded-For is parsed correctly with trusted proxies."""
    trusted = [ipaddress.ip_network("127.0.0.1/32")]
    app = _RecordingApp()
    middleware = RateLimitMiddleware(app=app, per_minute=2, trusted_proxies=trusted)

    # Request from trusted peer (127.0.0.1) with XFF "203.0.113.195"
    scope = _http_scope(
        client_ip="127.0.0.1",
        headers=[(b"x-forwarded-for", b"203.0.113.195")],
    )
    asyncio.run(middleware(scope, _empty_receive, _CaptureSend()))
    assert "203.0.113.195" in middleware._hits
    assert "127.0.0.1" not in middleware._hits

    # Request from untrusted peer (198.51.100.1) with spoofed XFF "203.0.113.195"
    untrusted_scope = _http_scope(
        client_ip="198.51.100.1",
        headers=[(b"x-forwarded-for", b"203.0.113.195")],
    )
    asyncio.run(middleware(untrusted_scope, _empty_receive, _CaptureSend()))
    assert "198.51.100.1" in middleware._hits


# ---------------------------------------------------------------------------
# BearerAuthMiddleware Tests
# ---------------------------------------------------------------------------


def test_bearer_auth_no_tokens_open_access():
    """When no tokens are set, all routes pass through."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token=None)

    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/process"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_bearer_auth_global_token_validation():
    """Global token allows matching Bearer header and rejects missing/invalid."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="secret-global")

    # Missing auth header -> 401
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/some-route"), _empty_receive, send))
    assert send.status == 401
    assert send.json_body == {"error": "Unauthorized"}

    # Invalid token -> 401
    send = _CaptureSend()
    scope_bad = _http_scope(
        "/api/some-route",
        headers=[(b"authorization", b"Bearer wrong-token")],
    )
    asyncio.run(middleware(scope_bad, _empty_receive, send))
    assert send.status == 401

    # Valid token -> 200
    send = _CaptureSend()
    scope_good = _http_scope(
        "/api/some-route",
        headers=[(b"authorization", b"Bearer secret-global")],
    )
    asyncio.run(middleware(scope_good, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_bearer_auth_subsystem_tokens_precedence():
    """Subsystem tokens override global token on their respective route namespaces."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app,
        expected_token="global-token",
        ocr_token="ocr-secret",
        translation_token="trans-secret",
        transcription_token="audio-secret",
    )

    # OCR route: ocr-secret works, global-token fails
    scope_ocr_global = _http_scope(
        "/api/process",
        headers=[(b"authorization", b"Bearer global-token")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope_ocr_global, _empty_receive, send))
    assert send.status == 401

    scope_ocr_correct = _http_scope(
        "/api/process",
        headers=[(b"authorization", b"Bearer ocr-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope_ocr_correct, _empty_receive, send))
    assert send.status == 200

    # Translation route: trans-secret works
    scope_trans = _http_scope(
        "/api/translate",
        headers=[(b"authorization", b"Bearer trans-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope_trans, _empty_receive, send))
    assert send.status == 200

    # Transcription route: audio-secret works
    scope_audio = _http_scope(
        "/api/transcribe",
        headers=[(b"authorization", b"Bearer audio-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope_audio, _empty_receive, send))
    assert send.status == 200


def test_bearer_auth_health_endpoints_exempt():
    """Health and readiness probe paths are exempt from authentication."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="strict-token")

    for path in ["/health", "/healthz", "/ready", "/readyz"]:
        send = _CaptureSend()
        asyncio.run(middleware(_http_scope(path), _empty_receive, send))
        assert send.status == 200, f"probe {path} should be exempt"


def test_bearer_auth_invalid_path_returns_400():
    """Non-ASCII characters or homoglyphs in path return 400."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="token")

    # Path containing Cyrillic 'а' (\u0430)
    scope = _http_scope(path="/api/\u0430pi/process")
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 400
    assert send.json_body == {"error": "Invalid path"}


# ---------------------------------------------------------------------------
# MaxUploadSizeMiddleware Tests
# ---------------------------------------------------------------------------


def test_max_upload_content_length_under_cap_passes():
    """Request with Content-Length under max_bytes passes through."""
    app = _RecordingApp()
    middleware = MaxUploadSizeMiddleware(app=app, max_bytes=1024)

    scope = _http_scope(
        "/upload",
        headers=[(b"content-length", b"500")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_max_upload_content_length_over_cap_returns_413():
    """Request with Content-Length exceeding max_bytes returns 413 envelope."""
    app = _RecordingApp()
    middleware = MaxUploadSizeMiddleware(app=app, max_bytes=1024)

    scope = _http_scope(
        "/upload",
        headers=[(b"content-length", b"2048")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 413
    assert send.json_body["error"] == "Upload exceeds maximum size"
    assert send.json_body["limit_bytes"] == "1024"
    assert app.called is False


def test_max_upload_chunked_accumulation():
    """Chunked request accumulating more than max_bytes returns 413."""
    app = _RecordingApp()
    middleware = MaxUploadSizeMiddleware(app=app, max_bytes=100)

    chunks = [b"a" * 60, b"b" * 60]  # 120 bytes total > 100 bytes
    chunk_iter = iter(chunks)

    async def _chunked_receive():
        try:
            chunk = next(chunk_iter)
            return {"type": "http.request", "body": chunk, "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    scope = _http_scope("/upload", headers=[])
    send = _CaptureSend()
    asyncio.run(middleware(scope, _chunked_receive, send))
    assert send.status == 413
    assert send.json_body["error"] == "Upload exceeds maximum size"


def test_max_upload_chunked_deadline_exceeded():
    """Chunked request exceeding deadline_s returns 408 Request Timeout."""
    app = _RecordingApp()
    # 0.01 second deadline
    middleware = MaxUploadSizeMiddleware(app=app, max_bytes=10000, deadline_s=0.01)

    async def _slow_receive():
        await asyncio.sleep(0.02)
        return {"type": "http.request", "body": b"chunk", "more_body": True}

    scope = _http_scope("/upload", headers=[])
    send = _CaptureSend()
    asyncio.run(middleware(scope, _slow_receive, send))
    assert send.status == 408
    assert send.json_body["error"] == "Upload deadline exceeded"
