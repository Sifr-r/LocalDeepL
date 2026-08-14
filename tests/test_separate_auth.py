"""Tests for the per-service bearer-token middleware and env-var loading.

Pins the public contract for the OAuth-style split introduced alongside the
per-namespace config endpoints:

* ``BearerAuthMiddleware.route_group_for`` classifies incoming paths into
  ``"ocr"``, ``"translation"`` and ``"other"`` buckets. Paths under
  ``/api/process`` are OCR; paths under ``/api/translate``, ``/api/extract``,
  ``/api/export`` and ``/api/glossary`` are translation.
* Per-service tokens (``ocr_token`` / ``translation_token``) take precedence
  over the global ``expected_token`` for the matching route group.
* When a per-service token is set, requests under that group must carry
  *that* token specifically — the global token does not unlock the group.
* When neither the global nor a per-service token is configured, the
  middleware is a no-op.
* ``SecuritySettings.from_env`` reads ``OMNISCRIBE_OCR_AUTH_TOKEN`` and
  ``OMNISCRIBE_TRANSLATION_AUTH_TOKEN`` from the environment.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

import pytest

from omniscribe.api.services.security_config import SecuritySettings
from omniscribe.api.services.security_middleware import BearerAuthMiddleware

# ---------------------------------------------------------------------------
# Pure ASGI helpers
# ---------------------------------------------------------------------------


class _CollectSend:
    """Capture ASGI send events so a test can inspect status / body."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    @property
    def status(self) -> int:
        for event in self.events:
            if event.get("type") == "http.response.start":
                return int(event.get("status", 0))
        return 0

    @property
    def body(self) -> bytes:
        chunks: list[bytes] = []
        for event in self.events:
            if event.get("type") == "http.response.body":
                body = event.get("body", b"")
                if isinstance(body, (bytes, bytearray)):
                    chunks.append(bytes(body))
        return b"".join(chunks)

    @property
    def body_json(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.body or b"{}"))


class _MarkerApp:
    """Terminal ASGI app that records whether the middleware passed through."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_scope: dict[str, Any] | None = None

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        self.calls += 1
        self.last_scope = scope
        # Mimic a minimal FastAPI 200 OK response so callers can read body.
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", b"2"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})


async def _receive() -> dict[str, Any]:
    """No-op receive callable; tests do not exercise request bodies."""
    return {"type": "http.request", "body": b"", "more_body": False}


def _scope(
    *,
    path: str,
    authorization: str | None = None,
    raw_path: bytes | None = None,
) -> dict[str, Any]:
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "scheme": "http",
        "server": ("testserver", 80),
        "headers": headers,
    }
    if raw_path is not None:
        scope["raw_path"] = raw_path
    return scope


async def _invoke(
    middleware: BearerAuthMiddleware,
    *,
    path: str,
    authorization: str | None = None,
    raw_path: bytes | None = None,
) -> tuple[_MarkerApp, _CollectSend]:
    inner = cast(_MarkerApp, middleware.app)
    send = _CollectSend()
    await middleware(
        _scope(path=path, authorization=authorization, raw_path=raw_path),
        _receive,
        send,
    )
    return inner, send


# ---------------------------------------------------------------------------
# route_group_for classification
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


# ---------------------------------------------------------------------------
# No-op when no token is configured
# ---------------------------------------------------------------------------


async def test_middleware_is_noop_when_no_token_set() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token=None)

    inner, send = await _invoke(middleware, path="/api/process")

    assert inner.calls == 1
    assert send.status == 200


async def test_middleware_is_noop_when_only_whitespace_token_set() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="   ")

    inner, _send = await _invoke(middleware, path="/api/process")

    assert inner.calls == 1


# ---------------------------------------------------------------------------
# Global token (back-compat) still works
# ---------------------------------------------------------------------------


async def test_global_token_accepts_ocr_request() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    inner, send = await _invoke(
        middleware, path="/api/process", authorization="Bearer global-secret"
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_global_token_accepts_translation_request() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    inner, send = await _invoke(
        middleware, path="/api/translate", authorization="Bearer global-secret"
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_global_token_rejects_request_without_authorization() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    inner, send = await _invoke(middleware, path="/api/process")

    assert inner.calls == 0
    assert send.status == 401
    assert send.body_json == {"error": "Unauthorized"}


async def test_global_token_rejects_wrong_authorization() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    inner, send = await _invoke(
        middleware, path="/api/process", authorization="Bearer not-the-secret"
    )

    assert inner.calls == 0
    assert send.status == 401


async def test_global_token_rejects_non_bearer_scheme() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    inner, send = await _invoke(
        middleware, path="/api/process", authorization="Basic dXNlcjpwYXNz"
    )

    assert inner.calls == 0
    assert send.status == 401


# ---------------------------------------------------------------------------
# Per-service tokens take precedence
# ---------------------------------------------------------------------------


async def test_ocr_token_accepts_ocr_request_with_ocr_token() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/process", authorization="Bearer ocr-secret"
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_ocr_token_rejects_ocr_request_with_global_token() -> None:
    """When an OCR token is set, the global token does NOT unlock OCR routes."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/process", authorization="Bearer global-secret"
    )

    assert inner.calls == 0
    assert send.status == 401


