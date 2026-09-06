"""Structured logging configuration for the OmniScribe web server.

Addresses audit finding **A-17** (no structured logging). The existing
codebase already uses ``logging.getLogger(__name__)`` across the
:mod:`omniscribe` package, so adopting structured output does NOT require
touching every call site — only the root handler configuration. Every
existing ``logger.info("foo")`` will emit a JSON object with
``timestamp``, ``level``, ``logger``, and ``message`` plus any
``extra={...}`` keyword arguments the caller passed.

Two output formats are supported:

* ``json`` (default) — one JSON object per line, suitable for log
  aggregators (Loki, Elasticsearch, Datadog, CloudWatch).
* ``text`` — the standard ``logging`` human-readable format. Useful for
  local development where JSON is noisy.

Configure with the ``OMNISCRIBE_LOG_FORMAT`` and ``OMNISCRIBE_LOG_LEVEL``
environment variables. Idempotent: a second call is a no-op so importing
this module from a test does not clobber the user's handler.

Implementation notes:

* We deliberately use :class:`logging.Formatter` (stdlib) instead of
  pulling in ``structlog`` — the latter would require rewriting every
  call site to wrap loggers, which is out of scope for this iteration.
* The JSON formatter is stdlib-only (no ``python-json-logger`` dep),
  keeps the deploy surface small, and produces a stable shape.
* ``exc_info`` (set automatically when callers pass ``exc_info=True``)
  is rendered as a stack trace string under the ``exc_info`` key.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from omniscribe.config import load_settings

__all__ = [
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "JsonFormatter",
    "configure_logging",
    "is_configured",
]

DEFAULT_LOG_FORMAT: Final[str] = "json"
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)
_VALID_FORMATS: Final[frozenset[str]] = frozenset({"json", "text"})

_configured = False


def is_configured() -> bool:
    """Return ``True`` if :func:`configure_logging` has been called."""
    return _configured


def _resolve_log_level(value: str | None) -> int:
    """Map a level name (or ``None``) to a stdlib ``logging`` level int."""
    candidate = (value or DEFAULT_LOG_LEVEL).upper()
    if candidate not in _VALID_LEVELS:
        raise ValueError(
            f"Unknown log level: {candidate!r}. "
            f"Expected one of: {sorted(_VALID_LEVELS)}"
        )
    return logging.getLevelNamesMapping()[candidate]


def _resolve_log_format(value: str | None) -> str:
    """Map a format name (or ``None``) to ``"json"`` or ``"text"``."""
    candidate = (value or DEFAULT_LOG_FORMAT).lower()
    if candidate not in _VALID_FORMATS:
        raise ValueError(
            f"Unknown log format: {candidate!r}. "
            f"Expected one of: {sorted(_VALID_FORMATS)}"
        )
    return candidate


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    The shape is deliberately minimal and stable:

    * ``timestamp`` — ISO 8601 UTC timestamp.
    * ``level`` — level name (``INFO``, ``WARNING``, …).
    * ``logger`` — the logger name (typically ``module.submodule``).
    * ``message`` — the formatted message string.
    * ``exc_info`` — string-formatted traceback when present.
    * Any extras passed via ``logger.info(..., extra={"key": value})``
      are merged into the top-level object.
    """

    # Standard ``LogRecord`` attributes we don't want to leak into the
    # JSON payload as their own keys. Anything not in this set is
    # treated as caller-supplied ``extra={...}`` data.
    _RESERVED_KEYS: Final[frozenset[str]] = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
    )

    _SENSITIVE_KEYS: frozenset[str] = frozenset(
        {
            "password",
            "token",
            "auth_token",
            "secret",
            "api_key",
            "apikey",
            "key",
            "credential",
            "credentials",
            "private_key",
            "access_token",
            "refresh_token",
            "authorization",
            "client_secret",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # Surface caller-supplied ``extra={...}`` at the top level so
        # request IDs and job IDs land in the same JSON object as the
        # message they annotate. Scrub sensitive credential fields.
        for key, value in record.__dict__.items():
            if key in self._RESERVED_KEYS or key.startswith("_"):
                continue
            if key in payload:
                # Don't clobber the canonical fields above.
                continue
            if key.lower() in self._SENSITIVE_KEYS:
                payload[key] = "<redacted>"
            else:
                payload[key] = _jsonable(value)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _jsonable(value: object) -> object:
    """Best-effort coercion of ``extra`` values to JSON-friendly types.

    Mirrors the behaviour of :func:`json.dumps`'s ``default`` callback so
    the formatter can be reused outside :class:`JsonFormatter` (e.g.
    custom error responses). Datetimes become ISO strings, ``Path``
    objects become ``str``, and anything else falls through to ``repr``
    via :func:`json.dumps`'s own ``default``.

    Values that are already JSON-serialisable (numbers, strings, bools,
    None, lists, dicts) are returned unchanged so int ``7`` stays int
    ``7`` rather than becoming the string ``"7"``.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str, list, tuple, dict)):
        return value
    return str(value)


def configure_logging(
    *,
    level: str | None = None,
    fmt: str | None = None,
    stream: Any | None = None,
) -> None:
    """Configure the root logger for structured output.

    Idempotent: a second call updates the existing handler instead of
    stacking duplicates. ``level`` and ``fmt`` are resolved against the
    ``OMNISCRIBE_LOG_LEVEL`` / ``OMNISCRIBE_LOG_FORMAT`` env vars when
    not supplied explicitly (so :func:`os.getenv` is the single source
    of truth at startup).
    """
    global _configured

    settings = load_settings()
    resolved_level = _resolve_log_level(
        level if level is not None else settings.log_level
    )
    resolved_fmt = _resolve_log_format(fmt if fmt is not None else settings.log_format)
    target_stream = stream if stream is not None else sys.stderr

    handler: logging.Handler | None = None
    root = logging.getLogger()
    for existing in root.handlers:
        if getattr(existing, "_omniscribe_configured", False):
            handler = existing
            break

    if handler is None:
        new_handler = logging.StreamHandler(target_stream)
        new_handler.setLevel(resolved_level)
        new_handler._omniscribe_configured = True  # type: ignore[attr-defined]
        root.addHandler(new_handler)
        handler = new_handler
    else:
        handler.setLevel(resolved_level)
        # ``Handler.stream`` exists on ``StreamHandler`` (where we install
        # our handler) but isn't part of the abstract ``Handler`` base.
        stream_attr = getattr(handler, "stream", None)
        if stream_attr is not target_stream:
            handler.stream = target_stream  # type: ignore[attr-defined]

    if resolved_fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root.setLevel(resolved_level)
    # ``omniscribe`` package loggers bubble up to root by default; we
    # only need to enforce a sane ceiling on the noisy third-party
    # loggers (uvicorn, httpx, asyncio) so they don't drown the JSON
    # stream.
    for noisy_name in ("uvicorn.access", "httpx", "asyncio"):
        logging.getLogger(noisy_name).setLevel(max(resolved_level, logging.INFO))
    _configured = True


def merge_extras(
    base: Mapping[str, object] | None,
    **overrides: object,
) -> dict[str, object]:
    """Merge ``overrides`` into ``base`` for ``logger.*(extra=...)`` calls.

    Convenience helper so call sites can spread request/job IDs into the
    structured payload without manually constructing a new dict every
    time. Returns a fresh dict so the caller can safely mutate it.
    """
    merged: dict[str, object] = dict(base) if base else {}
    merged.update(overrides)
    return merged
