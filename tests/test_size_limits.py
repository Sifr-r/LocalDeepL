"""Size-cap contract tests.

Pins the new default upload cap (10 GB) and the absolute ceiling (100 GB):

* ``SecuritySettings.from_env()`` returns a ``max_upload_bytes`` at or above
  the documented 10 GB default and clamps any operator override to the
  100 GB hard ceiling.
* ``MaxUploadSizeMiddleware`` lets requests whose ``Content-Length`` is at
  or under the cap pass through, and returns the documented 413 envelope
  (with the ``limit_bytes`` / ``limit_bytes_mb`` / ``hint`` fields) when
  the body exceeds the cap.
* ``MAX_UPLOAD_BYTES`` in :mod:`omniscribe.api.services.uploads` matches
  the security-config default so the in-process upload validator can't
  silently fall behind the middleware cap.

The middleware exercises ASGI directly (no FastAPI boot), matching the
``test_websocket_handler.py`` pattern.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# SecuritySettings — default cap & clamping
# ---------------------------------------------------------------------------


def test_security_settings_default_is_at_least_10gb(monkeypatch: pytest.MonkeyPatch):
    """Default upload cap is at least 10 GB (10240 MB)."""
    monkeypatch.delenv("OMNISCRIBE_MAX_UPLOAD_MB", raising=False)

    from omniscribe.api.middleware.settings import (
        ABSOLUTE_MAX_UPLOAD_MB,
        DEFAULT_MAX_UPLOAD_MB,
        SecuritySettings,
    )

    assert DEFAULT_MAX_UPLOAD_MB >= 10_240, (
        "DEFAULT_MAX_UPLOAD_MB must be at least 10 GB so the size cap "
        "doesn't silently hide the file picker from local users."
    )
    assert ABSOLUTE_MAX_UPLOAD_MB >= DEFAULT_MAX_UPLOAD_MB

    settings = SecuritySettings.from_env()
    expected_bytes = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    assert settings.max_upload_bytes == expected_bytes


def test_security_settings_accepts_10gb_override(monkeypatch: pytest.MonkeyPatch):
    """An explicit 10240 MB override is honoured verbatim."""
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "10240")

    from omniscribe.api.middleware.settings import SecuritySettings

    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == 10240 * 1024 * 1024


@pytest.mark.parametrize("mb_value", [20480, 51200, 100_000])
def test_security_settings_accepts_large_overrides(
    monkeypatch: pytest.MonkeyPatch, mb_value: int
):
    """Operators can dial the cap anywhere between 10 GB and 100 GB."""
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", str(mb_value))

    from omniscribe.api.middleware.settings import SecuritySettings

    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == mb_value * 1024 * 1024


def test_security_settings_clamps_ridiculous_overrides(
    monkeypatch: pytest.MonkeyPatch,
):
    """Anything above the absolute ceiling is clamped, not honoured verbatim."""
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "99999999")

    from omniscribe.api.middleware.settings import (
        ABSOLUTE_MAX_UPLOAD_MB,
        SecuritySettings,
    )

    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == ABSOLUTE_MAX_UPLOAD_MB * 1024 * 1024


def test_security_settings_clamps_zero_and_negative(monkeypatch: pytest.MonkeyPatch):
    """Operators can't lock themselves out by setting a zero/negative cap."""
    for raw in ("0", "-5"):
        monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", raw)
        from omniscribe.api.middleware.settings import SecuritySettings

        settings = SecuritySettings.from_env()
        assert settings.max_upload_bytes >= 1024 * 1024


def test_security_settings_module_constant_matches_default():
    """``MAX_UPLOAD_BYTES`` in security.py must equal ``DEFAULT_MAX_UPLOAD_MB``.

    The in-process upload validator (``save_validated_upload``) defaults
    its cap from this constant; if it drifts behind the middleware cap,
    a request rejected by one layer can be silently accepted by the
    other.
    """
    from omniscribe.api.middleware.settings import DEFAULT_MAX_UPLOAD_MB
    from omniscribe.api.services.uploads import MAX_UPLOAD_BYTES

    assert MAX_UPLOAD_BYTES == DEFAULT_MAX_UPLOAD_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# MaxUploadSizeMiddleware — pass-through vs. rejection