async def test_translation_token_accepts_translate_request() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/translate", authorization="Bearer translation-secret"
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_translation_token_rejects_translate_request_with_global_token() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/translate", authorization="Bearer global-secret"
    )

    assert inner.calls == 0
    assert send.status == 401


async def test_translation_token_accepts_extract_request() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        translation_token="translation-secret",
    )

    inner, _send = await _invoke(
        middleware, path="/api/extract", authorization="Bearer translation-secret"
    )

    assert inner.calls == 1


async def test_translation_token_accepts_glossary_request() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        translation_token="translation-secret",
    )

    inner, _send = await _invoke(
        middleware, path="/api/glossary", authorization="Bearer translation-secret"
    )

    assert inner.calls == 1


async def test_other_routes_use_global_token_only() -> None:
    """``/api/config`` and other shared endpoints fall back to the global token."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/config", authorization="Bearer global-secret"
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_other_routes_reject_ocr_token() -> None:
    """Per-service tokens must not unlock routes outside their group."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware, path="/api/config", authorization="Bearer ocr-secret"
    )

    assert inner.calls == 0
    assert send.status == 401


async def test_only_ocr_token_set_blocks_translation_routes() -> None:
    """Setting only an OCR token leaves translation routes open per global."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token=None,
        ocr_token="ocr-secret",
    )

    # OCR request rejected (no token).
    _inner, ocr_send = await _invoke(middleware, path="/api/process")
    assert ocr_send.status == 401

    # Translation route is unaffected when no global or per-service token is set.
    inner, tr_send = await _invoke(middleware, path="/api/translate")
    assert inner.calls == 1
    assert tr_send.status == 200


# ---------------------------------------------------------------------------
# Whitespace / None normalisation
# ---------------------------------------------------------------------------


async def test_whitespace_only_ocr_token_is_ignored() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token=None,
        ocr_token="   ",
    )

    inner, send = await _invoke(middleware, path="/api/process")

    # Treated as no token at all -> no-op.
    assert inner.calls == 1
    assert send.status == 200


async def test_whitespace_global_token_is_ignored() -> None:
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="   ",
    )

    inner, send = await _invoke(middleware, path="/api/process")

    assert inner.calls == 1
    assert send.status == 200


# ---------------------------------------------------------------------------
# SecuritySettings.from_env — per-service token loading
# ---------------------------------------------------------------------------


def test_security_settings_loads_per_service_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "global-secret")
    monkeypatch.setenv("OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret")
    monkeypatch.setenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "translation-secret")

    settings = SecuritySettings.from_env()

    assert settings.auth_token == "global-secret"
    assert settings.ocr_auth_token == "ocr-secret"
    assert settings.translation_auth_token == "translation-secret"
    assert settings.auth_enabled is True
    assert settings.ocr_auth_enabled is True
    assert settings.translation_auth_enabled is True


def test_security_settings_only_ocr_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNISCRIBE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret")

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token == "ocr-secret"
    assert settings.translation_auth_token is None
    assert settings.auth_enabled is False
    assert settings.ocr_auth_enabled is True
    assert settings.translation_auth_enabled is False


def test_security_settings_only_translation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNISCRIBE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_OCR_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "translation-secret")

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token is None
    assert settings.translation_auth_token == "translation-secret"
    assert settings.auth_enabled is False
    assert settings.translation_auth_enabled is True


def test_security_settings_empty_tokens_are_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "   ")
    monkeypatch.setenv("OMNISCRIBE_OCR_AUTH_TOKEN", "")
    monkeypatch.setenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "\t\n")

    settings = SecuritySettings.from_env()

    # All whitespace values should be normalised to None.
    assert settings.auth_token is None
    assert settings.ocr_auth_token is None
    assert settings.translation_auth_token is None


def test_security_settings_trims_token_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "  trimmed-global  ")
    monkeypatch.setenv("OMNISCRIBE_OCR_AUTH_TOKEN", "  trimmed-ocr  ")
    monkeypatch.setenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "  trimmed-tr  ")

    settings = SecuritySettings.from_env()

    assert settings.auth_token == "trimmed-global"
    assert settings.ocr_auth_token == "trimmed-ocr"
    assert settings.translation_auth_token == "trimmed-tr"


def test_security_settings_no_env_returns_none_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OMNISCRIBE_AUTH_TOKEN",
        "OMNISCRIBE_OCR_AUTH_TOKEN",
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token is None
    assert settings.translation_auth_token is None
    assert settings.auth_enabled is False


# ---------------------------------------------------------------------------
# M10: fail-fast on well-known placeholder auth tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_name, placeholder",
    [
        ("OMNISCRIBE_AUTH_TOKEN", "change-me-in-prod"),
        ("OMNISCRIBE_AUTH_TOKEN", "Change-Me-In-Prod"),
        ("OMNISCRIBE_AUTH_TOKEN", "  password  "),
        ("OMNISCRIBE_OCR_AUTH_TOKEN", "secret"),
        ("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "admin"),
    ],
)
def test_security_settings_rejects_placeholder_auth_token(
    monkeypatch: pytest.MonkeyPatch, env_name: str, placeholder: str
) -> None:
    """Boots must refuse any of the well-known placeholder values, in
    any of the three auth-token env vars. The same denylist is enforced
    on incoming ``AuthTokenUpdate`` requests, so a copy-pasted ``.env``
    never lets the server come up with an attacker-guessable credential.
    """
    monkeypatch.delenv("OMNISCRIBE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_OCR_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", raising=False)
    monkeypatch.setenv(env_name, placeholder)

    with pytest.raises(RuntimeError, match="placeholder"):
        SecuritySettings.from_env()


def test_security_settings_accepts_32_char_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real 32+ char secret is accepted verbatim, no fail-fast."""
    real_secret = "a" * 32 + "real-secret-with-enough-entropy"
    for name in (
        "OMNISCRIBE_AUTH_TOKEN",
        "OMNISCRIBE_OCR_AUTH_TOKEN",
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN",
    ):
        monkeypatch.setenv(name, real_secret)

    settings = SecuritySettings.from_env()

    assert settings.auth_token == real_secret
    assert settings.ocr_auth_token == real_secret
    assert settings.translation_auth_token == real_secret


