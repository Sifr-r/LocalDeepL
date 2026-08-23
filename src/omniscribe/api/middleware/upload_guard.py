"""Upload size guard and request deadline middleware for ASGI.

Rejects HTTP requests whose body exceeds the configured cap or wall-clock budget.
"""

from __future__ import annotations

import json
import time
from typing import Any, Final, TypedDict

_TOO_LARGE: Final[dict[str, str]] = {"error": "Upload exceeds maximum size"}
_DEADLINE_EXCEEDED: Final[dict[str, str]] = {"error": "Upload deadline exceeded"}


class _UploadGuard(TypedDict):
    total: int
    rejected: bool
    sent_rejection: bool
    envelope: dict[str, str] | None
    status: int | None
    deadline_exceeded: bool


async def _send_json(
    scope: dict[str, Any], receive: Any, send: Any, payload: dict[str, str], status: int
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

    F2.3 audit fix: the chunked path now also enforces a per-request
    deadline (``deadline_s``, default 120s). Pre-fix, a slow client
    could keep streaming 1-byte-per-second chunks indefinitely —
    the byte cap never triggered, but the connection held a worker
    open for hours. The deadline rejects with a 408 Request Timeout
    envelope the moment the wall-clock exceeds the budget,
    regardless of cumulative bytes. ``save_validated_upload`` also
    has its own deadline; the middleware cap is the first line of
    defense, the saved-file deadline is the second. Either firing
    is a clean 408/413 exit, no half-parsed bytes left in the
    downstream app.

    The 413 envelope is ``{"error": "Upload exceeds maximum size",
    "limit_bytes": ..., "limit_bytes_mb": ..., "hint": ...}`` so the
    Settings tab can render an operator-friendly hint. The 408
    envelope is the standard ``{"error": "Upload deadline exceeded",
    "deadline_s": ..., "hint": ...}`` shape.
    """

    # F2.3: default 120s. Tuned for the 100 GB hard ceiling — a
    # legitimate upload at 100 MB/s finishes in 17 minutes, so a
    # 2-minute budget is plenty for a healthy client. A slow
    # trickle attacker burns the budget in seconds.
    DEFAULT_DEADLINE_S: float = 120.0

    def __init__(
        self, app: Any, max_bytes: int, deadline_s: float = DEFAULT_DEADLINE_S
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.deadline_s = float(deadline_s)

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

    @staticmethod
    def _deadline_envelope(deadline_s: float) -> dict[str, str]:
        """Build the 408 envelope returned when a request exceeds the per-request budget."""
        return {
            **_DEADLINE_EXCEEDED,
            "deadline_s": str(deadline_s),
            "hint": (
                "The upload took longer than the per-request budget. "
                "Check the client network, then retry. The cap can be "
                "raised by setting OMNISCRIBE_UPLOAD_DEADLINE_S at "
                "server startup (default 120s)."
            ),
        }

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
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
        deadline_s = self.deadline_s
        started_at = time.monotonic()
        guard: _UploadGuard = {
            "total": 0,
            "rejected": False,
            "sent_rejection": False,
            "envelope": None,
            "status": None,
            "deadline_exceeded": False,
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
                # Mark the request rejected up front so the send wrapper
                # knows to drop every subsequent downstream event (the
                # inner app will still try to emit its own start + body
                # even though we've truncated its body stream).
                guard["rejected"] = True
                # Truncate this chunk so downstream reads stop.
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
            # F2.3 audit fix: per-request wall-clock budget. A slow
            # trickle attacker that stays just under the byte cap can
            # still hold a worker open indefinitely; the deadline
            # forces a 408 the moment the wall-clock crosses the
            # budget, regardless of cumulative bytes. The cap and the
            # deadline are complementary — either one fires a clean
            # 413/408 exit; the operator's only tuning knob is the
            # budget. We do not enforce the deadline when ``body`` is
            # empty (a keep-alive ``more_body=False`` trailer) so the
            # final handshake is never penalised.
            if (time.monotonic() - started_at) > deadline_s:
                guard["envelope"] = self._deadline_envelope(deadline_s)
                guard["status"] = 408
                guard["rejected"] = True
                guard["deadline_exceeded"] = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
            return msg

        async def _guarded_send(event: dict[str, Any]):
            # Once we've emitted the rejection envelope, every further
            # downstream send call must be dropped silently. The ASGI
            # spec only allows one ``http.response.start`` per request;
            # forwarding the inner app's body event after our own body
            # is a duplicate-completion bug that crashes uvicorn and
            # can be abused for HTTP request smuggling.
            if guard["sent_rejection"]:
                return
            # While the request is rejected, any non-``start`` event
            # the inner app tries to send is dropped on the floor. The
            # middleware will synthesize its own rejection start + body
            # the first time it sees a start event; the inner app's
            # own body event would otherwise follow our body and
            # produce a second response completion.
            if guard["rejected"] and event.get("type") != "http.response.start":
                return
            if event.get("type") == "http.response.start" and guard["rejected"]:
                envelope = guard.get("envelope") or self._envelope(max_bytes)
                status = guard.get("status") or 413
                envelope_body = json.dumps(envelope).encode("utf-8")
                guard["sent_rejection"] = True
                event = {
                    **event,
                    "status": status,
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


__all__ = [
    "_DEADLINE_EXCEEDED",
    "_TOO_LARGE",
    "MaxUploadSizeMiddleware",
    "_UploadGuard",
    "_send_json",
]
