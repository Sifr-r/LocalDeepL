"""
ASGI middleware that enforces the guards in `SecuritySettings`.

Two thin middlewares are exposed:

  * :class:`BearerAuthMiddleware` — when one or more auth tokens are
    set, rejects every HTTP request whose ``Authorization: Bearer
    <token>`` header does not match. Three independent tokens are
    supported, with per-route precedence:

      * ``expected_token`` (global) applies to every route.
      * ``ocr_token`` overrides the global token for OCR routes
        (``/api/process``, ``/api/models/ocr``, ``/api/config/ocr``).
        When set, the global token does NOT unlock those routes.
      * ``translation_token`` overrides the global token for
        translation routes (``/api/translate``, ``/api/extract``,
        ``/api/export``, ``/api/glossary``, ``/api/models/translation``,
        ``/api/config/translation``). When set, the global token does
        NOT unlock those routes.

    WebSocket traffic is passed through; channel-level token binding
    is enforced separately inside ``api/routers/websocket.py``.

  * :class:`MaxUploadSizeMiddleware` — rejects HTTP requests whose
    body exceeds the configured cap. Two complementary paths guard
    uploads: the ``Content-Length`` fast path (rejects before reading
    any body) and the chunked path (accumulates bytes forwarded via
    ``receive`` and 413s once the cumulative size exceeds the cap).
    On rejection the middleware returns a 413 envelope
    (``error`` / ``limit_bytes`` / ``limit_bytes_mb`` / ``hint``).

  * :class:`RateLimitMiddleware` — per-IP token bucket with a 60s
    sliding window. In-memory and process-local; behind uvicorn workers
    the effective cap is ``per_minute * workers``. Suitable for
    personal / single-process deployments; a multi-worker deployment
    needs a shared store and that's out of scope here.

The middlewares are deliberately small. They sit at the ASGI layer so
they run *before* FastAPI's routing logic — no per-router boilerplate.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import posixpath
import secrets
import time
import urllib.parse
from collections import deque
from typing import Any, Final, TypedDict

_LOGGER = logging.getLogger(__name__)

_UNAUTHORIZED: Final[dict[str, str]] = {"error": "Unauthorized"}
_INVALID_PATH: Final[dict[str, str]] = {"error": "Invalid path"}
_TOO_LARGE: Final[dict[str, str]] = {"error": "Upload exceeds maximum size"}
_TOO_MANY_REQUESTS: Final[dict[str, str]] = {"error": "Rate limit exceeded"}


class _UploadGuard(TypedDict):
    total: int
    envelope: dict[str, str] | None
    status: int | None


async def _send_json(
    scope, receive, send, payload: dict[str, str], status: int
) -> None:
    """Send a small JSON error response via raw ASGI (no FastAPI import)."""
    body = json.dumps(payload).encode("utf-8")
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


def _normalize_token(value: str | None) -> str | None:
    """Strip whitespace; treat empty/whitespace-only as ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_path(scope: dict[str, Any]) -> str:
    """Return a canonical, safe path for route classification.

    Starlette URL-decodes ``scope["path"]`` for the common case, but
    leaves reserved characters (e.g. ``%2F`` for ``/``) intact because
    decoding them would change the path structure. ``scope["raw_path"]``
    carries the undecoded wire bytes when the ASGI server provides them.

    We percent-decode the raw bytes once more with ``errors="replace"``
    so any remaining ``%2F`` is collapsed, then run
    :func:`posixpath.normpath` to fold ``..`` segments. The result is the
    canonical path the route allowlist should match against — a request
    for ``/api/process%2F/../models/ocr`` is reclassified to OCR after
    collapsing, instead of falling through to the global token bucket.

    Any path containing a non-ASCII character (a Cyrillic
    homoglyph standing in for ``a`` in ``/api/process``, UTF-8
    replacement chars, raw 8-bit bytes that Starlette did not decode,
    etc.) is rejected by returning ``""``. The caller turns that into
    a 400 before the token compare so a homoglyph cannot be used to
    escape the per-route grouping.
    """
    raw_path = scope.get("raw_path")
    if isinstance(raw_path, (bytes, bytearray)) and raw_path:
        try:
            candidate = bytes(raw_path).decode("utf-8", errors="replace")
        except (AttributeError, UnicodeDecodeError):
            return ""
    else:
        candidate = str(scope.get("path", ""))

    candidate = urllib.parse.unquote(candidate, errors="replace")

    if any(ord(ch) > 127 for ch in candidate):
        return ""

    collapsed = posixpath.normpath(candidate)
    if not collapsed or collapsed == ".":
        return "/"
    return collapsed


def _is_ocr_route(path: str) -> bool:
    """Return True when ``path`` is an OCR route namespace."""
    if path == "/api/process" or path.startswith("/api/process/"):
        return True
    return bool(
        path == "/api/models/ocr"
        or path.startswith("/api/models/ocr/")
        or path == "/api/config/ocr"
        or path.startswith("/api/config/ocr/")
    )