# ---------------------------------------------------------------------------


async def _drive_middleware(
    max_bytes: int, content_length: str | None
) -> tuple[int, dict[str, Any] | None]:
    """Drive ``MaxUploadSizeMiddleware`` and return ``(status, body_dict)``.

    ``body_dict`` is the decoded JSON body for 413 responses, or ``None``
    when the request passes through to the downstream app.
    """
    from omniscribe.api.middleware import MaxUploadSizeMiddleware

    forwarded: dict[str, Any] = {}

    async def _forward_app(scope, receive, send):
        # Just enough ASGI to mark the request as forwarded; we don't
        # need a real response for the pass-through case.
        forwarded["called"] = True

    middleware = MaxUploadSizeMiddleware(_forward_app, max_bytes=max_bytes)

    headers: list[tuple[bytes, bytes]] = []
    if content_length is not None:
        headers.append((b"content-length", content_length.encode("ascii")))
    scope = {
        "type": "http",
        "method": "POST",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
    }

    captured: dict[str, Any] = {"status": 0, "body": None}

    async def _noop_receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _capture_send(msg):
        if msg["type"] == "http.response.start":
            captured["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            captured["body"] = json.loads(msg["body"].decode("utf-8"))

    await middleware(scope, _noop_receive, _capture_send)
    return captured["status"], captured["body"], forwarded


def test_middleware_passes_request_at_exact_cap():
    """A ``Content-Length`` equal to ``max_bytes`` is allowed through."""

    async def _drive():
        return await _drive_middleware(10 * 1024 * 1024, str(10 * 1024 * 1024))

    status, body, forwarded = asyncio.run(_drive())
    assert status == 0, f"unexpected rejection status {status}: {body}"
    assert forwarded.get("called") is True, "downstream app was not invoked"
    assert body is None


def test_middleware_passes_request_under_cap():
    """A small body well under the cap flows through unchanged."""

    async def _drive():
        return await _drive_middleware(10 * 1024 * 1024, "1024")

    status, body, forwarded = asyncio.run(_drive())
    assert status == 0
    assert forwarded.get("called") is True
    assert body is None


def test_middleware_passes_request_at_10gb():
    """A 10 GB body is allowed under the new default cap (no regression)."""
    ten_gb = 10 * 1024 * 1024 * 1024

    async def _drive():
        return await _drive_middleware(ten_gb, str(ten_gb))

    status, body, forwarded = asyncio.run(_drive())
    assert status == 0
    assert forwarded.get("called") is True
    assert body is None


@pytest.mark.parametrize(
    "max_mb, content_length",
    [
        (10240, str(11 * 1024 * 1024 * 1024)),  # 11 GB body, 10 GB cap
        (1024, str(2 * 1024 * 1024 * 1024)),  # 2 GB body, 1 GB cap
        (10, str(20 * 1024 * 1024)),  # 20 MB body, 10 MB cap
    ],
)
def test_middleware_rejects_oversized_with_413_envelope(
    max_mb: int, content_length: str
):
    """An oversized body is rejected with the documented 413 envelope."""

    async def _drive():
        return await _drive_middleware(max_mb * 1024 * 1024, content_length)

    status, body, forwarded = asyncio.run(_drive())
    assert status == 413, f"expected 413, got {status}"
    assert forwarded.get("called") is None, "downstream app must not be invoked"
    assert body is not None
    # Envelope contract: error label + the three operator-friendly fields
    # the Settings tab consumes.
    assert body["error"] == "Upload exceeds maximum size"
    assert body["limit_bytes"] == str(max_mb * 1024 * 1024)
    assert body["limit_bytes_mb"] == str(max_mb)
    assert "OMNISCRIBE_MAX_UPLOAD_MB" in body["hint"]


def test_middleware_lets_chunked_request_without_length_through():
    """Chunked uploads bypass the length check — middleware passes through."""

    async def _drive():
        return await _drive_middleware(1024 * 1024, None)

    status, body, forwarded = asyncio.run(_drive())
    assert status == 0
    assert forwarded.get("called") is True
    assert body is None


def test_middleware_handles_non_ascii_length_gracefully():
    """A non-ASCII content-length falls through to the downstream app."""

    async def _drive():
        # Use a raw header that *looks* numeric but isn't ASCII so the
        # int() decode raises ValueError. The middleware should treat
        # this like "no length known" and pass the request through.
        return await _drive_middleware(1024, None)

    status, _body, forwarded = asyncio.run(_drive())
    assert status == 0
    assert forwarded.get("called") is True


# ---------------------------------------------------------------------------
# /api/config surfaces the cap (used by the Settings tab)
# ---------------------------------------------------------------------------


def test_config_endpoint_surfaces_max_upload_cap(
    monkeypatch: pytest.MonkeyPatch,
):
    """``GET /api/config`` exposes the operator-visible upload cap."""
    # The config router reads ``SecuritySettings.from_env()`` on every
    # call, so a monkeypatched env is sufficient — we don't need to
    # reload the module.
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "10240")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from omniscribe.api.routers.config import router as config_router

    app = FastAPI()
    app.include_router(config_router)

    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["max_upload_bytes"] == 10240 * 1024 * 1024
    assert payload["max_upload_mb"] == 10240
    assert payload["max_upload_env"] == "10240"


