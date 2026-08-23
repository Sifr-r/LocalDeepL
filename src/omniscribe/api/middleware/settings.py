"""
Runtime security settings for the FastAPI web app.

All knobs are environment-driven so the same codebase can run in
"personal/local-only" mode (no env vars needed) or in "exposed to
untrusted users" mode where the host sets every guard.

Adding a new knob:
  1. Add a parser in `_env_<type>` below.
  2. Add the field to `SecuritySettings`.
  3. Add the loader line to `from_env`.
  4. Use it from `create_app()` (server.py) so the app boots with the
     correct middleware.

Three auth-token env vars are recognised:

* ``OMNISCRIBE_AUTH_TOKEN`` — global fallback applied to every route.
* ``OMNISCRIBE_OCR_AUTH_TOKEN`` — overrides the global token for OCR
  routes (``/api/process``, ``/api/models/ocr``, ``/api/config/ocr``).
  When set, the global token does **not** unlock those routes.
* ``OMNISCRIBE_TRANSLATION_AUTH_TOKEN`` — overrides the global token
  for translation routes (``/api/translate``, ``/api/extract``,
  ``/api/export``, ``/api/glossary``, ``/api/models/translation``,
  ``/api/config/translation``). When set, the global token does
  **not** unlock those routes.

The defaults match the historical "localhost dev" posture: no auth,
no CORS, no size cap beyond Starlette's defaults, no rate limit.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from typing import Final

_LOGGER = logging.getLogger(__name__)

# Default upload cap. 10 GB is generous for OCR PDFs — most scans are
# 2-20 MB, but the file picker must not silently hide the option to
# ingest very large image/PDF collections. Hosts serving across the
# public internet should set this explicitly to whatever they want
# to commit disk + memory to honouring.
DEFAULT_MAX_UPLOAD_MB: Final[int] = 10_240

# Hard ceiling regardless of what the env says. Prevents a typo from
# allowing clients to OOM the server with a 10-TB upload.
ABSOLUTE_MAX_UPLOAD_MB: Final[int] = 102_400

# Tokens that operators sometimes copy-paste from a tutorial. Any of
# these in any of the three auth-token env vars causes startup to
# refuse with a clear ``RuntimeError``. The same denylist is re-applied
# by ``POST /api/config/ocr/auth`` so a runtime override cannot
# downgrade the boot-time guard.
PLACEHOLDER_AUTH_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "change-me-in-prod",
        "change-me",
        "changeme",
        "change-me-in-production",
        "password",
        "secret",
        "admin",
        "root",
        "example",
        "sample",
        "default",
        "test",
        "your-token-here",
        "your-secret-here",
        "your-token",
        "your-secret",
        "your-api-key",
        "your-api-key-here",
        "your-key",
        "your-key-here",
        "your-password",
        "your-password-here",
        "yourpass",
        "yourpasshere",
        "yourpass-here",
        "yourpassword",
        "yourpasswordhere",
        "yourpassword-here",
        "your-token-please",
        "your-token-please-change",
        "your-secret-please",
        "your-secret-please-change",
        "your-secret-please-change-me",
        "your-token-please-change-me",
        "your-token-please-change-me-in-prod",
        "your-secret-please-change-me-in-prod",
        "your-token-please-change-me-in-production",
        "your-secret-please-change-me-in-production",
    }
)

# Minimum acceptable length for a real auth token. Anything shorter is
# either too easy to brute-force or is the masked preview that the
# config endpoint returns ("abcd...wxyz"), and we reject it on the
# Pydantic layer before the custom denylist runs.
MIN_AUTH_TOKEN_LENGTH: Final[int] = 32

# F2.8 audit fix: explicit CORS surface. The previous code used
# ``allow_methods=["*"], allow_headers=["*"]`` with the wildcard
# always-on. With ``allow_credentials=False`` the classic CORS
# misconfig is blocked (the spec refuses ``Allow-Credentials: true``
# with a wildcard origin), but the wildcard surface is still wider
# than necessary: an attacker that already has an allow-listed origin
# can put any verb or any custom header into a cross-origin request
# and the server will answer it. The defaults below are the minimum
# surface the OmniScribe workstation UI needs. Operators can
# override per-deployment via ``OMNISCRIBE_CORS_ALLOWED_METHODS`` /
# ``OMNISCRIBE_CORS_ALLOWED_HEADERS`` (comma-separated) without
# touching the source.
DEFAULT_CORS_ALLOWED_METHODS: Final[frozenset[str]] = frozenset(
    {"GET", "POST", "PUT", "DELETE", "OPTIONS"}
)
DEFAULT_CORS_ALLOWED_HEADERS: Final[frozenset[str]] = frozenset(
    {"Authorization", "Content-Type", "X-Requested-With"}
)


def _legacy_name(name: str) -> str:
    if name.startswith("OMNISCRIBE_"):
        return "LOCAL_DEEPL_" + name[len("OMNISCRIBE_") :]
    return name


def _env_str(name: str) -> str | None:
    """Read a trimmed string env var. Checks OMNISCRIBE_* then legacy LOCAL_DEEPL_*."""
    value = os.getenv(name)
    if value is None and name != _legacy_name(name):
        value = os.getenv(_legacy_name(name))
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None and name != _legacy_name(name):
        value = os.getenv(_legacy_name(name))
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        _LOGGER.warning("Ignoring invalid integer environment value for %s", name)
        return default


def _env_float(name: str, default: float) -> float | None:
    """Read a float env var. Returns ``None`` on parse error so the caller can warn + fallback.

    The historical int helper falls back to the default silently;
    floats need a separate signal so the caller can distinguish
    "unset" (default) from "set but unparseable" (warn + default).
    """
    value = os.getenv(name)
    if value is None and name != _legacy_name(name):
        value = os.getenv(_legacy_name(name))
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return None


def _env_list_csv(name: str) -> list[str]:
    """Read a comma-separated list. Trims each item; drops empties."""
    raw = os.getenv(name)
    if not raw and name != _legacy_name(name):
        raw = os.getenv(_legacy_name(name))
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_cidr_list(name: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Read a comma-separated list of CIDR ranges.

    Drops invalid entries with a warning rather than silently widening
    to "trust all" or rejecting the whole var. An empty list preserves
    the historical peer-only behaviour.
    """
    import ipaddress

    raw = os.getenv(name)
    if not raw and name != _legacy_name(name):
        raw = os.getenv(_legacy_name(name))
    if not raw:
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError as exc:
            _LOGGER.warning("Ignoring invalid CIDR %r in %s: %s", candidate, name, exc)
    return networks


