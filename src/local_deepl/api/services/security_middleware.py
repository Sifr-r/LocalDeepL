"""
ASGI middleware that enforces the guards in `SecuritySettings`.

Two thin middlewares are exposed:

  * :class:`BearerAuthMiddleware` — when ``auth_token`` is set, rejects
    every HTTP request whose ``Authorization: Bearer <token>`` header
    does not match (constant-time compare). WebSocket traffic is passed
    through; channel-level token binding is enforced separately inside
    ``api/routers/websocket.py``.

  * :class:`MaxUploadSizeMiddleware` — rejects HTTP requests whose
    ``Content-Length`` exceeds the configured cap. Rejection is
    performed *before* any body is read, so the server never even
    attempts to buffer an oversized upload.

  * :class:`RateLimitMiddleware` — per-IP token bucket with a 60s
    sliding window. In-memory and process-local; behind uvicorn workers
    the effective cap is ``per_minute * workers``. Suitable for
    personal / single-process deployments; a multi-worker deployment
    needs a shared store and that's out of scope here.

The middlewares are deliberately small. They sit at the ASGI layer so
they run *before* FastAPI's routing logic — no per-router boilerplate.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import deque
from typing import Final

_LOGGER = logging.getLogger(__name__)

_UNAUTHORIZED: Final[dict[str, str]] = {"error": "Unauthorized"}
_TOO_LARGE: Final[dict[str, str]] = {"error": "Upload exceeds maximum size"}
_TOO_MANY_REQUESTS: Final[dict[str, str]] = {"error": "Rate limit exceeded"}


async def _send_json(
    scope, receive, send, payload: dict[str, str], status: int
) -> None:
    """Send a small JSON error response via raw ASGI (no FastAPI import)."""
    body = (str(payload).replace("'", '"')).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class BearerAuthMiddleware:
    """Reject any HTTP request whose bearer token doesn't match."""

    def __init__(self, app, expected_token: str | None) -> None:
        self.app = app
        self.expected_token = (
            expected_token.strip()
            if expected_token and expected_token.strip()
            else None
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self.expected_token is None:
            await self.app(scope, receive, send)
            return

        supplied: str | None = None
        for name, value in scope.get("headers", ()):
            if name == b"authorization":
                try:
                    supplied = value.decode("latin-1").strip()
                except UnicodeDecodeError:
                    supplied = None
                break

        if not supplied:
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return
        scheme, _, token = supplied.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return
        if not secrets.compare_digest(token.strip(), self.expected_token):
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return

        await self.app(scope, receive, send)


class MaxUploadSizeMiddleware:
    """Reject HTTP requests with a Content-Length over the configured cap.

    Only ``Content-Length`` is consulted; chunked uploads without a
    length header bypass this. Pair with a body-size ``Request`` check
    for full coverage when that matters.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    length = int(value.decode("ascii"))
                except (UnicodeDecodeError, ValueError):
                    break
                if length > self.max_bytes:
                    await _send_json(
                        scope,
                        receive,
                        send,
                        {
                            **_TOO_LARGE,
                            "limit_bytes": str(self.max_bytes),
                        },
                        413,
                    )
                    return
                break

        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Per-IP fixed-window rate limiter; in-memory and process-local.

    Each request from a given client IP appends a timestamp to a deque;
    before forwarding the request we evict entries older than 60s and
    reject if the deque is at capacity. Suitable for soft abuse
    protection on a single-worker server; not a substitute for a proper
    edge gateway.
    """

    WINDOW_SECONDS: Final[float] = 60.0

    def __init__(self, app, per_minute: int, clock=time.monotonic) -> None:
        self.app = app
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _client_key(self, scope) -> str:
        client = scope.get("client")
        if client is None:
            return "unknown"
        # `scope["client"]` is a tuple[str, int] (host, port) per ASGI; we
        # only care about the IP, and the value is untyped at our layer.
        return str(client[0])

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self._client_key(scope)
        now = self.clock()
        cutoff = now - self.WINDOW_SECONDS
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.per_minute:
            await _send_json(scope, receive, send, _TOO_MANY_REQUESTS, 429)
            return
        hits.append(now)
        await self.app(scope, receive, send)
