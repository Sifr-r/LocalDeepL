"""Environment parsing contract for ``SecuritySettings.from_env``.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import logging

import pytest

from omniscribe.api.middleware.settings import (
    ABSOLUTE_MAX_UPLOAD_MB,
    DEFAULT_MAX_UPLOAD_MB,
    SecuritySettings,
)


def test_security_settings_parses_environment_defaults(monkeypatch):
    """Empty env ⇒ personal/local posture: no auth, no CORS, no rate limit.

    The default upload cap is the 10 GB minimum the size-limits tests
    pin (see ``test_size_limits.py``); we verify the *contract* of the
    parser here, not the specific Megabyte value.
    """
    monkeypatch.delenv("OMNISCRIBE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OMNISCRIBE_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("OMNISCRIBE_MAX_UPLOAD_MB", raising=False)
    monkeypatch.delenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", raising=False)

    settings = SecuritySettings.from_env()
    assert settings.auth_token is None
    assert settings.auth_enabled is False
    assert settings.cors_origins == []
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    assert settings.rate_limit_per_minute is None
    assert settings.rate_limit_enabled is False


def test_security_settings_cors_parses_csv_and_trims(monkeypatch):
    monkeypatch.setenv(
        "OMNISCRIBE_CORS_ORIGINS",
        "https://app.example.com, https://admin.example.com ,, ",
    )
    settings = SecuritySettings.from_env()
    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_security_settings_rate_limit_zero_disables(monkeypatch):
    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "0")
    settings = SecuritySettings.from_env()
    assert settings.rate_limit_per_minute is None
    assert settings.rate_limit_enabled is False


def test_security_settings_max_upload_clamps(monkeypatch):
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "999999")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == ABSOLUTE_MAX_UPLOAD_MB * 1024 * 1024

    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "0")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == 1 * 1024 * 1024


def test_security_settings_invalid_ints_fall_back_to_default(monkeypatch):
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "not-a-number")
    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "garbage")
    settings = SecuritySettings.from_env()
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
    assert settings.rate_limit_per_minute is None


# ---------------------------------------------------------------------------
# Per-service token loading (consolidated from tests/test_separate_auth.py)
# ---------------------------------------------------------------------------


def _clear_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OMNISCRIBE_AUTH_TOKEN",
        "OMNISCRIBE_OCR_AUTH_TOKEN",
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN",
        "OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_security_settings_loads_per_service_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_AUTH_TOKEN", "global-secret-with-sufficient-length-32"
    )
    monkeypatch.setenv(
        "OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret-with-sufficient-length-32"
    )
    monkeypatch.setenv(
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "translation-secret-with-sufficient-length"
    )

    settings = SecuritySettings.from_env()

    assert settings.auth_token == "global-secret-with-sufficient-length-32"
    assert settings.ocr_auth_token == "ocr-secret-with-sufficient-length-32"
    assert (
        settings.translation_auth_token == "translation-secret-with-sufficient-length"
    )
    assert settings.auth_enabled is True
    assert settings.ocr_auth_enabled is True
    assert settings.translation_auth_enabled is True


def test_security_settings_only_ocr_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret-with-sufficient-length-32"
    )

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token == "ocr-secret-with-sufficient-length-32"
    assert settings.translation_auth_token is None
    assert settings.auth_enabled is False
    assert settings.ocr_auth_enabled is True
    assert settings.translation_auth_enabled is False


def test_security_settings_only_translation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "translation-secret-with-sufficient-length"
    )

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token is None
    assert (
        settings.translation_auth_token == "translation-secret-with-sufficient-length"
    )
    assert settings.auth_enabled is False
    assert settings.translation_auth_enabled is True


def test_security_settings_empty_tokens_are_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_token_env(monkeypatch)
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
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_AUTH_TOKEN", "  trimmed-global-with-sufficient-length-32  "
    )
    monkeypatch.setenv(
        "OMNISCRIBE_OCR_AUTH_TOKEN", "  trimmed-ocr-with-sufficient-length-32  "
    )
    monkeypatch.setenv(
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "  trimmed-tr-with-sufficient-length-32  "
    )

    settings = SecuritySettings.from_env()

    assert settings.auth_token == "trimmed-global-with-sufficient-length-32"
    assert settings.ocr_auth_token == "trimmed-ocr-with-sufficient-length-32"
    assert settings.translation_auth_token == "trimmed-tr-with-sufficient-length-32"


def test_security_settings_no_env_returns_none_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_token_env(monkeypatch)

    settings = SecuritySettings.from_env()

    assert settings.auth_token is None
    assert settings.ocr_auth_token is None
    assert settings.translation_auth_token is None
    assert settings.auth_enabled is False


# ---------------------------------------------------------------------------
# M10: fail-fast on well-known placeholder auth tokens and short tokens
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
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(env_name, placeholder)

    with pytest.raises(RuntimeError):
        SecuritySettings.from_env()


@pytest.mark.parametrize(
    "env_name, short_val",
    [
        ("OMNISCRIBE_AUTH_TOKEN", "short"),
        ("OMNISCRIBE_AUTH_TOKEN", "a" * 31),
        ("OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-short-1234"),
        ("OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "trans-short-123"),
    ],
)
def test_security_settings_rejects_short_auth_token(
    monkeypatch: pytest.MonkeyPatch, env_name: str, short_val: str
) -> None:
    """Auth tokens shorter than MIN_AUTH_TOKEN_LENGTH (32 chars) must refuse boot."""
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(env_name, short_val)

    with pytest.raises(RuntimeError, match="too short"):
        SecuritySettings.from_env()


def test_security_settings_accepts_32_char_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real 32+ char secret is accepted verbatim, no fail-fast."""
    _clear_token_env(monkeypatch)
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
# F2.1 audit fix: from_env() warns at startup when some auth tokens are
# set but not all. The unset namespaces are unprotected and a
# misconfigured operator may believe they have locked everything.
# ---------------------------------------------------------------------------