def _is_translation_route(path: str) -> bool:
    """Return True when ``path`` is a translation route namespace."""
    if path == "/api/translate" or path.startswith("/api/translate/"):
        return True
    if path == "/api/models/translation" or path.startswith("/api/models/translation/"):
        return True
    if path == "/api/config/translation" or path.startswith("/api/config/translation/"):
        return True
    return bool(
        path == "/api/extract"
        or path.startswith("/api/extract/")
        or path == "/api/export"
        or path.startswith("/api/export/")
        or path == "/api/glossary"
        or path.startswith("/api/glossary/")
    )


def _is_transcription_route(path: str) -> bool:
    """Return True when ``path`` is a transcription route namespace."""
    if path == "/api/transcribe" or path.startswith("/api/transcribe/"):
        return True
    return bool(
        path == "/api/models/transcription"
        or path.startswith("/api/models/transcription/")
        or path == "/api/config/transcription"
        or path.startswith("/api/config/transcription/")
    )


_HEALTH_PATHS: Final[frozenset[str]] = frozenset(
    {"/health", "/healthz", "/ready", "/readyz"}
)


def _is_health_path(path: str) -> bool:
    """Return True when ``path`` is a health/readiness probe.

    Orchestrators must always be able to probe the server, even when a
    global bearer token is configured. The exact set is the four
    Kubernetes-flavoured aliases; we deliberately do NOT match prefix
    paths so a future ``/health/details`` route stays protected.
    """
    return path in _HEALTH_PATHS


class BearerAuthMiddleware:
    """Reject any HTTP request whose bearer token does not match.

    Constructor accepts independent tokens:

    * ``expected_token`` — global fallback; accepted on every route.
    * ``ocr_token`` — required for OCR routes; takes precedence over
      the global token on those routes.
    * ``translation_token`` — required for translation routes; takes
      precedence over the global token on those routes.
    * ``transcription_token`` — required for transcription routes; takes
      precedence over the global token on those routes.

    Whitespace-only values are normalised to ``None`` so a stray
    ``"   "`` env var does not silently lock everyone out.

    When no token is set for a route group, that group is open.
    """

    def __init__(
        self,
        app,
        expected_token: str | None,
        ocr_token: str | None = None,
        translation_token: str | None = None,
        transcription_token: str | None = None,
    ) -> None:
        self.app = app
        self.expected_token = _normalize_token(expected_token)
        self.ocr_token = _normalize_token(ocr_token)
        self.translation_token = _normalize_token(translation_token)
        self.transcription_token = _normalize_token(transcription_token)

    @staticmethod
    def route_group_for(path: str) -> str:
        """Classify an HTTP path into ``"ocr"``, ``"translation"``, ``"transcription"`` or ``"other"``.

        Used by tests to pin the per-route token mapping and by callers
        that want to know which token to attach when both a global and a
        per-service token are set. Health/probe paths return ``"health"``
        so callers can branch on them explicitly (the bearer middleware
        also short-circuits these before reaching the token lookup).
        """
        if _is_health_path(path):
            return "health"
        if _is_ocr_route(path):
            return "ocr"
        if _is_translation_route(path):
            return "translation"
        if _is_transcription_route(path):
            return "transcription"
        return "other"

    def _token_for(self, path: str) -> str | None:
        """Pick the token that applies to ``path``.

        Per-service tokens (OCR / translation / transcription) win over the global
        token when set. When only the global token is set,
        every route uses it. When neither is set, returns ``None``
        and the caller is open.
        """
        group = self.route_group_for(path)
        if group == "ocr" and self.ocr_token is not None:
            return self.ocr_token
        if group == "translation" and self.translation_token is not None:
            return self.translation_token
        if group == "transcription" and self.transcription_token is not None:
            return self.transcription_token
        return self.expected_token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        normalized = _normalize_path(scope)
        # Non-ASCII paths (homoglyphs, raw 8-bit bytes, percent-decoded
        # multibyte sequences) are rejected before the token compare so
        # they cannot be used to escape the per-route grouping.
        if not normalized:
            await _send_json(scope, receive, send, _INVALID_PATH, 400)
            return

        # Health and readiness probes must always reach the inner app so
        # the orchestrator can probe even when a global bearer token is
        # configured. The exempt set is exact (no prefix matching) so a
        # future ``/health/details`` endpoint stays protected.
        if _is_health_path(normalized):
            await self.app(scope, receive, send)
            return

        token = self._token_for(normalized)
        if token is None:
            await self.app(scope, receive, send)
            return

        supplied: str | None = None
        headers_dict = dict(scope.get("headers", ()) or ())
        auth_header = headers_dict.get(b"authorization")
        if auth_header is not None:
            try:
                supplied = auth_header.decode("latin-1").strip()
            except UnicodeDecodeError:
                supplied = None

        if not supplied:
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return
        scheme, _, candidate = supplied.partition(" ")
        if scheme.lower() != "bearer" or not candidate.strip():
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return
        if not secrets.compare_digest(candidate.strip(), token):
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return

        await self.app(scope, receive, send)


