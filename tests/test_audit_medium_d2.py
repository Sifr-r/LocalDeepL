"""Regression tests for the Domain 2 MEDIUM cluster audit fixes.

Pins the post-2026-08-17 behaviour of the security middleware / config
/ provider-create surface so future refactors cannot silently regress
the six MEDIUM items addressed in Phase 5b:

* **F2.3** — ``MaxUploadSizeMiddleware`` enforces a per-request
  wall-clock deadline (``deadline_s``) in the chunked path; pre-fix,
  a slow trickle attacker could hold a worker open indefinitely.
* **F2.4** — ``RateLimitMiddleware`` applies the per-IP bucket to
  ``scope["type"] == "websocket"`` upgrades too; pre-fix, WS floods
  were bounded only by the 10 s ``verify_minted`` auth-frame timeout.
* **F2.5** — ``BearerAuthMiddleware._get_active_tokens`` logs a
  warning (with traceback) when the config-store read fails; pre-fix,
  Redis / SQLite outages silently downgraded to env-only tokens.
* **F2.6** — ``ProviderCreateRequest.headers`` rejects
  routing-affecting / auth-override / body-framing keys; pre-fix, the
  field was a freeform ``dict[str, str]`` and a token-bearing caller
  could override ``Host``, ``Authorization``, or push
  ``Content-Length`` for request smuggling.
* **F2.7** — ``SecuritySettings._validate_auth_token`` redacts the
  offending token in the startup ``RuntimeError``; pre-fix, a
  misconfigured ``.env`` + log aggregator leaked the credential.
* **F2.8** — CORS uses an explicit methods/headers allowlist
  (configurable via ``OMNISCRIBE_CORS_ALLOWED_METHODS`` /
  ``OMNISCRIBE_CORS_ALLOWED_HEADERS``); pre-fix, the middleware used
  ``allow_methods=["*"], allow_headers=["*"]`` wildcards.

The middleware exercises ASGI directly (no FastAPI boot) following
the existing ``test_size_limits.py`` / ``test_rate_limit_proxy.py``
patterns. Pydantic validation is exercised via the
``ProviderCreateRequest`` model directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")


REPO_ROOT = "D:/OmniScribe"


# ---------------------------------------------------------------------------
# F2.3 — per-request deadline
# ---------------------------------------------------------------------------


def test_max_upload_middleware_default_deadline_is_120s() -> None:
    """The middleware default is 120s — a comfortable budget at the 100 GB cap.

    A legitimate 100 GB upload at 100 MB/s finishes in ~17 minutes, so
    2 minutes is plenty of headroom for healthy clients. A slow
    trickle attacker burns the budget in seconds.
    """
    from omniscribe.api.services.security_middleware import MaxUploadSizeMiddleware

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
    from omniscribe.api.services.security_middleware import MaxUploadSizeMiddleware

    async def _noop(scope, receive, send):
        return None

    mw = MaxUploadSizeMiddleware(_noop, max_bytes=1024, deadline_s=7.5)
    assert mw.deadline_s == 7.5


def test_security_settings_exposes_upload_deadline_s() -> None:
    """``SecuritySettings.upload_deadline_s`` carries the configured budget."""
    from omniscribe.api.services.security_config import SecuritySettings

    s = SecuritySettings()
    assert s.upload_deadline_s == 120.0


def test_security_settings_upload_deadline_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OMNISCRIBE_UPLOAD_DEADLINE_S`` overrides the default."""
    from omniscribe.api.services.security_config import SecuritySettings

    monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_S", "300.0")
    s = SecuritySettings.from_env()
    assert s.upload_deadline_s == 300.0


def test_security_settings_upload_deadline_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric deadline warns and falls back to the 120s default."""
    from omniscribe.api.services.security_config import SecuritySettings

    monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_S", "not-a-number")
    s = SecuritySettings.from_env()
    assert s.upload_deadline_s == 120.0


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
    from omniscribe.api.services.security_middleware import MaxUploadSizeMiddleware

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
    from omniscribe.api.services.security_middleware import MaxUploadSizeMiddleware

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
# ---------------------------------------------------------------------------


def _stub_app() -> Any:
    """A no-op ASGI app used as the rate-limiter's inner target."""

    class _Stub:
        async def __call__(self, scope, receive, send):
            return None

    return _Stub()


def test_rate_limit_passes_websocket_under_cap() -> None:
    """A WS upgrade under the per-IP cap is forwarded to the inner app."""
    from omniscribe.api.services.security_middleware import RateLimitMiddleware

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
    from omniscribe.api.services.security_middleware import RateLimitMiddleware

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
    from omniscribe.api.services.security_middleware import RateLimitMiddleware

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
    from omniscribe.api.services.security_middleware import RateLimitMiddleware

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
# ---------------------------------------------------------------------------


