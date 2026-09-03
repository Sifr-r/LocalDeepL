"""ASGI upload size limiting middleware (Wave 14: API, Middleware & Security Hardening).

Enforces request body size limits at the ASGI boundary. Requests with an incoming
``Content-Length`` header exceeding ``max_bytes`` are rejected immediately with HTTP 413.
For streaming or chunked transfers (or requests omitting Content-Length), the middleware
wraps the ASGI ``receive()`` callable to accumulate incoming body chunk sizes and terminates
with HTTP 413 if the cumulative payload exceeds ``max_bytes``.

HTTP methods exempt from body limits:
    ``GET``, ``HEAD``, ``OPTIONS`` (CORS preflight).

When the limit is exceeded, returns HTTP 413 JSONResponse:
    ``{"error": "payload_too_large", "detail": f"Request body exceeds maximum allowed size of {max_bytes} bytes"}``
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("omniscribe.middleware.upload_limit")

#: Default maximum upload size in bytes (100 MB).
DEFAULT_MAX_BYTES: int = 100 * 1024 * 1024

#: HTTP methods exempt from upload size checking.
EXEMPT_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

#: ASGI 3.0 type aliases.
ASGIScope = dict[str, Any]
ASGIRecv = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]


async def _send_payload_too_large(send: ASGISend, max_bytes: int) -> None:
    """Send an HTTP 413 Payload Too Large JSON response via ASGI send."""
    body = json.dumps(
        {
            "error": "payload_too_large",
            "detail": f"Request body exceeds maximum allowed size of {max_bytes} bytes",
        }
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("latin-1")),
    ]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class UploadSizeLimitMiddleware:
    """ASGI 3.0 middleware that enforces maximum request body sizes.

    Inspects the ``Content-Length`` header early to fail fast before buffering.
    Also wraps the ``receive`` callable to monitor cumulative received bytes during
    streaming/chunked transfers.

    Usage:
        web_app.add_middleware(UploadSizeLimitMiddleware, max_bytes=100 * 1024 * 1024)
    """

    def __init__(
        self,
        app: Any,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._app = app
        self._max_bytes = max(1, int(max_bytes))

    @property
    def max_bytes(self) -> int:
        """The maximum allowed upload size in bytes."""
        return self._max_bytes

    async def __call__(
        self, scope: ASGIScope, receive: ASGIRecv, send: ASGISend
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        if method in EXEMPT_METHODS:
            await self._app(scope, receive, send)
            return

        # 1. Early Content-Length header check
        content_length: int | None = None
        headers: list[tuple[bytes, bytes]] = list(scope.get("headers") or [])
        for raw_name, raw_value in headers:
            if raw_name.lower() == b"content-length":
                try:
                    content_length = int(raw_value.decode("latin-1").strip())
                except (ValueError, UnicodeDecodeError):
                    content_length = None
                break

        if content_length is not None and content_length > self._max_bytes:
            logger.warning(
                "upload_limit.middleware: 413 payload too large (content-length=%d > max_bytes=%d) for %s %s",
                content_length,
                self._max_bytes,
                method,
                scope.get("path", ""),
            )
            await _send_payload_too_large(send, self._max_bytes)
            return

        # 2. Streaming accumulation check
        total_bytes = 0
        limit_exceeded = False
        response_started = False

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if limit_exceeded:
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        async def wrapped_receive() -> dict[str, Any]:
            nonlocal total_bytes, limit_exceeded, response_started
            if limit_exceeded:
                return {"type": "http.disconnect", "body": b"", "more_body": False}

            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                total_bytes += len(chunk)
                if total_bytes > self._max_bytes:
                    limit_exceeded = True
                    logger.warning(
                        "upload_limit.middleware: 413 payload too large (streamed=%d > max_bytes=%d) for %s %s",
                        total_bytes,
                        self._max_bytes,
                        method,
                        scope.get("path", ""),
                    )
                    if not response_started:
                        response_started = True
                        await _send_payload_too_large(send, self._max_bytes)
                    return {"type": "http.disconnect", "body": b"", "more_body": False}
            return message

        try:
            await self._app(scope, wrapped_receive, wrapped_send)
        except Exception:
            if not limit_exceeded:
                raise


__all__ = [
    "DEFAULT_MAX_BYTES",
    "EXEMPT_METHODS",
    "UploadSizeLimitMiddleware",
]