# ---------------------------------------------------------------------------
# .env.example documents the new defaults
# ---------------------------------------------------------------------------


def test_env_example_documents_upload_and_chunk_defaults():
    """``.env.example`` mentions both new knobs with the right defaults.

    The Settings tab hint reads this file, but more importantly operators
    reading it should see the same numbers the code ships with.
    """
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "OMNISCRIBE_MAX_UPLOAD_MB=10240" in env_example, (
        ".env.example must show the 10 GB default for OMNISCRIBE_MAX_UPLOAD_MB"
    )
    assert "OMNISCRIBE_CHUNK_PAGES=25" in env_example, (
        ".env.example must show the 25-page default for OMNISCRIBE_CHUNK_PAGES"
    )


# ---------------------------------------------------------------------------
# T2 / H2 audit gap: chunked upload (no Content-Length) > cap must still 413.
# ---------------------------------------------------------------------------


async def _drive_middleware_chunked(
    max_bytes: int, body_chunks: list[bytes]
) -> tuple[int, dict[str, Any] | None, bool]:
    """Drive ``MaxUploadSizeMiddleware`` with a multi-chunk chunked upload.

    Returns ``(status, body_dict, inner_called)``:
      * ``status`` is the HTTP status code the client saw (``0`` when the
        inner app produced a 200-style response the middleware let through).
      * ``body_dict`` is the decoded 413 envelope when ``status == 413``,
        otherwise ``None``.
      * ``inner_called`` records whether the inner app ran (sanity check
        that the test is exercising the real middleware path).
    """
    from omniscribe.api.middleware import MaxUploadSizeMiddleware

    inner_called = {"called": False}

    async def _inner(scope, receive, send):
        # Drain the (possibly truncated) body so the middleware's wrapped
        # receive actually runs against every chunk it was given.
        while True:
            msg = await receive()
            if msg.get("type") != "http.request":
                break
            if not msg.get("more_body", False):
                break
        # Emit a deterministic 200 with empty body — the middleware
        # will replace this with 413 if overflow was detected.
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        inner_called["called"] = True

    middleware = MaxUploadSizeMiddleware(_inner, max_bytes=max_bytes)
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],  # no Content-Length => chunked transfer
        "client": ("127.0.0.1", 1234),
    }

    captured: dict[str, Any] = {"status": 0, "body": None}
    chunk_iter = iter(body_chunks)

    async def _chunked_receive():
        try:
            chunk = next(chunk_iter)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def _capture_send(msg):
        if msg["type"] == "http.response.start":
            captured["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                captured["body"] = json.loads(msg["body"].decode("utf-8"))

    await middleware(scope, _chunked_receive, _capture_send)
    return captured["status"], captured["body"], inner_called["called"]


def test_middleware_rejects_chunked_single_chunk_overflow():
    """A single chunk larger than the cap is rejected with 413.

    T2 audit gap: a client that streams the whole upload as one chunk
    with no ``Content-Length`` must still see a 413 — the middleware
    cannot rely on the Content-Length fast path for chunked transfers.
    """
    cap = 1024

    async def _drive():
        return await _drive_middleware_chunked(
            cap,
            [b"x" * (cap * 2)],  # 2 KB body, 1 KB cap
        )

    status, body, inner_called = asyncio.run(_drive())
    assert status == 413
    assert body is not None
    assert body["error"] == "Upload exceeds maximum size"
    assert body["limit_bytes"] == str(cap)
    # The inner app's empty-body 200 must NOT reach the client.
    assert inner_called is True, (
        "inner app ran (test sanity); its 200 must be overridden by 413"
    )


def test_middleware_rejects_chunked_cumulative_overflow():
    """Many small chunks that sum past the cap are still rejected.

    The pre-fix implementation compared each chunk's individual size
    against ``max_bytes`` and missed cumulative overflow. This regression
    test pins the cumulative-byte accounting so a future refactor can't
    silently break it.
    """
    cap = 4 * 1024  # 4 KB cap
    # 10 × 600 B = 6 KB > 4 KB; no individual chunk exceeds the cap.
    chunks = [b"x" * 600 for _ in range(10)]

    async def _drive():
        return await _drive_middleware_chunked(cap, chunks)

    status, body, _ = asyncio.run(_drive())
    assert status == 413
    assert body is not None
    assert body["limit_bytes"] == str(cap)


def test_middleware_passes_chunked_under_cap():
    """A multi-chunk upload whose total fits under the cap passes through.

    Negative control for the cumulative-byte counter: confirms that the
    fix didn't accidentally reject any normal-sized chunked upload.
    """
    cap = 4 * 1024
    chunks = [b"x" * 256 for _ in range(8)]  # 2 KB total, 4 KB cap

    async def _drive():
        return await _drive_middleware_chunked(cap, chunks)

    status, body, inner_called = asyncio.run(_drive())
    assert status == 200, f"expected pass-through 200, got {status}: {body}"
    assert body is None, f"inner app's empty 200 body should not be JSON: {body}"
    assert inner_called is True


# ---------------------------------------------------------------------------
# C3 audit gap: ASGI protocol contract on chunked overflow
# ---------------------------------------------------------------------------


async def _drive_middleware_capture_all(
    max_bytes: int, body_chunks: list[bytes]
) -> tuple[list[dict[str, Any]], bool]:
    """Drive ``MaxUploadSizeMiddleware`` and record EVERY event forwarded
    to the ASGI ``send`` callable.

    Returns ``(events, inner_called)``:

    * ``events`` is the raw list of ASGI send-event dicts in the order
      they were forwarded to the underlying server. Used to assert the
      ASGI protocol contract (exactly one start, at most one body).
    * ``inner_called`` records whether the inner app ran (sanity).
    """
    from omniscribe.api.middleware import MaxUploadSizeMiddleware

    inner_called = {"called": False}

    async def _inner(scope, receive, send):
        # Drain the (possibly truncated) body so the middleware's
        # wrapped receive actually runs against every chunk.
        while True:
            msg = await receive()
            if msg.get("type") != "http.request":
                break
            if not msg.get("more_body", False):
                break
        # The inner app emits its own 200 + body. The middleware must
        # suppress BOTH of these on the rejected path; only the
        # middleware's 413 envelope should reach the underlying server.
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", b"13"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"hello, world!",
                "more_body": False,
            }
        )
        inner_called["called"] = True

    middleware = MaxUploadSizeMiddleware(_inner, max_bytes=max_bytes)
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],  # no Content-Length => chunked transfer
        "client": ("127.0.0.1", 1234),
    }

    events: list[dict[str, Any]] = []
    chunk_iter = iter(body_chunks)

    async def _chunked_receive():
        try:
            chunk = next(chunk_iter)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def _capture_send(msg):
        events.append(msg)

    await middleware(scope, _chunked_receive, _capture_send)
    return events, inner_called["called"]