def test_get_active_tokens_logs_warning_on_config_store_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing config-store read logs a warning (with traceback) before falling back."""
    from omniscribe.api.services.security_middleware import BearerAuthMiddleware

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


# ---------------------------------------------------------------------------
# F2.6 — ProviderCreateRequest.headers validation
# ---------------------------------------------------------------------------


def test_provider_create_request_accepts_benign_headers() -> None:
    """Custom headers (e.g. tenant-id, x-trace-id) are accepted unchanged."""
    from omniscribe.api.schemas.requests import ProviderCreateRequest

    req = ProviderCreateRequest(
        id="custom",
        display_name="Custom",
        api_url="https://api.example.com/v1",
        headers={"X-Tenant-Id": "abc", "x-trace-id": "trace-1"},
    )
    assert req.headers == {"X-Tenant-Id": "abc", "x-trace-id": "trace-1"}


@pytest.mark.parametrize(
    "bad_key",
    [
        "Host",
        "host",
        "X-Forwarded-Host",
        "x-forwarded-for",
        "X-Real-IP",
        "Forwarded",
        ":authority",
        ":scheme",
        "content-length",
        "transfer-encoding",
        "Authorization",
        "authorization",
        "Proxy-Authorization",
        "Cookie",
    ],
)
def test_provider_create_request_rejects_routing_and_auth_headers(bad_key: str) -> None:
    """Routing-affecting, body-framing, and credential headers are rejected."""
    from pydantic import ValidationError

    from omniscribe.api.schemas.requests import ProviderCreateRequest

    with pytest.raises(ValidationError) as exc_info:
        ProviderCreateRequest(
            id="custom",
            display_name="Custom",
            api_url="https://api.example.com/v1",
            headers={bad_key: "value"},
        )
    msg = str(exc_info.value)
    assert "routing- or auth-affecting keys" in msg
    assert bad_key in msg or bad_key.lower() in msg


def test_provider_create_request_error_lists_all_bad_keys() -> None:
    """The error message lists every offending key, not just the first."""
    from pydantic import ValidationError

    from omniscribe.api.schemas.requests import ProviderCreateRequest

    with pytest.raises(ValidationError) as exc_info:
        ProviderCreateRequest(
            id="custom",
            display_name="Custom",
            api_url="https://api.example.com/v1",
            headers={"Host": "x", "Authorization": "y", "X-Tenant-Id": "ok"},
        )
    msg = str(exc_info.value)
    assert "Host" in msg
    assert "Authorization" in msg
    # The benign key is still present in the model (validation
    # happens on assignment; the model is built before the validator
    # raises). What matters is that the validator raises, not that
    # partial state is preserved.
    assert "X-Tenant-Id" not in msg or "routing" in msg


# ---------------------------------------------------------------------------
# F2.7 — _validate_auth_token redacts the token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "abc",  # too short (3 chars, need >= 32)
        "abcdefgh",  # too short (8 chars)
        "change-me",  # placeholder
        "password",  # placeholder
    ],
)
def test_validate_auth_token_redacts_offending_value(token: str) -> None:
    """The startup RuntimeError never contains the raw token."""
    from omniscribe.api.services.security_config import _validate_auth_token

    with pytest.raises(RuntimeError) as exc_info:
        _validate_auth_token("OMNISCRIBE_AUTH_TOKEN", token)
    msg = str(exc_info.value)
    # The raw value must not appear in the message.
    assert token not in msg, f"token leaked into RuntimeError: {msg!r}"
    # The redaction placeholder is present.
    assert "<redacted" in msg
    # Length and first/last char are surfaced.
    assert f"length={len(token)}" in msg
    assert f"first={token[0]!r}" in msg
    assert f"last={token[-1]!r}" in msg


def test_validate_auth_token_preserves_env_name_in_error() -> None:
    """The error still identifies the offending env var."""
    from omniscribe.api.services.security_config import _validate_auth_token

    with pytest.raises(RuntimeError) as exc_info:
        _validate_auth_token("OMNISCRIBE_OCR_AUTH_TOKEN", "short")
    msg = str(exc_info.value)
    assert "OMNISCRIBE_OCR_AUTH_TOKEN" in msg


def test_redact_token_handles_empty_string() -> None:
    """An empty input returns ``<empty>`` (defensive)."""
    from omniscribe.api.services.security_config import _redact_token

    assert _redact_token("") == "<empty>"


def test_redact_token_shape_is_deterministic_for_same_input() -> None:
    """Same input produces the same redaction (operator can correlate)."""
    from omniscribe.api.services.security_config import _redact_token

    sample = "abcdefghijklmnopqrstuvwxyz0123456789"  # 36 chars
    assert _redact_token(sample) == _redact_token(sample)
    assert "length=36" in _redact_token(sample)
    assert "first='a'" in _redact_token(sample)
    assert "last='9'" in _redact_token(sample)


def test_validate_auth_token_valid_token_returns_unchanged() -> None:
    """A valid-length, non-placeholder token is returned trimmed."""
    from omniscribe.api.services.security_config import _validate_auth_token

    valid = "a" * 64
    assert _validate_auth_token("OMNISCRIBE_AUTH_TOKEN", valid) == valid
    # With surrounding whitespace.
    assert _validate_auth_token("OMNISCRIBE_AUTH_TOKEN", f"  {valid}  ") == valid


# ---------------------------------------------------------------------------
# F2.8 — CORS allowlist
# ---------------------------------------------------------------------------


def test_security_settings_default_cors_methods_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default CORS methods are the explicit (non-wildcard) set."""
    from omniscribe.api.services.security_config import (
        DEFAULT_CORS_ALLOWED_METHODS,
        SecuritySettings,
    )

    monkeypatch.delenv("OMNISCRIBE_CORS_ALLOWED_METHODS", raising=False)
    monkeypatch.delenv("OMNISCRIBE_CORS_ALLOWED_HEADERS", raising=False)
    s = SecuritySettings.from_env()
    assert "*" not in s.cors_allowed_methods
    assert set(s.cors_allowed_methods) == set(DEFAULT_CORS_ALLOWED_METHODS)
    # Default surface is GET/POST/PUT/DELETE/OPTIONS — no PATCH,
    # no custom verbs.
    assert "PATCH" not in s.cors_allowed_methods
    assert "TRACE" not in s.cors_allowed_methods