# ---------------------------------------------------------------------------
# Body-decoding utility — guard the JSON error path
# ---------------------------------------------------------------------------


async def test_401_body_is_well_formed_json() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    _inner, send = await _invoke(middleware, path="/api/process")

    payload = send.body_json
    assert payload == {"error": "Unauthorized"}


# ---------------------------------------------------------------------------
# Headers iteration robustness
# ---------------------------------------------------------------------------


async def test_middleware_handles_missing_headers_scope() -> None:
    """Middleware must not crash when an ASGI scope lacks ``headers``."""
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    scope = _scope(path="/api/process")
    scope.pop("headers", None)
    send = _CollectSend()
    await middleware(scope, _receive, send)

    assert send.status == 401


async def test_middleware_handles_empty_headers_list() -> None:
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token="global-secret")

    scope: dict[str, Any] = _scope(path="/api/process")
    scope["headers"] = cast(Iterable[tuple[bytes, bytes]], [])
    send = _CollectSend()
    await middleware(scope, _receive, send)

    assert send.status == 401


# ---------------------------------------------------------------------------
# Path-normalization hardening (report finding 1.5)
#
# The middleware must percent-decode the request path, collapse ``..``
# segments, and reject any non-ASCII character before the route is
# classified. A request that abuses percent-encoding or traversal to
# cross the per-route token boundary must end up using the correct
# service-specific token, not the global one.
# ---------------------------------------------------------------------------


