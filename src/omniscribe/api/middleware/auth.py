"""Bearer authentication middleware for ASGI.

Rejects every HTTP request whose ``Authorization: Bearer <token>`` header
does not match the configured token(s). Three independent tokens are
supported, with per-route precedence:

  * ``expected_token`` (global) applies to every route.
  * ``ocr_token`` overrides the global token for OCR routes
    (``/api/process``, ``/api/models/ocr``, ``/api/config/ocr``).
  * ``translation_token`` overrides the global token for
    translation routes (``/api/translate``, ``/api/extract``,
    ``/api/export``, ``/api/glossary``, ``/api/models/translation``,
    ``/api/config/translation``).
  * ``transcription_token`` overrides the global token for
    transcription routes (``/api/transcribe``,
    ``/api/models/transcription``, ``/api/config/transcription``).

WebSocket traffic is passed through; channel-level token binding
is enforced separately inside ``api/routers/websocket.py``.
"""

from __future__ import annotations

import json
import logging
import posixpath
import secrets
import urllib.parse
from typing import Any, Final

_LOGGER = logging.getLogger("omniscribe.api.middleware")

_UNAUTHORIZED: Final[dict[str, str]] = {"error": "Unauthorized"}
_INVALID_PATH: Final[dict[str, str]] = {"error": "Invalid path"}

_HEALTH_PATHS: Final[frozenset[str]] = frozenset(
    {"/health", "/healthz", "/ready", "/readyz"}
)


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
    if (
        path == "/api/process"
        or path.startswith("/api/process/")
        or path == "/process"
        or path.startswith("/process/")
    ):
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


def _is_health_path(path: str) -> bool:
    """Return True when ``path`` is a health/readiness probe.

    Orchestrators must always be able to probe the server, even when a
    global bearer token is configured. The exact set is the four
    Kubernetes-flavoured aliases; we deliberately do NOT match prefix
    paths so a future ``/health/details`` route stays protected.
    """
    return path in _HEALTH_PATHS


def _is_management_route(path: str) -> bool:
    """Return True when ``path`` is a management or administration endpoint."""
    return bool(
        path == "/api/providers"
        or path.startswith("/api/providers/")
        or path == "/api/jobs"
        or path.startswith("/api/jobs/")
        or path == "/api/progress/session"
        or path.startswith("/api/progress/session/")
        or path == "/api/config"
        or path.startswith("/api/config/")
    )


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
        app: Any,
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

    def _get_active_tokens(self) -> dict[str, str | None]:
        dynamic_ocr: str | None = None
        dynamic_translation: str | None = None
        dynamic_transcription: str | None = None
        dynamic_global: str | None = None
        try:
            from omniscribe.api.routers.config import _load_config_from_store

            cfg = _load_config_from_store()
            dynamic_ocr = _normalize_token(cfg.get("ocr_auth_token"))
            dynamic_translation = _normalize_token(cfg.get("translation_auth_token"))
            dynamic_transcription = _normalize_token(
                cfg.get("transcription_auth_token")
            )
            dynamic_global = _normalize_token(cfg.get("auth_token"))
        except Exception as exc:
            # F2.5 audit fix: the previous bare ``except Exception:
            # pass`` silently downgraded to env-only tokens on any
            # config-store read failure (Redis outage, SQLite lock
            # contention, JSON corruption, missing module after a
            # hot-reload, ...). Operators would see "I set the OCR
            # token via the API yesterday and the server still uses
            # the env value" with no log line to point at. The
            # fallback itself is fine — env tokens are a valid
            # boot-time-only auth — but the operator deserves to
            # know the dynamic store was unreachable. We log the
            # exception (with traceback) and continue.
            _LOGGER.warning(
                "BearerAuthMiddleware: failed to read tokens from "
                "config store; falling back to env-only tokens. %s",
                exc,
                exc_info=True,
            )

        return {
            "global": dynamic_global
            if dynamic_global is not None
            else self.expected_token,
            "ocr": dynamic_ocr if dynamic_ocr is not None else self.ocr_token,
            "translation": dynamic_translation
            if dynamic_translation is not None
            else self.translation_token,
            "transcription": dynamic_transcription
            if dynamic_transcription is not None
            else self.transcription_token,
        }

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
        every route uses it. When global is unset but subsystem tokens exist,
        management routes return the first available subsystem token.
        When no token applies, returns ``None``.
        """
        tokens = self._get_active_tokens()
        group = self.route_group_for(path)
        if group == "ocr" and tokens["ocr"] is not None:
            return tokens["ocr"]
        if group == "translation" and tokens["translation"] is not None:
            return tokens["translation"]
        if group == "transcription" and tokens["transcription"] is not None:
            return tokens["transcription"]
        if tokens["global"] is not None:
            return tokens["global"]
        if _is_management_route(path):
            for t in (tokens["ocr"], tokens["translation"], tokens["transcription"]):
                if t is not None:
                    return t
        return None

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
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

        tokens = self._get_active_tokens()
        group = self.route_group_for(normalized)

        acceptable_tokens: list[str] = []
        if group == "ocr" and tokens["ocr"] is not None:
            acceptable_tokens = [tokens["ocr"]]
        elif group == "translation" and tokens["translation"] is not None:
            acceptable_tokens = [tokens["translation"]]
        elif group == "transcription" and tokens["transcription"] is not None:
            acceptable_tokens = [tokens["transcription"]]
        elif tokens["global"] is not None:
            acceptable_tokens = [tokens["global"]]
        elif group == "other":
            # D2-01 audit fix: If global token is unset but one or more subsystem
            # tokens are active, protect management routes with active subsystem tokens
            # rather than leaving management routes completely unauthenticated.
            active_subsystems = [
                tok
                for tok in (
                    tokens["ocr"],
                    tokens["translation"],
                    tokens["transcription"],
                )
                if tok is not None
            ]
            if active_subsystems:
                acceptable_tokens = active_subsystems

        if not acceptable_tokens:
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
        cand = candidate.strip()
        if not any(secrets.compare_digest(cand, tok) for tok in acceptable_tokens):
            await _send_json(scope, receive, send, _UNAUTHORIZED, 401)
            return

        await self.app(scope, receive, send)


__all__ = [
    "_HEALTH_PATHS",
    "_INVALID_PATH",
    "_UNAUTHORIZED",
    "BearerAuthMiddleware",
    "_is_health_path",
    "_is_management_route",
    "_is_ocr_route",
    "_is_transcription_route",
    "_is_translation_route",
    "_normalize_path",
    "_normalize_token",
    "_send_json",
]