def test_security_settings_default_cors_headers_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default CORS headers are the explicit (non-wildcard) set."""
    from omniscribe.api.services.security_config import (
        DEFAULT_CORS_ALLOWED_HEADERS,
        SecuritySettings,
    )

    monkeypatch.delenv("OMNISCRIBE_CORS_ALLOWED_HEADERS", raising=False)
    s = SecuritySettings.from_env()
    assert "*" not in s.cors_allowed_headers
    assert set(s.cors_allowed_headers) == set(DEFAULT_CORS_ALLOWED_HEADERS)
    # Authorization is the only auth header in the default surface.
    assert "Authorization" in s.cors_allowed_headers


def test_security_settings_cors_methods_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OMNISCRIBE_CORS_ALLOWED_METHODS`` overrides the default."""
    from omniscribe.api.services.security_config import SecuritySettings

    monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_METHODS", "GET,POST,PATCH")
    s = SecuritySettings.from_env()
    assert s.cors_allowed_methods == ["GET", "POST", "PATCH"]
    # Methods are upper-cased.
    assert all(m == m.upper() for m in s.cors_allowed_methods)


def test_security_settings_cors_wildcard_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A wildcard-only override warns and falls back to the default surface."""
    from omniscribe.api.services.security_config import (
        DEFAULT_CORS_ALLOWED_HEADERS,
        DEFAULT_CORS_ALLOWED_METHODS,
        SecuritySettings,
    )

    with caplog.at_level(
        logging.WARNING, logger="omniscribe.api.services.security_config"
    ):
        monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_METHODS", "*")
        monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_HEADERS", "*")
        s = SecuritySettings.from_env()
    assert s.cors_allowed_methods == sorted(DEFAULT_CORS_ALLOWED_METHODS)
    assert s.cors_allowed_headers == sorted(DEFAULT_CORS_ALLOWED_HEADERS)
    matching = [
        r for r in caplog.records if "OMNISCRIBE_CORS_ALLOWED" in r.getMessage()
    ]
    assert len(matching) == 2


def test_server_passes_cors_allowlist_to_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``create_app()`` threads the configured methods/headers to ``CORSMiddleware``."""
    from omniscribe.api.services import security_config as sc_module
    from omniscribe.server import create_app

    fake_settings = sc_module.SecuritySettings(
        cors_origins=["https://app.example.com"],
        cors_allowed_methods=["GET", "POST"],
        cors_allowed_headers=["Authorization", "Content-Type"],
    )
    with patch.object(sc_module, "SecuritySettings") as mock_cls:
        mock_cls.from_env.return_value = fake_settings
        # Skip the lifespan / router / mount dance — we only want to
        # verify CORSMiddleware was registered with the right kwargs.
        app = create_app()
    cors_layers = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors_layers) == 1
    layer = cors_layers[0]
    # The middleware was constructed with the configured allowlist.
    assert layer.kwargs.get("allow_methods") == ["GET", "POST"]
    assert layer.kwargs.get("allow_headers") == ["Authorization", "Content-Type"]
    assert layer.kwargs.get("allow_origins") == ["https://app.example.com"]
    # Wildcards are gone.
    assert "*" not in layer.kwargs.get("allow_methods", [])
    assert "*" not in layer.kwargs.get("allow_headers", [])
    # ``allow_credentials`` stays False (the CORS misconfig guard).
    assert layer.kwargs.get("allow_credentials") is False
