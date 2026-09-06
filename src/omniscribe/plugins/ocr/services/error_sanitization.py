"""Job error sanitization for the OCR service.

Extracted from ``plugins/ocr/service.py`` in Phase 3.8 (4.8,
2026-09-05). The previous ``service.py`` mixed route-adjacent
helpers, error-sanitization regexes, content-type sniffing, service
implementation, SSE event formatting, and config seeding in one
~890-LOC file. This module owns the sanitization surface area.

Public surface:

- :func:`sanitize_job_error` — the single public entry point. Returns
  a redacted, user-safe string or ``None`` if the input was ``None``.

Everything else (the regexes, the path-replacement helper) is private
to this module. The pattern constants are kept module-private so that
adding a new secret-shaped token does not require touching any caller.
"""

from __future__ import annotations

import re

#: Traceback signature that, if present in the error, means the raw
#: Python traceback leaked. We replace the whole error with a generic
#: "internal processing error" string in that case.
_TRACEBACK_MARKERS: tuple[str, ...] = ("Traceback (most recent call last):",)
_TRACEBACK_FILE_PATTERN: re.Pattern[str] = re.compile(r'File\s+["\'][^"\']+["\']')

#: Database-driver error keywords that indicate a raw SQL / storage
#: layer failure. Replaced with a generic "storage error" message.
_DB_ERROR_PATTERNS: tuple[str, ...] = (
    "sqlite3.",
    "syntax error near",
    "operationalerror",
    "integrityerror",
    "databaseerror",
    "programmingerror",
)

#: ``Authorization: ...`` header line in any case / with optional scheme.
_AUTH_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r'(?i)\b(authorization\s*:\s*(?:bearer\s+|basic\s+)?)[^\s"\'\,]+'
)

#: Bare ``bearer <token>`` sequence (e.g. in a URL or a log line).
_BEARER_PATTERN: re.Pattern[str] = re.compile(r'(?i)\b(bearer\s+)[^\s"\'\,]+')

#: ``api_key=...`` / ``access_token=...`` / ``secret=...`` style
#: assignments. Captures the key, the separator (``=`` or ``:``), the
#: optional quote, the value, and the closing quote (matched against
#: the open quote group via backref) so we can re-emit the structure
#: without the value.
_SECRET_KEY_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|secret|token|password)"
    r'(\s*[:=]\s*)(["\']?)[^\s"\'\,]+(\3)'
)

#: OpenAI-style ``sk-...`` / ``pk-...`` keys (16+ chars after the dash).
_SK_PATTERN: re.Pattern[str] = re.compile(r"\b(?:sk|pk)[-_][a-zA-Z0-9_\-]{16,}\b")

#: Internal file paths: Windows ``C:\...`` / UNC ``\\host\share\...`` /
#: Unix ``/tmp/...``, ``/home/...``, etc. Replaced with ``[path]``.
_PATH_PATTERN: re.Pattern[str] = re.compile(
    r'(?:[A-Za-z]:[\\/]|\\\\|/(?:tmp|home|var|usr|etc|opt|root|Users|private)/)[^"\'\s]+'
)


def _replace_path(match: re.Match[str]) -> str:
    """Strip trailing punctuation from a matched path before replacing it."""
    path_str = match.group(0)
    trailing = ""
    while path_str and path_str[-1] in ":;,.)]":
        trailing = path_str[-1] + trailing
        path_str = path_str[:-1]
    return f"[path]{trailing}"


def sanitize_job_error(error: str | None) -> str | None:
    """Sanitize a job error string to prevent leaking internal details.

    Redacts tracebacks, raw database errors, internal filesystem
    paths, and credentials/tokens, while preserving clean known-safe
    error messages. The output is safe to surface in
    :class:`JobStatusResponse` and the SSE event stream.

    The function is the single public entry point; everything else in
    this module is implementation detail. Audit test:
    ``tests/plugins/ocr/test_service_sanitization.py`` (or equivalent)
    should cover each replacement class.
    """
    if not error:
        return error

    # 1. Traceback signatures -> generic internal error
    if any(
        marker in error for marker in _TRACEBACK_MARKERS
    ) or _TRACEBACK_FILE_PATTERN.search(error):
        return "An internal processing error occurred."

    # 2. Raw database error keywords -> generic storage error
    lower = error.lower()
    if any(pat in lower for pat in _DB_ERROR_PATTERNS):
        return "A storage error occurred."

    # 3. Strip secret / token references
    sanitized = _AUTH_HEADER_PATTERN.sub(r"\1[redacted]", error)
    sanitized = _BEARER_PATTERN.sub(r"\1[redacted]", sanitized)
    sanitized = _SECRET_KEY_PATTERN.sub(r"\1\2\3[redacted]\4", sanitized)
    sanitized = _SK_PATTERN.sub("[redacted]", sanitized)

    # 4. Scrub internal file paths -> [path]
    sanitized = _PATH_PATTERN.sub(_replace_path, sanitized)

    return sanitized


__all__ = ["sanitize_job_error"]