async def test_percent_encoded_slash_with_traversal_classifies_as_ocr() -> None:
    """``/api/process%2F/../models/ocr`` collapses to ``/api/models/ocr``.

    Starlette leaves ``%2F`` intact in ``scope["path"]``; without
    percent-decoding, the request would slip past the OCR allowlist and
    be authed against the global token. After normalization the path
    matches the OCR group, so the global token must fail.
    """
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    wire_path = "/api/process%2F/../models/ocr"
    inner, send = await _invoke(
        middleware,
        path=wire_path,
        raw_path=wire_path.encode("latin-1"),
        authorization="Bearer global-secret",
    )

    # The global token does NOT unlock OCR routes, so the request is
    # rejected even though the wire path looks like an unrelated prefix.
    assert inner.calls == 0
    assert send.status == 401
    assert send.body_json == {"error": "Unauthorized"}


async def test_ocr_token_unlocks_percent_encoded_slash_with_traversal() -> None:
    """The matching OCR token unlocks the same request — full round-trip."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    wire_path = "/api/process%2F/../models/ocr"
    inner, send = await _invoke(
        middleware,
        path=wire_path,
        raw_path=wire_path.encode("latin-1"),
        authorization="Bearer ocr-secret",
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_non_ascii_path_is_rejected_before_token_compare() -> None:
    """Cyrillic homoglyph ``а`` (U+0430) cannot stand in for ``a``.

    The wire form ``/api/process`` is rejected with 400 Invalid path
    before any token comparison runs, so an attacker cannot use a
    homoglyph to bypass the per-route grouping.
    """
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    # Wire form: /%D0%B0pi/process  (Cyrillic а percent-encoded as UTF-8).
    wire_path = "/%D0%B0pi/process"
    inner, send = await _invoke(
        middleware,
        path=wire_path,
        raw_path=wire_path.encode("latin-1"),
        authorization="Bearer global-secret",
    )

    assert inner.calls == 0
    assert send.status == 400
    assert send.body_json == {"error": "Invalid path"}


async def test_traversal_within_ocr_namespace_classifies_as_ocr() -> None:
    """``/api/config/ocr/x/y/..`` collapses to ``/api/config/ocr/x``.

    A traversal that stays inside the OCR namespace must still classify
    as OCR, so the global token does not unlock the request.
    """
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
    )

    inner, send = await _invoke(
        middleware,
        path="/api/config/ocr/x/y/..",
        authorization="Bearer global-secret",
    )

    # Global token fails because the collapsed path is OCR.
    assert inner.calls == 0
    assert send.status == 401
    assert send.body_json == {"error": "Unauthorized"}


async def test_health_probe_bypasses_auth_with_token_set() -> None:
    """The fix must not regress the orchestrator probe bypass.

    With both a global and per-service token configured, ``/health``
    still reaches the inner app so the orchestrator can probe the
    server. This pins the post-normalization behaviour of the
    ``_is_health_path`` short-circuit.
    """
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(middleware, path="/health")

    assert inner.calls == 1
    assert send.status == 200


async def test_traversal_collapses_to_translation_route() -> None:
    """``/api/translate/x/y/../z`` collapses to ``/api/translate/x/z``.

    The final segment is under ``/api/translate``; the traversal is
    collapsed before classification so the translation token (not the
    global) is required.
    """
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        ocr_token="ocr-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware,
        path="/api/translate/x/y/../z",
        authorization="Bearer global-secret",
    )

    # Global token does not unlock translation routes.
    assert inner.calls == 0
    assert send.status == 401


async def test_translation_token_unlocks_traversal_to_translation_route() -> None:
    """Same request, but with the matching translation token — accepted."""
    middleware = BearerAuthMiddleware(
        app=_MarkerApp(),
        expected_token="global-secret",
        translation_token="translation-secret",
    )

    inner, send = await _invoke(
        middleware,
        path="/api/translate/x/y/../z",
        authorization="Bearer translation-secret",
    )

    assert inner.calls == 1
    assert send.status == 200


async def test_non_ascii_path_rejected_even_with_no_token() -> None:
    """The 400 Invalid path response fires regardless of token config.

    A non-ASCII path is rejected before the token lookup, so the
    response is the same whether or not a global token is set.
    """
    middleware = BearerAuthMiddleware(app=_MarkerApp(), expected_token=None)

    wire_path = "/%D0%B0pi/process"
    inner, send = await _invoke(
        middleware,
        path=wire_path,
        raw_path=wire_path.encode("latin-1"),
    )

    assert inner.calls == 0
    assert send.status == 400
    assert send.body_json == {"error": "Invalid path"}