def _redact_token(value: str) -> str:
    """Return ``<redacted length=N first=… last=…>`` for use in error messages.

    F2.7 audit fix: the previous formatter embedded the offending
    token in the startup ``RuntimeError`` (both the too-short and the
    placeholder branches). A misconfigured ``.env`` + a log
    aggregator / Sentry / cloud log sink is enough to leak the
    credential. We log only the *shape* of the value — its length
    and the first / last character — so an operator can correlate
    against the env var they typed, but a log scraper cannot
    recover the secret.
    """
    if not value:
        return "<empty>"
    first = value[0]
    last = value[-1]
    return f"<redacted length={len(value)} first={first!r} last={last!r}>"


def _validate_auth_token(env_name: str, token: str | None) -> str | None:
    """Trim and fail-fast on well-known placeholder values or short tokens.

    Returns the trimmed token (or None for unset/whitespace). Raises
    ``RuntimeError`` if the supplied value is a known placeholder or shorter
    than ``MIN_AUTH_TOKEN_LENGTH`` so a copy-pasted ``.env`` never lets the
    server come up with an attacker-guessable credential. The error
    message embeds the *shape* of the offending value (length, first
    and last character) but never the value itself, so a log scraper
    cannot recover the secret.
    """
    if token is None:
        return None
    trimmed = token.strip()
    if not trimmed:
        return None
    redacted = _redact_token(trimmed)
    if len(trimmed) < MIN_AUTH_TOKEN_LENGTH:
        raise RuntimeError(
            f"{env_name}={redacted} is too short (length {len(trimmed)}); "
            f"refusing to boot. Auth tokens must be at least {MIN_AUTH_TOKEN_LENGTH} characters."
        )
    if trimmed.lower() in PLACEHOLDER_AUTH_TOKENS:
        raise RuntimeError(
            f"{env_name}={redacted} is a well-known placeholder auth token; "
            "refusing to boot. Set a real, high-entropy secret (>= "
            f"{MIN_AUTH_TOKEN_LENGTH} chars)."
        )
    return trimmed


