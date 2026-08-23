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
import contextlib
import inspect
import ipaddress
import json
import logging
from collections import OrderedDict
from typing import Any
from unittest.mock import patch

import pytest

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


# ---------------------------------------------------------------------------
# BearerAuthMiddleware — route grouping, precedence, and path hardening
# (consolidated from the former tests/test_separate_auth.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/process", "ocr"),
        ("/api/process/sync", "ocr"),
        ("/api/process/async", "ocr"),
        ("/api/models/ocr", "ocr"),
        ("/api/config/ocr", "ocr"),
        ("/api/config/ocr/auth", "ocr"),
        ("/api/translate", "translation"),
        ("/api/translate/async", "translation"),
        ("/api/translate/tree", "translation"),
        ("/api/translate/status/job-1", "translation"),
        ("/api/models/translation", "translation"),
        ("/api/config/translation", "translation"),
        ("/api/config/translation/auth", "translation"),
        ("/api/extract", "translation"),
        ("/api/export/text", "translation"),
        ("/api/export/docx", "translation"),
        ("/api/glossary", "translation"),
        ("/api/glossary/import", "translation"),
        # Unrelated endpoints fall into the global bucket.
        ("/api/config", "other"),
        ("/api/jobs", "other"),
        ("/api/models", "other"),
        ("/api/models/all", "other"),
        ("/", "other"),
    ],
)
def test_route_group_for_classifies_paths(path: str, expected: str) -> None:
    assert BearerAuthMiddleware.route_group_for(path) == expected


def test_bearer_auth_whitespace_tokens_are_noop():
    """Whitespace-only tokens (global or per-service) mean no auth at all."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="   ")
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/process"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True

    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token=None, ocr_token="   ")
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/process"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_bearer_auth_global_token_rejects_non_bearer_scheme():
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="global-secret")
    scope = _http_scope(
        "/api/process", headers=[(b"authorization", b"Basic dXNlcjpwYXNz")]
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401
    assert app.called is False


@pytest.mark.parametrize(
    ("token_kwarg", "token_value", "path"),
    [
        ("ocr_token", "ocr-secret", "/api/process"),
        ("translation_token", "translation-secret", "/api/translate"),
        ("translation_token", "translation-secret", "/api/extract"),
        ("translation_token", "translation-secret", "/api/glossary"),
    ],
)
def test_subsystem_token_unlocks_its_group_and_not_global(
    token_kwarg: str, token_value: str, path: str
) -> None:
    """The per-service token unlocks its own route group; once set, the
    global token no longer unlocks that group."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", **{token_kwarg: token_value}
    )

    send = _CaptureSend()
    scope_ok = _http_scope(
        path, headers=[(b"authorization", f"Bearer {token_value}".encode("latin-1"))]
    )
    asyncio.run(middleware(scope_ok, _empty_receive, send))
    assert send.status == 200
    assert app.called is True

    app.called = False
    send = _CaptureSend()
    scope_global = _http_scope(
        path, headers=[(b"authorization", b"Bearer global-secret")]
    )
    asyncio.run(middleware(scope_global, _empty_receive, send))
    assert send.status == 401
    assert app.called is False