def test_from_env_warns_when_only_some_namespace_tokens_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Mixed auth configuration: only OCR is set, translation/transcription unset.

    The startup warning names the unset namespaces and points the
    operator at the global token as the lock-everything knob.
    """
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret-with-sufficient-length-32"
    )

    with caplog.at_level(logging.WARNING, logger="omniscribe.api.middleware.settings"):
        SecuritySettings.from_env()

    warnings = [r for r in caplog.records if "Mixed auth configuration" in r.message]
    assert len(warnings) == 1
    msg = warnings[0].message
    assert "OMNISCRIBE_OCR_AUTH_TOKEN" in msg
    assert "OMNISCRIBE_TRANSLATION_AUTH_TOKEN" in msg
    assert "OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN" in msg


def test_from_env_silent_when_all_tokens_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """No mixed-config warning when all four tokens are set (or none)."""
    _clear_token_env(monkeypatch)
    monkeypatch.setenv(
        "OMNISCRIBE_AUTH_TOKEN", "global-secret-with-sufficient-length-32"
    )
    monkeypatch.setenv(
        "OMNISCRIBE_OCR_AUTH_TOKEN", "ocr-secret-with-sufficient-length-32"
    )
    monkeypatch.setenv(
        "OMNISCRIBE_TRANSLATION_AUTH_TOKEN", "translation-secret-with-sufficient-length"
    )
    monkeypatch.setenv(
        "OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN",
        "transcription-secret-with-sufficient-len",
    )

    with caplog.at_level(logging.WARNING, logger="omniscribe.api.middleware.settings"):
        SecuritySettings.from_env()

    warnings = [r for r in caplog.records if "Mixed auth configuration" in r.message]
    assert warnings == []


# ---------------------------------------------------------------------------
# F2.3 — upload deadline settings surface
# (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_security_settings_exposes_upload_deadline_s() -> None:
    """``SecuritySettings.upload_deadline_s`` carries the configured budget."""
    s = SecuritySettings()
    assert s.upload_deadline_s == 120.0


def test_security_settings_upload_deadline_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OMNISCRIBE_UPLOAD_DEADLINE_S`` overrides the default."""
    monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_S", "300.0")
    s = SecuritySettings.from_env()
    assert s.upload_deadline_s == 300.0


