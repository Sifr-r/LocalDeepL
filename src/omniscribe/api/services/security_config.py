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
            _LOGGER.warning(
                "Ignoring invalid CIDR %r in %s: %s", candidate, name, exc
            )
    return networks


def _validate_auth_token(env_name: str, token: str | None) -> str | None:
    """Trim and fail-fast on well-known placeholder values.

    Returns the trimmed token (or None for unset/whitespace). Raises
    ``RuntimeError`` if the supplied value is a known placeholder so a
    copy-pasted ``.env`` never lets the server come up with an
    attacker-guessable credential.
    """
    if token is None:
        return None
    trimmed = token.strip()
    if not trimmed:
        return None
    if trimmed.lower() in PLACEHOLDER_AUTH_TOKENS:
        raise RuntimeError(
            f"{env_name}={token!r} is a well-known placeholder auth token; "
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
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
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
        max_mb = _env_int("OMNISCRIBE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)
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

        return SecuritySettings(
            auth_token=token,
            ocr_auth_token=ocr_token,
            translation_auth_token=translation_token,
            transcription_auth_token=transcription_token,
            cors_origins=origins,
            max_upload_bytes=max_mb * 1024 * 1024,
            rate_limit_per_minute=rate,
            trusted_proxies=_env_cidr_list("OMNISCRIBE_TRUSTED_PROXIES"),
        )
