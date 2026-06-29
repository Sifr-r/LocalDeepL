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

The defaults match the historical "localhost dev" posture: no auth,
no CORS, no size cap beyond Starlette's defaults, no rate limit.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Final

_LOGGER = logging.getLogger(__name__)

# Default upload cap. 100 MB is generous for OCR PDFs — most scans are
# 2-20 MB. Hosts serving across the public internet should set this
# explicitly to whatever they want to commit disk + memory to honouring.
DEFAULT_MAX_UPLOAD_MB: Final[int] = 100

# Hard ceiling regardless of what the env says. Prevents a typo from
# allowing clients to OOM the server with a single 100-GB upload.
ABSOLUTE_MAX_UPLOAD_MB: Final[int] = 1_024


def _env_str(name: str) -> str | None:
    """Read a trimmed string env var. None if unset or empty after strip."""
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
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
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class SecuritySettings:
    """Runtime security knobs. Construct via `SecuritySettings.from_env()`."""

    auth_token: str | None = None
    cors_origins: list[str] = field(default_factory=list)
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    rate_limit_per_minute: int | None = None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_token)

    @property
    def rate_limit_enabled(self) -> bool:
        return self.rate_limit_per_minute is not None and self.rate_limit_per_minute > 0

    @staticmethod
    def from_env() -> SecuritySettings:
        """Build settings from ``LOCAL_DEEPL_*`` environment variables.

        Recognised variables:
          * ``LOCAL_DEEPL_AUTH_TOKEN`` - if set, every request must
            carry ``Authorization: Bearer <token>``.
          * ``LOCAL_DEEPL_CORS_ORIGINS`` - comma-separated allowlist for
            cross-origin browser requests. Empty = same-origin only.
          * ``LOCAL_DEEPL_MAX_UPLOAD_MB`` - reject request bodies above
            this many megabytes. Default 100, capped at 1024.
          * ``LOCAL_DEEPL_RATE_LIMIT_PER_MIN`` - per-client-IP HTTP
            request cap, sliding 60s window. Set to 0 or unset to
            disable.
        """
        token = _env_str("LOCAL_DEEPL_AUTH_TOKEN")
        origins = _env_list_csv("LOCAL_DEEPL_CORS_ORIGINS")
        max_mb = _env_int("LOCAL_DEEPL_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)
        if max_mb < 1:
            _LOGGER.warning(
                "LOCAL_DEEPL_MAX_UPLOAD_MB=%d is below 1; clamping to 1",
                max_mb,
            )
            max_mb = 1
        if max_mb > ABSOLUTE_MAX_UPLOAD_MB:
            _LOGGER.warning(
                "LOCAL_DEEPL_MAX_UPLOAD_MB=%d exceeds absolute cap %d; clamping",
                max_mb,
                ABSOLUTE_MAX_UPLOAD_MB,
            )
            max_mb = ABSOLUTE_MAX_UPLOAD_MB
        rate_raw = os.getenv("LOCAL_DEEPL_RATE_LIMIT_PER_MIN")
        rate: int | None
        if rate_raw is None or rate_raw.strip() == "":
            rate = None
        else:
            try:
                rate = int(rate_raw.strip())
            except ValueError:
                _LOGGER.warning(
                    "Ignoring invalid integer environment value for %s",
                    "LOCAL_DEEPL_RATE_LIMIT_PER_MIN",
                )
                rate = None
            if rate is not None and rate < 0:
                rate = None
        if rate == 0:
            rate = None

        return SecuritySettings(
            auth_token=token,
            cors_origins=origins,
            max_upload_bytes=max_mb * 1024 * 1024,
            rate_limit_per_minute=rate,
        )