def test_other_routes_use_global_token_only():
    """``/api/config`` and other shared endpoints fall back to the global
    token; per-service tokens must not unlock routes outside their group."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app,
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    send = _CaptureSend()
    scope_ok = _http_scope(
        "/api/config", headers=[(b"authorization", b"Bearer global-secret")]
    )
    asyncio.run(middleware(scope_ok, _empty_receive, send))
    assert send.status == 200
    assert app.called is True

    app.called = False
    send = _CaptureSend()
    scope_ocr = _http_scope(
        "/api/config", headers=[(b"authorization", b"Bearer ocr-secret")]
    )
    asyncio.run(middleware(scope_ocr, _empty_receive, send))
    assert send.status == 401
    assert app.called is False


def test_only_ocr_token_set_leaves_translation_routes_open():
    """Setting only an OCR token leaves translation routes open per global."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token=None, ocr_token="ocr-secret"
    )

    # OCR request rejected (no token).
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/process"), _empty_receive, send))
    assert send.status == 401
    assert app.called is False

    # Translation route is unaffected when no global or per-service token is set.
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/translate"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_middleware_handles_missing_or_empty_headers():
    """The middleware must not crash when an ASGI scope lacks ``headers``
    or carries an empty header list — both mean no auth, so 401."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token="global-secret")

    scope = _http_scope("/api/process")
    del scope["headers"]
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401

    send = _CaptureSend()
    asyncio.run(
        middleware(_http_scope("/api/process", headers=[]), _empty_receive, send)
    )
    assert send.status == 401


# --- Path-normalization hardening (audit report finding 1.5) --------------
#
# The middleware must percent-decode the request path, collapse ``..``
# segments, and reject any non-ASCII character before the route is
# classified. A request that abuses percent-encoding or traversal to
# cross the per-route token boundary must end up using the correct
# service-specific token, not the global one.


def test_percent_encoded_slash_with_traversal_classifies_as_ocr():
    """``/api/process%2F/../models/ocr`` collapses to ``/api/models/ocr``.

    Starlette leaves ``%2F`` intact in ``scope["path"]``; without
    percent-decoding, the request would slip past the OCR allowlist and
    be authed against the global token. After normalization the path
    matches the OCR group, so the global token must fail.
    """
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    wire_path = "/api/process%2F/../models/ocr"
    scope = _http_scope(
        wire_path,
        raw_path=wire_path.encode("latin-1"),
        headers=[(b"authorization", b"Bearer global-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401
    assert send.json_body == {"error": "Unauthorized"}
    assert app.called is False


def test_ocr_token_unlocks_percent_encoded_slash_with_traversal():
    """The matching OCR token unlocks the same request — full round-trip."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    wire_path = "/api/process%2F/../models/ocr"
    scope = _http_scope(
        wire_path,
        raw_path=wire_path.encode("latin-1"),
        headers=[(b"authorization", b"Bearer ocr-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_non_ascii_path_is_rejected_before_token_compare():
    """Cyrillic homoglyph ``а`` (U+0430) cannot stand in for ``a``.

    The wire form ``/%D0%B0pi/process`` is rejected with 400 Invalid path
    before any token comparison runs, so an attacker cannot use a
    homoglyph to bypass the per-route grouping.
    """
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    wire_path = "/%D0%B0pi/process"  # Cyrillic а percent-encoded as UTF-8
    scope = _http_scope(
        wire_path,
        raw_path=wire_path.encode("latin-1"),
        headers=[(b"authorization", b"Bearer global-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 400
    assert send.json_body == {"error": "Invalid path"}
    assert app.called is False


def test_non_ascii_path_rejected_even_with_no_token():
    """The 400 Invalid path response fires regardless of token config."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token=None)

    wire_path = "/%D0%B0pi/process"
    scope = _http_scope(wire_path, raw_path=wire_path.encode("latin-1"))
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 400
    assert send.json_body == {"error": "Invalid path"}
    assert app.called is False


def test_traversal_within_ocr_namespace_classifies_as_ocr():
    """``/api/config/ocr/x/y/..`` collapses to ``/api/config/ocr/x``.

    A traversal that stays inside the OCR namespace must still classify
    as OCR, so the global token does not unlock the request.
    """
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    scope = _http_scope(
        "/api/config/ocr/x/y/..",
        headers=[(b"authorization", b"Bearer global-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401
    assert send.json_body == {"error": "Unauthorized"}
    assert app.called is False


def test_traversal_collapses_to_translation_route():
    """``/api/translate/x/y/../z`` collapses inside ``/api/translate``;
    the traversal is collapsed before classification so the translation
    token (not the global) is required — and unlocks the request."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app,
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    scope = _http_scope(
        "/api/translate/x/y/../z",
        headers=[(b"authorization", b"Bearer global-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401
    assert app.called is False

    # Same request with the matching translation token — accepted.
    app.called = False
    scope = _http_scope(
        "/api/translate/x/y/../z",
        headers=[(b"authorization", b"Bearer translation-secret")],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_health_probe_bypasses_auth_with_tokens_set():
    """With both a global and per-service token configured, ``/health``
    still reaches the inner app so the orchestrator can probe the
    server. This pins the post-normalization behaviour of the
    ``_is_health_path`` short-circuit."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app,
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/health"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True


# --- F2.2 audit fix: management routes require the GLOBAL token ----------
#
# Management routes accept ONLY the global token, not per-namespace
# tokens. This prevents an OCR-token holder from switching the LLM
# provider, cancelling any job, or clearing another namespace's token
# via /api/config/{other}/auth.


@pytest.mark.parametrize(
    "path",
    [
        "/api/jobs/abc/cancel",
        "/api/providers/active",
        "/api/config/translation/auth",
    ],
)
def test_ocr_token_does_not_unlock_management_routes(path: str):
    """An OCR token must NOT unlock cross-namespace management routes."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    scope = _http_scope(path, headers=[(b"authorization", b"Bearer ocr-secret")])
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 401
    assert app.called is False


def test_global_token_unlocks_jobs_cancel_management_route():
    """The global token satisfies every protected route, including management."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app, expected_token="global-secret", ocr_token="ocr-secret"
    )

    scope = _http_scope(
        "/api/jobs/abc/cancel", headers=[(b"authorization", b"Bearer global-secret")]
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_no_token_means_management_routes_open():
    """Dev default: when no token is set, every route (including
    management) is open. The F2.2 fix removed the subsystem-token
    branch; it did not introduce a requirement that a global token be
    set. Operators who want to lock down management must set the
    global token explicitly."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(app=app, expected_token=None)

    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/jobs/abc/cancel"), _empty_receive, send))
    assert send.status == 200
    assert app.called is True


def test_management_routes_protected_when_only_subsystem_token_set():
    """D2-01 audit fix: when global token is unset but a subsystem token
    is set, management routes must require an active token rather than
    bypassing auth."""
    app = _RecordingApp()
    middleware = BearerAuthMiddleware(
        app=app,
        expected_token=None,
        ocr_token="ocr-secret-with-sufficient-length-32",
    )

    # Unauthenticated request to management route is rejected (401).
    send = _CaptureSend()
    asyncio.run(middleware(_http_scope("/api/config"), _empty_receive, send))
    assert send.status == 401
    assert app.called is False

    # Request with active subsystem token is accepted (200).
    scope = _http_scope(
        "/api/config",
        headers=[
            (
                b"authorization",
                b"Bearer ocr-secret-with-sufficient-length-32",
            )
        ],
    )
    send = _CaptureSend()
    asyncio.run(middleware(scope, _empty_receive, send))
    assert send.status == 200
    assert app.called is True


# ---------------------------------------------------------------------------
# F2.3 — per-request upload deadline
# (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_max_upload_middleware_default_deadline_is_120s() -> None:
    """The middleware default is 120s — a comfortable budget at the 100 GB cap.

    A legitimate 100 GB upload at 100 MB/s finishes in ~17 minutes, so
    2 minutes is plenty of headroom for healthy clients. A slow
    trickle attacker burns the budget in seconds.
    """
    assert MaxUploadSizeMiddleware.DEFAULT_DEADLINE_S == 120.0
    # Constructor defaults to the class constant.
    assert (
        inspect.signature(MaxUploadSizeMiddleware.__init__)
        .parameters["deadline_s"]
        .default
        == 120.0
    )


def test_max_upload_middleware_init_accepts_custom_deadline() -> None:
    """Operators can override the deadline at construction time."""

    async def _noop(scope, receive, send):
        return None

    mw = MaxUploadSizeMiddleware(_noop, max_bytes=1024, deadline_s=7.5)
    assert mw.deadline_s == 7.5


async def _drive_chunked_with_delay(
    deadline_s: float, max_bytes: int, sleep_before_chunks: float
) -> tuple[int, dict[str, Any] | None]:
    """Drive ``MaxUploadSizeMiddleware`` with chunked upload that respects the deadline.

    Sends two 1-byte chunks spaced ``sleep_before_chunks`` seconds apart;
    if the cumulative wall-clock between the two exceeds ``deadline_s``,
    the second chunk triggers the 408 envelope. Returns ``(status, body)``
    where ``status=0`` means the request passed through.

    The inner app drains the body in a loop so the second chunk is
    actually pulled through the middleware's ``_guarded_receive``
    wrapper (where the deadline check lives). Without that drain
    the inner app would return after reading the first chunk and
    the deadline test would never fire.
    """
    forwarded: dict[str, Any] = {}

    async def _forward_app(scope, receive, send):
        forwarded["called"] = True
        # Drain the (truncated) body so the chunk loop completes.
        msg = await receive()
        while msg.get("more_body"):
            msg = await receive()
        # Emit a minimal response so the send wrapper has a start event.
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    mw = MaxUploadSizeMiddleware(
        _forward_app, max_bytes=max_bytes, deadline_s=deadline_s
    )
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    captured: dict[str, Any] = {"status": 0, "body": None}

    async def _capture_send(msg):
        if msg["type"] == "http.response.start":
            captured["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                captured["body"] = json.loads(msg["body"].decode("utf-8"))

    async def _two_chunk_receive():
        # First chunk: a single byte. The middleware increments total
        # and returns the message; downstream reads 1 byte and waits
        # for the next one.
        yield {"type": "http.request", "body": b"a", "more_body": True}
        await asyncio.sleep(sleep_before_chunks)
        # Second chunk: a single byte. The middleware either returns
        # it (if the deadline hasn't expired) or truncates to b"" and
        # marks the guard as rejected with status 408.
        yield {"type": "http.request", "body": b"b", "more_body": False}

    receive_iter = _two_chunk_receive()

    async def _pull_receive():
        return await receive_iter.__anext__()

    await mw(scope, _pull_receive, _capture_send)
    return captured["status"], captured["body"]


def test_chunked_upload_under_deadline_passes_through() -> None:
    """Two fast chunks (well under the budget) flow through to the inner app."""

    async def _drive():
        return await _drive_chunked_with_delay(
            deadline_s=2.0, max_bytes=1024, sleep_before_chunks=0.0
        )

    status, body = asyncio.run(_drive())
    # No rejection: the inner app's response is forwarded verbatim.
    assert status == 200, f"unexpected status {status}: {body!r}"
    assert body is None  # inner app sent an empty 200 body, not a JSON envelope


def test_chunked_upload_over_deadline_rejects_with_408_envelope() -> None:
    """A slow trickle (gap > deadline) fires the 408 envelope."""

    async def _drive():
        # deadline=0.1s, sleep 0.3s between chunks → 408.
        return await _drive_chunked_with_delay(
            deadline_s=0.1, max_bytes=1024, sleep_before_chunks=0.3
        )

    status, body = asyncio.run(_drive())
    assert status == 408
    assert body is not None
    assert body["error"] == "Upload deadline exceeded"
    assert body["deadline_s"] == "0.1"
    assert "hint" in body


def test_chunked_upload_byte_cap_still_works_alongside_deadline() -> None:
    """The 413 byte cap and 408 deadline are complementary — either fires a clean exit."""

    async def _drive():
        forwarded: dict[str, Any] = {}

        async def _forward_app(scope, receive, send):
            forwarded["called"] = True
            # Drain the (truncated) body so the chunk loop completes.
            msg = await receive()
            while msg.get("more_body"):
                msg = await receive()
            # Emit a normal response — the middleware's guard will
            # intercept the start event and rewrite it to 413.
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        # Tiny cap (4 bytes), generous deadline (10s) — the byte cap
        # fires first, the deadline never sees the wall clock.
        mw = MaxUploadSizeMiddleware(_forward_app, max_bytes=4, deadline_s=10.0)
        scope: dict[str, Any] = {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
        captured: dict[str, Any] = {"status": 0, "body": None}

        async def _capture_send(msg):
            if msg["type"] == "http.response.start":
                captured["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                    captured["body"] = json.loads(msg["body"].decode("utf-8"))

        async def _chunked_receive():
            yield {
                "type": "http.request",
                "body": b"aaaaa",
                "more_body": False,
            }  # 5 bytes > 4 cap

        receive_iter = _chunked_receive()

        async def _pull_receive():
            return await receive_iter.__anext__()

        await mw(scope, _pull_receive, _capture_send)
        return captured["status"], captured["body"]

    status, body = asyncio.run(_drive())
    assert status == 413
    assert body is not None
    assert body["error"] == "Upload exceeds maximum size"


# ---------------------------------------------------------------------------
# F2.4 — RateLimitMiddleware applies to WebSocket scopes
# (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_rate_limit_passes_websocket_under_cap() -> None:
    """A WS upgrade under the per-IP cap is forwarded to the inner app."""
    forwarded: dict[str, Any] = {}

    class _App:
        async def __call__(self, scope, receive, send):
            forwarded["called"] = True
            forwarded["type"] = scope["type"]

    mw = RateLimitMiddleware(_App(), per_minute=5)
    scope: dict[str, Any] = {
        "type": "websocket",
        "client": ("10.0.0.1", 1234),
        "headers": [],
    }

    async def _no_receive():
        return {"type": "websocket.connect"}

    sent: list[dict[str, Any]] = []

    async def _capture_send(msg):
        sent.append(msg)

    asyncio.run(mw(scope, _no_receive, _capture_send))
    assert forwarded.get("called") is True
    assert forwarded.get("type") == "websocket"
    # No 429 emitted.
    assert not any(m.get("type") == "http.response.start" for m in sent)


def test_rate_limit_rejects_websocket_over_cap() -> None:
    """A WS upgrade over the per-IP cap is rejected with 429."""

    class _App:
        async def __call__(self, scope, receive, send):
            pass  # never reached

    mw = RateLimitMiddleware(_App(), per_minute=2)
    scope: dict[str, Any] = {
        "type": "websocket",
        "client": ("10.0.0.2", 1234),
        "headers": [],
    }

    async def _no_receive():
        return {"type": "websocket.connect"}

    sent: list[dict[str, Any]] = []

    async def _capture_send(msg):
        sent.append(msg)

    async def _drive():
        # Three upgrades; third one is over the 2/minute cap.
        for _ in range(3):
            sent.clear()
            await mw(scope, _no_receive, _capture_send)
            if sent and sent[0].get("status") == 429:
                return sent

    rejected = asyncio.run(_drive())
    assert rejected is not None, "WS upgrades were never rejected"
    assert rejected[0]["status"] == 429
    body = json.loads(rejected[1]["body"].decode("utf-8"))
    assert body == {"error": "Rate limit exceeded"}


def test_rate_limit_websocket_and_http_share_bucket() -> None:
    """The same client IP shares one bucket across HTTP and WS scopes."""

    class _App:
        async def __call__(self, scope, receive, send):
            pass

    mw = RateLimitMiddleware(_App(), per_minute=2)
    ip = ("10.0.0.3", 1234)
    http_scope: dict[str, Any] = {"type": "http", "client": ip, "headers": []}
    ws_scope: dict[str, Any] = {"type": "websocket", "client": ip, "headers": []}

    async def _no_receive():
        return {"type": "websocket.connect"}

    sent: list[dict[str, Any]] = []

    async def _capture_send(msg):
        sent.append(msg)

    async def _drive():
        # Two HTTP requests use the entire 2/minute cap.
        for _ in range(2):
            sent.clear()
            await mw(http_scope, _no_receive, _capture_send)
        # Third call (WS upgrade from the same IP) must be rejected.
        sent.clear()
        await mw(ws_scope, _no_receive, _capture_send)
        return list(sent)

    rejected = asyncio.run(_drive())
    assert rejected and rejected[0]["status"] == 429


def test_rate_limit_passes_lifespan_through() -> None:
    """Lifespan scopes still pass through — the bucket is keyed to network identity."""
    forwarded: dict[str, Any] = {}

    class _App:
        async def __call__(self, scope, receive, send):
            forwarded["called"] = True

    mw = RateLimitMiddleware(_App(), per_minute=1)
    scope: dict[str, Any] = {
        "type": "lifespan",
        "client": ("10.0.0.4", 1234),
        "headers": [],
    }

    async def _no_receive():
        return {"type": "lifespan.startup"}

    async def _no_send(msg):
        pass

    asyncio.run(mw(scope, _no_receive, _no_send))
    assert forwarded.get("called") is True


# ---------------------------------------------------------------------------
# F2.5 — _get_active_tokens logs warning on config-store read failure
# (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_get_active_tokens_logs_warning_on_config_store_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing config-store read logs a warning (with traceback) before falling back."""

    async def _noop(scope, receive, send):
        return None

    middleware = BearerAuthMiddleware(_noop, expected_token="env-fallback-token")
    # Simulate a config-store outage.
    boom = RuntimeError("simulated redis outage")
    with patch(
        "omniscribe.api.routers.config._load_config_from_store",
        side_effect=boom,
        create=True,
    ):
        with caplog.at_level(
            logging.WARNING, logger="omniscribe.api.services.security_middleware"
        ):
            tokens = middleware._get_active_tokens()

    # The env fallback is still used — the warning is non-fatal.
    assert tokens["global"] == "env-fallback-token"
    # The warning is emitted with the right shape.
    matching = [r for r in caplog.records if "config store" in r.getMessage()]
    assert matching, "expected a warning mentioning the config store failure"
    assert matching[0].levelname == "WARNING"
    # exc_info=True means the traceback is attached.
    assert matching[0].exc_info is not None