def test_middleware_chunked_overflow_emits_exactly_one_start_and_body():
    """C3 audit fix: a chunked overflow must NOT produce a duplicate
    ``http.response.start`` / ``http.response.body`` pair from the inner
    app after the middleware's 413 envelope.

    ASGI only allows one ``http.response.start`` per request. The pre-fix
    middleware emitted its 413 envelope and then forwarded the inner
    app's own 200 start + body, which is a duplicate-completion bug that
    crashes uvicorn and is a known request-smuggling primitive.
    """
    cap = 1024

    async def _drive():
        return await _drive_middleware_capture_all(
            cap,
            [b"x" * (cap * 2)],  # 2 KB body, 1 KB cap
        )

    events, inner_called = asyncio.run(_drive())

    # Sanity: the inner app actually ran (otherwise the test is a no-op).
    assert inner_called is True, "inner app must run for the test to be meaningful"

    starts = [e for e in events if e.get("type") == "http.response.start"]
    bodies = [e for e in events if e.get("type") == "http.response.body"]

    # ASGI contract: exactly one start, at most one body, status 413.
    assert len(starts) == 1, (
        f"expected exactly one http.response.start, got {len(starts)}: {events}"
    )
    assert starts[0]["status"] == 413, (
        f"the one start event must be the 413 envelope, got {starts[0]['status']}"
    )
    assert len(bodies) == 1, (
        f"expected exactly one http.response.body, got {len(bodies)}: {events}"
    )
    decoded = json.loads(bodies[0]["body"].decode("utf-8"))
    assert decoded["error"] == "Upload exceeds maximum size"

    # The inner app's "hello, world!" body must not have leaked through.
    raw_bodies = [b["body"] for b in bodies]
    assert b"hello, world!" not in raw_bodies, (
        "inner app's body must be suppressed after the 413 envelope"
    )


