"""Tests for LLM call resilience: retry with backoff + circuit breaker (R-O1/R-O2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from local_deepl.core.ocr.exceptions import LLMCallError
from local_deepl.core.ocr.processor import OCRProcessor
from local_deepl.core.ocr.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    is_transient_error,
)

# ---------------------------------------------------------------------------
# is_transient_error classification
# ---------------------------------------------------------------------------


class _FakeHTTPError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


@pytest.mark.parametrize(
    "exc",
    [
        _FakeHTTPError("rate limit reached", 429),
        _FakeHTTPError("Internal Server Error", 500),
        _FakeHTTPError("Bad Gateway", 502),
        _FakeHTTPError("Service Unavailable", 503),
        _FakeHTTPError("Gateway Timeout", 504),
        _FakeHTTPError("Connection reset by peer"),
        _FakeHTTPError("Connection refused"),
        _FakeHTTPError("ReadTimeout: timed out after 240s"),
        _FakeHTTPError("The server is overloaded"),
        _FakeHTTPError("some unknown vendor quirk"),  # default: retryable
    ],
)
def test_transient_errors_are_retryable(exc):
    assert is_transient_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        _FakeHTTPError("context_length_exceeded: max 8192 tokens"),
        _FakeHTTPError("This model's maximum context size is 8192"),
        _FakeHTTPError("Invalid API key provided", 401),
        _FakeHTTPError("permission denied for this resource", 403),
        _FakeHTTPError("model not found: typo/model", 404),
        _FakeHTTPError("Unauthorized"),
        _FakeHTTPError("invalid request: bad image format", 400),
    ],
)
def test_permanent_errors_are_not_retryable(exc):
    assert is_transient_error(exc) is False


# ---------------------------------------------------------------------------
# CircuitBreaker state machine
# ---------------------------------------------------------------------------


def test_breaker_stays_closed_below_threshold():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    cb.check()  # should not raise
    assert cb.consecutive_failures == 2


def test_breaker_opens_at_threshold():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
    for _ in range(3):
        cb.record_failure()
    with pytest.raises(CircuitOpenError, match="3 consecutive"):
        cb.check()


def test_breaker_resets_on_success():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0)
    cb.record_failure()
    cb.record_success()
    assert cb.consecutive_failures == 0
    cb.record_failure()
    cb.check()  # only 1 consecutive failure — still closed


def test_breaker_half_open_after_cooldown():
    now = [0.0]
    cb = CircuitBreaker(
        failure_threshold=2, cooldown_seconds=30.0, clock=lambda: now[0]
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open

    # Advance past cooldown → half-open: check() passes a probe through.
    now[0] = 31.0
    assert not cb.is_open
    cb.check()  # probe allowed


def test_breaker_closes_after_successful_probe():
    now = [0.0]
    cb = CircuitBreaker(
        failure_threshold=2, cooldown_seconds=30.0, clock=lambda: now[0]
    )
    cb.record_failure()
    cb.record_failure()
    now[0] = 31.0
    cb.record_success()
    assert cb.consecutive_failures == 0
    cb.check()  # fully closed


def test_breaker_reopens_after_failed_probe():
    now = [0.0]
    cb = CircuitBreaker(
        failure_threshold=2, cooldown_seconds=30.0, clock=lambda: now[0]
    )
    cb.record_failure()
    cb.record_failure()
    now[0] = 31.0
    cb.record_failure()  # probe failed
    with pytest.raises(CircuitOpenError):
        cb.check()


# ---------------------------------------------------------------------------
# OCRProcessor._chat retry integration
# ---------------------------------------------------------------------------


def _make_processor() -> OCRProcessor:
    p = OCRProcessor(api_base="http://test:1234/v1", api_key="k", model="m")
    p.MAX_RETRIES = 2
    p.RETRY_BASE_DELAY_S = 0.001  # keep tests fast
    p.RETRY_MAX_DELAY_S = 0.01
    p.circuit_breaker = CircuitBreaker(failure_threshold=50, cooldown_seconds=1.0)
    return p


async def test_chat_retries_transient_error_and_succeeds():
    p = _make_processor()
    mock_call = AsyncMock(
        side_effect=[
            _FakeHTTPError("Internal Server Error", 500),
            "  recovered text  ",
        ]
    )
    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        result = await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)

    assert result == "recovered text"
    assert mock_call.call_count == 2


async def test_chat_exhausts_retries_then_raises_llm_call_error():
    p = _make_processor()
    mock_call = AsyncMock(side_effect=_FakeHTTPError("Service Unavailable", 503))
    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        with pytest.raises(LLMCallError, match="Service Unavailable"):
            await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)

    assert mock_call.call_count == 3  # 1 initial + 2 retries


async def test_chat_does_not_retry_permanent_context_size_error():
    p = _make_processor()
    mock_call = AsyncMock(
        side_effect=_FakeHTTPError("context_length_exceeded: 12000 > 8192")
    )
    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        with pytest.raises(LLMCallError, match="Context Size Limit"):
            await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)

    assert mock_call.call_count == 1  # no retries


async def test_chat_does_not_retry_auth_error():
    p = _make_processor()
    mock_call = AsyncMock(side_effect=_FakeHTTPError("Invalid API key", 401))
    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        with pytest.raises(LLMCallError, match="Invalid API key"):
            await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)

    assert mock_call.call_count == 1


async def test_circuit_breaker_fails_fast_after_consecutive_failures():
    p = _make_processor()
    p.circuit_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
    mock_call = AsyncMock(side_effect=_FakeHTTPError("Connection refused"))

    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        # First call: 3 attempts all fail → breaker at 3 → open.
        with pytest.raises(LLMCallError):
            await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)
        assert mock_call.call_count == 3

        # Second call: circuit open → fails fast, zero LLM calls.
        with pytest.raises(CircuitOpenError, match="circuit breaker open"):
            await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)
        assert mock_call.call_count == 3  # unchanged


async def test_successful_call_resets_breaker_for_next_page():
    p = _make_processor()
    p.circuit_breaker = CircuitBreaker(failure_threshold=4, cooldown_seconds=60.0)

    transient = _FakeHTTPError("Bad Gateway", 502)
    mock_call = AsyncMock(side_effect=[transient, transient, "ok", "ok"])

    with patch("local_deepl.core.ocr.processor.call_llm", mock_call):
        result = await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)
        assert result == "ok"
        # 2 failures then success → breaker reset to 0.
        assert p.circuit_breaker.consecutive_failures == 0

        result = await p._chat("prompt", "aW1n", timeout=10, max_tokens=100)
        assert result == "ok"
