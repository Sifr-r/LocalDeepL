"""Tests for the structured-logging configuration (audit A-17).

The configuration module is intentionally tiny but we lock down the
contract so future refactors don't regress the JSON shape or the env
resolution rules.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime

import pytest

from omniscribe.utils import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    JsonFormatter,
    configure_logging,
    is_configured,
    merge_extras,
)
from omniscribe.utils.structured_logging import (
    _resolve_log_format,
    _resolve_log_level,
)


@pytest.fixture(autouse=True)
def _isolate_root_logger() -> None:  # type: ignore[misc]
    """Snapshot / restore the root logger around each test.

    ``configure_logging`` mutates ``logging.getLogger().handlers`` and
    the root level. Without this fixture, individual tests would leak
    handlers into each other and pytest's own log capture would lose
    records.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_disabled = root.disabled
    # Reset module-level ``_configured`` flag so each test exercises
    # the full configure path.
    import omniscribe.utils.structured_logging as sl

    sl._configured = False
    try:
        yield
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        root.disabled = saved_disabled
        sl._configured = False


def _make_stream() -> io.StringIO:
    return io.StringIO()


def test_json_formatter_emits_canonical_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="omniscribe.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "omniscribe.test"
    assert payload["message"] == "hello world"
    # Timestamp is ISO 8601 UTC with timezone offset, parseable round-trip.
    parsed = datetime.fromisoformat(payload["timestamp"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_json_formatter_includes_extras_at_top_level() -> None:
    formatter = JsonFormatter()
    # Build the LogRecord directly so the test does not depend on
    # pytest's log-capture plumbing (which can interfere with handler
    # wiring in some configurations). ``extra=...`` is the same keyword
    # Python's logging uses to surface caller-supplied fields on the
    # record's ``__dict__``.
    record = logging.LogRecord(
        name="omniscribe.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="processing page",
        args=None,
        exc_info=None,
    )
    record.request_id = "abc-123"
    record.page = 7
    payload = json.loads(formatter.format(record))
    assert payload["request_id"] == "abc-123"
    assert payload["page"] == 7


def test_json_formatter_renders_exception_traceback() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="omniscribe.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=None,
            exc_info=sys_exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "exc_info" in payload
    assert "ValueError: boom" in payload["exc_info"]


def test_json_formatter_does_not_leak_internal_attributes() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="omniscribe.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hi",
        args=None,
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    # Internal LogRecord plumbing must not surface in the JSON output.
    for forbidden in ("args", "pathname", "lineno", "process", "thread"):
        assert forbidden not in payload


def test_configure_logging_installs_json_formatter_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNISCRIBE_LOG_FORMAT", raising=False)
    monkeypatch.delenv("OMNISCRIBE_LOG_LEVEL", raising=False)
    buffer = _make_stream()

    configure_logging(stream=buffer)

    assert is_configured() is True
    root = logging.getLogger()
    assert root.level == logging.INFO
    # The configured handler is the one carrying the JSON formatter and
    # routing to the supplied stream.
    handler = next(
        h for h in root.handlers if getattr(h, "_omniscribe_configured", False)
    )
    assert isinstance(handler.formatter, JsonFormatter)
    assert handler.stream is buffer  # type: ignore[attr-defined]


def test_configure_logging_text_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNISCRIBE_LOG_FORMAT", "text")
    monkeypatch.setenv("OMNISCRIBE_LOG_LEVEL", "DEBUG")
    buffer = _make_stream()

    configure_logging(stream=buffer)

    handler = next(
        h
        for h in logging.getLogger().handlers
        if getattr(h, "_omniscribe_configured", False)
    )
    assert not isinstance(handler.formatter, JsonFormatter)
    logging.getLogger("omniscribe.test").info("hello")
    assert "hello" in buffer.getvalue()


def test_configure_logging_rejects_unknown_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_LOG_FORMAT", "yaml")
    with pytest.raises(ValueError, match="Unknown log format"):
        configure_logging()


def test_configure_logging_rejects_unknown_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_LOG_LEVEL", "LOUD")
    with pytest.raises(ValueError, match="Unknown log level"):
        configure_logging()


def test_configure_logging_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated calls must not stack handlers on the root logger."""
    monkeypatch.setenv("OMNISCRIBE_LOG_FORMAT", "json")

    configure_logging()
    configure_logging()
    configure_logging()

    configured = [
        h
        for h in logging.getLogger().handlers
        if getattr(h, "_omniscribe_configured", False)
    ]
    assert len(configured) == 1


def test_resolve_log_level_defaults() -> None:
    assert _resolve_log_level(None) == logging.getLevelNamesMapping()[DEFAULT_LOG_LEVEL]
    assert _resolve_log_level("DEBUG") == logging.DEBUG
    assert _resolve_log_level("CRITICAL") == logging.CRITICAL


def test_resolve_log_format_defaults() -> None:
    assert _resolve_log_format(None) == DEFAULT_LOG_FORMAT
    assert _resolve_log_format("JSON") == "json"
    assert _resolve_log_format("text") == "text"


def test_merge_extras_returns_fresh_dict() -> None:
    base = {"request_id": "abc"}
    merged = merge_extras(base, page=5)
    assert merged == {"request_id": "abc", "page": 5}
    # Mutating the merged dict does not affect the original.
    merged["page"] = 99
    assert base["request_id"] == "abc"
    assert "page" not in base


def test_merge_extras_with_none_base() -> None:
    assert merge_extras(None, request_id="xyz") == {"request_id": "xyz"}


def test_configure_logging_lowers_third_party_loggers() -> None:
    """uvicorn.access / httpx / asyncio must not drown the JSON stream."""
    configure_logging()
    for name in ("uvicorn.access", "httpx", "asyncio"):
        logger = logging.getLogger(name)
        assert logger.level >= logging.INFO


def test_json_formatter_uses_utc_timezone() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="omniscribe.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=None,
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    # Stored as offset-aware ISO; compare against current UTC instant.
    parsed = datetime.fromisoformat(payload["timestamp"])
    delta = abs((datetime.now(UTC) - parsed).total_seconds())
    assert delta < 5.0  # within 5 seconds


def test_json_formatter_scrubs_sensitive_keys() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="omniscribe.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login attempt",
        args=None,
        exc_info=None,
    )
    record.auth_token = "secret-token-12345"
    record.api_key = "sk-1234567890abcdef"
    record.password = "hunter2"
    record.request_id = "safe-request-id"

    payload = json.loads(formatter.format(record))
    assert payload["auth_token"] == "<redacted>"
    assert payload["api_key"] == "<redacted>"
    assert payload["password"] == "<redacted>"
    assert payload["request_id"] == "safe-request-id"


# Helper that returns the current ``sys.exc_info()`` triple so we can
# build a LogRecord with ``exc_info`` populated. Indirected because the
# actual ``raise`` must happen outside the helper to attach the traceback
# to the right frame.
def sys_exc_info():
    import sys

    return sys.exc_info()