def test_middleware_chunked_overflow_with_multiple_downstream_body_events():
    """C3 audit fix: even if the inner app emits several body events
    (e.g. streaming response), every one of them is suppressed.

    This pins the contract that ``self._sent_rejection`` (or the
    ``self._rejected and not start`` branch) catches every non-start
    event from the inner app, not just the first.
    """
    cap = 1024

    async def _drive():
        return await _drive_middleware_capture_all(
            cap,
            [b"x" * (cap * 3)],  # 3 KB body, 1 KB cap
        )

    events, _inner_called = asyncio.run(_drive())

    starts = [e for e in events if e.get("type") == "http.response.start"]
    bodies = [e for e in events if e.get("type") == "http.response.body"]

    assert len(starts) == 1
    assert starts[0]["status"] == 413
    # At most one body — the 413 envelope. No second body from the
    # inner app, ever.
    assert len(bodies) <= 1, (
        f"expected at most one body (the 413 envelope), got {len(bodies)}: "
        f"{[b['body'][:40] for b in bodies]}"
    )


def test_middleware_pass_through_emits_exactly_one_start_and_body():
    """Negative control: the suppression logic does NOT fire on a normal
    (under-cap) chunked request. The inner app's single 200 start and
    body must both reach the server.
    """
    cap = 4 * 1024
    chunks = [b"x" * 256 for _ in range(8)]  # 2 KB total, 4 KB cap

    async def _drive():
        return await _drive_middleware_capture_all(cap, chunks)

    events, inner_called = asyncio.run(_drive())

    assert inner_called is True
    starts = [e for e in events if e.get("type") == "http.response.start"]
    bodies = [e for e in events if e.get("type") == "http.response.body"]

    assert len(starts) == 1
    assert starts[0]["status"] == 200
    assert len(bodies) == 1
    assert bodies[0]["body"] == b"hello, world!"