def test_security_settings_upload_deadline_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric deadline warns and falls back to the 120s default."""
    monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_S", "not-a-number")
    s = SecuritySettings.from_env()
    assert s.upload_deadline_s == 120.0


# ---------------------------------------------------------------------------
# F2.7 — _validate_auth_token redacts the token
# (re-homed from test_audit_medium_d2.py)
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
    from omniscribe.api.middleware.settings import _validate_auth_token

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
    from omniscribe.api.middleware.settings import _validate_auth_token

    with pytest.raises(RuntimeError) as exc_info:
        _validate_auth_token("OMNISCRIBE_OCR_AUTH_TOKEN", "short")
    msg = str(exc_info.value)
    assert "OMNISCRIBE_OCR_AUTH_TOKEN" in msg


def test_redact_token_handles_empty_string() -> None:
    """An empty input returns ``<empty>`` (defensive)."""
    from omniscribe.api.middleware.settings import _redact_token

    assert _redact_token("") == "<empty>"


def test_redact_token_shape_is_deterministic_for_same_input() -> None:
    """Same input produces the same redaction (operator can correlate)."""
    from omniscribe.api.middleware.settings import _redact_token

    sample = "abcdefghijklmnopqrstuvwxyz0123456789"  # 36 chars
    assert _redact_token(sample) == _redact_token(sample)
    assert "length=36" in _redact_token(sample)
    assert "first='a'" in _redact_token(sample)
    assert "last='9'" in _redact_token(sample)


def test_validate_auth_token_valid_token_returns_unchanged() -> None:
    """A valid-length, non-placeholder token is returned trimmed."""
    from omniscribe.api.middleware.settings import _validate_auth_token

    valid = "a" * 64
    assert _validate_auth_token("OMNISCRIBE_AUTH_TOKEN", valid) == valid
    # With surrounding whitespace.
    assert _validate_auth_token("OMNISCRIBE_AUTH_TOKEN", f"  {valid}  ") == valid


# ---------------------------------------------------------------------------
# F2.8 — CORS allowlist (re-homed from test_audit_medium_d2.py)
# ---------------------------------------------------------------------------


def test_security_settings_default_cors_methods_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default CORS methods are the explicit (non-wildcard) set."""
    from omniscribe.api.middleware.settings import (
        DEFAULT_CORS_ALLOWED_METHODS,
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
    from omniscribe.api.middleware.settings import (
        DEFAULT_CORS_ALLOWED_HEADERS,
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
    monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_METHODS", "GET,POST,PATCH")
    s = SecuritySettings.from_env()
    assert s.cors_allowed_methods == ["GET", "POST", "PATCH"]
    # Methods are upper-cased.
    assert all(m == m.upper() for m in s.cors_allowed_methods)


def test_security_settings_cors_wildcard_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A wildcard-only override warns and falls back to the default surface."""
    from omniscribe.api.middleware.settings import (
        DEFAULT_CORS_ALLOWED_HEADERS,
        DEFAULT_CORS_ALLOWED_METHODS,
    )

    with caplog.at_level(logging.WARNING, logger="omniscribe.api.middleware.settings"):
        monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_METHODS", "*")
        monkeypatch.setenv("OMNISCRIBE_CORS_ALLOWED_HEADERS", "*")
        s = SecuritySettings.from_env()
    assert s.cors_allowed_methods == sorted(DEFAULT_CORS_ALLOWED_METHODS)
    assert s.cors_allowed_headers == sorted(DEFAULT_CORS_ALLOWED_HEADERS)
    matching = [
        r for r in caplog.records if "OMNISCRIBE_CORS_ALLOWED" in r.getMessage()
    ]
    assert len(matching) == 2


def test_from_env_silent_when_no_tokens_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Dev default: no tokens at all is the legacy open mode and is silent."""
    _clear_token_env(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="omniscribe.api.middleware.settings"):
        SecuritySettings.from_env()

    warnings = [r for r in caplog.records if "Mixed auth configuration" in r.message]
    assert warnings == []