class MaxUploadSizeMiddleware:
    """Reject HTTP requests whose body exceeds the configured cap.

    Two complementary paths guard uploads:

    * ``Content-Length`` fast path: when the header is present and
      already over the cap, the middleware rejects with a 413 envelope
      before reading any body so the server never pays the buffering
      cost.
    * Chunked path: when no Content-Length is present, the middleware
      wraps the ``receive`` callable, accumulates each chunk's bytes,
      and rejects with a 413 envelope once the cumulative size exceeds
      ``max_bytes``. The downstream app still runs against the
      truncated body so its own cleanup logic sees the boundary.

    The 413 envelope is ``{"error": "Upload exceeds maximum size",
    "limit_bytes": ..., "limit_bytes_mb": ..., "hint": ...}`` so the
    Settings tab can render an operator-friendly hint.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    def _envelope(max_bytes: int) -> dict[str, str]:
        limit_mb = max_bytes // (1024 * 1024)
        return {
            **_TOO_LARGE,
            "limit_bytes": str(max_bytes),
            "limit_bytes_mb": str(limit_mb),
            "hint": (
                "Raise OMNISCRIBE_MAX_UPLOAD_MB (current cap "
                f"{limit_mb} MB) and restart the server to accept "
                "larger uploads."
            ),
        }

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: Content-Length known. Reject up front without
        # reading any body so the server never pays the buffering cost.
        for name, value in scope.get("headers", ()) or ():
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
                        self._envelope(self.max_bytes),
                        413,
                    )
                    return
                break

        # Chunked path: no Content-Length. Wrap ``receive`` so we
        # accumulate bytes and reject with 413 the moment the running
        # total crosses the cap. The downstream app still runs against
        # the truncated body so it can do its own cleanup.
        max_bytes = self.max_bytes
        guard: _UploadGuard = {
            "total": 0,
            "envelope": None,
            "status": None,
        }

        async def _guarded_receive():
            msg = await receive()
            if msg.get("type") != "http.request":
                return msg
            body = msg.get("body", b"") or b""
            if not body:
                return msg
            running_total = guard["total"] + len(body)
            guard["total"] = running_total
            if running_total > max_bytes:
                guard["envelope"] = self._envelope(max_bytes)
                guard["status"] = 413
                # Truncate this chunk so downstream reads stop.
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
            return msg

        async def _guarded_send(event):
            if (
                event.get("type") == "http.response.start"
                and guard.get("status") == 413
            ):
                envelope = guard.get("envelope") or self._envelope(max_bytes)
                envelope_body = json.dumps(envelope).encode("utf-8")
                event = {
                    **event,
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (
                            b"content-length",
                            str(len(envelope_body)).encode("ascii"),
                        ),
                    ],
                }
                await send(event)
                await send(
                    {
                        "type": "http.response.body",
                        "body": envelope_body,
                        "more_body": False,
                    }
                )
                return
            await send(event)

        await self.app(scope, _guarded_receive, _guarded_send)


class RateLimitMiddleware:
    """Per-IP fixed-window rate limiter; in-memory and process-local.

    Each request from a given client IP appends a timestamp to a deque;
    before forwarding the request we evict entries older than 60s and
    reject if the deque is at capacity. Suitable for soft abuse
    protection on a single-worker server; not a substitute for a proper
    edge gateway.

    When ``trusted_proxies`` is non-empty, the limiter consults the
    ``X-Forwarded-For`` header on requests whose ASGI peer is inside
    one of the configured CIDR ranges. Requests from untrusted peers
    never see the header (the standard "do not trust client-supplied
    headers from an untrusted source" rule).
    """

    WINDOW_SECONDS: Final[float] = 60.0
    _XFF_HEADER: Final[bytes] = b"x-forwarded-for"

    def __init__(
        self,
        app,
        per_minute: int,
        clock=time.monotonic,
        trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = None,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = (
            list(trusted_proxies) if trusted_proxies else []
        )

    @staticmethod
    def _extract_xff(scope) -> str | None:
        """Return the leftmost ``X-Forwarded-For`` entry, trimmed, or None."""
        for name, value in scope.get("headers", ()) or ():
            if name.lower() == RateLimitMiddleware._XFF_HEADER:
                try:
                    raw = value.decode("latin-1").strip()
                except (UnicodeDecodeError, AttributeError):
                    return None
                if not raw:
                    return None
                return raw.split(",", 1)[0].strip() or None
        return None

    def _client_key(self, scope) -> str:
        client = scope.get("client")
        if client is None:
            return "unknown"
        peer_ip = str(client[0])
        if not self._trusted_proxies:
            return peer_ip
        try:
            peer = ipaddress.ip_address(peer_ip)
        except ValueError:
            return peer_ip
        if not any(peer in network for network in self._trusted_proxies):
            return peer_ip
        candidate = self._extract_xff(scope)
        if candidate is None:
            return peer_ip
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return peer_ip
        return candidate

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
        # Lazily evict stale keys from other IPs to bound memory growth.
        for stale_key in [k for k, v in self._hits.items() if k != key and not v]:
            del self._hits[stale_key]
        await self.app(scope, receive, send)