@dataclass
class SecuritySettings:
    """Runtime security knobs. Construct via `SecuritySettings.from_env()`."""

    auth_token: str | None = None
    ocr_auth_token: str | None = None
    translation_auth_token: str | None = None
    transcription_auth_token: str | None = None
    cors_origins: list[str] = field(default_factory=list)
    cors_allowed_methods: list[str] = field(
        default_factory=lambda: sorted(DEFAULT_CORS_ALLOWED_METHODS)
    )
    cors_allowed_headers: list[str] = field(
        default_factory=lambda: sorted(DEFAULT_CORS_ALLOWED_HEADERS)
    )
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    upload_deadline_s: float = 120.0
    rate_limit_per_minute: int | None = None
    trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = field(
        default_factory=list
    )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_token)

    @property
    def ocr_auth_enabled(self) -> bool:
        return bool(self.ocr_auth_token)

    @property
    def translation_auth_enabled(self) -> bool:
        return bool(self.translation_auth_token)

    @property
    def transcription_auth_enabled(self) -> bool:
        return bool(self.transcription_auth_token)

    @property
    def any_auth_enabled(self) -> bool:
        return (
            self.auth_enabled
            or self.ocr_auth_enabled
            or self.translation_auth_enabled
            or self.transcription_auth_enabled
        )

    @property
    def rate_limit_enabled(self) -> bool:
        return self.rate_limit_per_minute is not None and self.rate_limit_per_minute > 0

    def is_trusted_proxy(self, peer_ip: str) -> bool:
        """True when ``peer_ip`` is contained in any configured trusted CIDR.

        Returns False on unparseable input rather than raising — the
        rate limiter should fail-closed to the peer IP, not crash.
        """
        try:
            address = ipaddress.ip_address(peer_ip)
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxies)

    @staticmethod
    def from_env() -> SecuritySettings:
        """Build settings from ``OMNISCRIBE_*`` environment variables.

        Recognised variables:
          * ``OMNISCRIBE_AUTH_TOKEN`` — global fallback applied to every
            route. Setting it is the simplest "lock the door" knob.
          * ``OMNISCRIBE_OCR_AUTH_TOKEN`` — overrides the global token
            for OCR routes. When set, the global token does not unlock
            OCR routes.
          * ``OMNISCRIBE_TRANSLATION_AUTH_TOKEN`` — same as above for
            translation routes.
          * ``OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN`` — same as above for
            transcription routes.
          * ``OMNISCRIBE_CORS_ORIGINS`` — comma-separated allowlist for
            cross-origin browser requests. Empty = same-origin only.
          * ``OMNISCRIBE_MAX_UPLOAD_MB`` — reject request bodies above
            this many megabytes. Default 10240 (10 GB), capped at
            102400 (100 GB).
          * ``OMNISCRIBE_RATE_LIMIT_PER_MIN`` — per-client-IP HTTP
            request cap, sliding 60s window. Set to 0 or unset to
            disable.
        """
        token = _validate_auth_token(
            "OMNISCRIBE_AUTH_TOKEN", _env_str("OMNISCRIBE_AUTH_TOKEN")
        )
        ocr_token = _validate_auth_token(
            "OMNISCRIBE_OCR_AUTH_TOKEN",
            _env_str("OMNISCRIBE_OCR_AUTH_TOKEN"),
        )
        translation_token = _validate_auth_token(
            "OMNISCRIBE_TRANSLATION_AUTH_TOKEN",
            _env_str("OMNISCRIBE_TRANSLATION_AUTH_TOKEN"),
        )
        transcription_token = _validate_auth_token(
            "OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN",
            _env_str("OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN"),
        )
        origins = _env_list_csv("OMNISCRIBE_CORS_ORIGINS")
        # F2.8 audit fix: explicit CORS surface. We accept operator
        # overrides via ``OMNISCRIBE_CORS_ALLOWED_METHODS`` /
        # ``OMNISCRIBE_CORS_ALLOWED_HEADERS`` (comma-separated, case
        # preserved) and fall back to the documented defaults above.
        # We deliberately drop ``"*"`` if the operator copy-pastes the
        # previous code's wildcard — the whole point of the audit fix
        # is to keep that off the wire. HTTP method names are
        # upper-cased per RFC 7230 §3.1.1; header names are passed
        # through and the middleware itself is case-insensitive on
        # match.
        raw_methods = _env_list_csv("OMNISCRIBE_CORS_ALLOWED_METHODS")
        if raw_methods:
            cors_methods = [m for m in raw_methods if m != "*"]
            if not cors_methods:
                _LOGGER.warning(
                    "OMNISCRIBE_CORS_ALLOWED_METHODS contained only '*'; "
                    "falling back to defaults %s",
                    sorted(DEFAULT_CORS_ALLOWED_METHODS),
                )
                cors_methods = sorted(DEFAULT_CORS_ALLOWED_METHODS)
            else:
                cors_methods = [m.upper() for m in cors_methods]
        else:
            cors_methods = sorted(DEFAULT_CORS_ALLOWED_METHODS)
        raw_headers = _env_list_csv("OMNISCRIBE_CORS_ALLOWED_HEADERS")
        if raw_headers:
            cors_headers = [h for h in raw_headers if h != "*"]
            if not cors_headers:
                _LOGGER.warning(
                    "OMNISCRIBE_CORS_ALLOWED_HEADERS contained only '*'; "
                    "falling back to defaults %s",
                    sorted(DEFAULT_CORS_ALLOWED_HEADERS),
                )
                cors_headers = sorted(DEFAULT_CORS_ALLOWED_HEADERS)
            else:
                cors_headers = list(cors_headers)
        else:
            cors_headers = sorted(DEFAULT_CORS_ALLOWED_HEADERS)
        max_mb = _env_int("OMNISCRIBE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)
        # F2.3 audit fix: per-request wall-clock budget for chunked
        # uploads. Default 120s (see ``MaxUploadSizeMiddleware``). A
        # legitimate 100 GB upload at 100 MB/s finishes in ~17
        # minutes, so the 2-minute default has comfortable headroom
        # for healthy clients; a slow-trickle attacker burns the
        # budget in seconds. Operators can extend the budget for
        # known-slow network paths via
        # ``OMNISCRIBE_UPLOAD_DEADLINE_S``.
        upload_deadline_s = _env_float("OMNISCRIBE_UPLOAD_DEADLINE_S", 120.0)
        if upload_deadline_s is None or upload_deadline_s <= 0:
            _LOGGER.warning(
                "OMNISCRIBE_UPLOAD_DEADLINE_S=%r is invalid; falling back to 120s",
                upload_deadline_s,
            )
            upload_deadline_s = 120.0
        if max_mb < 1:
            _LOGGER.warning(
                "OMNISCRIBE_MAX_UPLOAD_MB=%d is below 1; clamping to 1",
                max_mb,
            )
            max_mb = 1
        if max_mb > ABSOLUTE_MAX_UPLOAD_MB:
            _LOGGER.warning(
                "OMNISCRIBE_MAX_UPLOAD_MB=%d exceeds absolute cap %d; clamping",
                max_mb,
                ABSOLUTE_MAX_UPLOAD_MB,
            )
            max_mb = ABSOLUTE_MAX_UPLOAD_MB
        rate_raw = os.getenv("OMNISCRIBE_RATE_LIMIT_PER_MIN")
        rate: int | None
        if rate_raw is None or rate_raw.strip() == "":
            rate = None
        else:
            try:
                rate = int(rate_raw.strip())
            except ValueError:
                _LOGGER.warning(
                    "Ignoring invalid integer environment value for %s",
                    "OMNISCRIBE_RATE_LIMIT_PER_MIN",
                )
                rate = None
            if rate is not None and rate < 0:
                rate = None
        if rate == 0:
            rate = None

        # F2.1 audit fix: when some auth tokens are set but not all,
        # the unset namespaces are unprotected. Warn the operator at
        # boot so the "I set one token and expected everything to be
        # locked" footgun is loud. The default dev mode (no token
        # set) is silent. The "all four set" case is also silent.
        _token_state: list[tuple[str, str | None]] = [
            ("OMNISCRIBE_AUTH_TOKEN (global)", token),
            ("OMNISCRIBE_OCR_AUTH_TOKEN", ocr_token),
            ("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", translation_token),
            ("OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN", transcription_token),
        ]
        _set = [name for name, value in _token_state if value is not None]
        _unset = [name for name, value in _token_state if value is None]
        if _set and _unset:
            _LOGGER.warning(
                "Mixed auth configuration: %s are set but %s are unset. "
                "The unset namespaces will be OPEN (no auth required "
                "for any route in that group, including the related "
                "data routes). To lock every route, set "
                "OMNISCRIBE_AUTH_TOKEN (the global token) or set a "
                "token for every namespace. Management routes "
                "(/api/jobs/*, /api/providers/*, /api/progress/*, "
                "/api/config/*) only accept the global token, not "
                "per-namespace tokens, regardless of which "
                "namespaces are locked.",
                ", ".join(_set),
                ", ".join(_unset),
            )

        return SecuritySettings(
            auth_token=token,
            ocr_auth_token=ocr_token,
            translation_auth_token=translation_token,
            transcription_auth_token=transcription_token,
            cors_origins=origins,
            cors_allowed_methods=cors_methods,
            cors_allowed_headers=cors_headers,
            max_upload_bytes=max_mb * 1024 * 1024,
            upload_deadline_s=upload_deadline_s,
            rate_limit_per_minute=rate,
            trusted_proxies=_env_cidr_list("OMNISCRIBE_TRUSTED_PROXIES"),
        )
