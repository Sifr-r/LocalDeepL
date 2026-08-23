"""Tests for the §3b unknown-exception default flip + §8 408 status code."""

from __future__ import annotations

import httpx

from omniscribe.core.ocr.resilience import (
    RETRYABLE_STATUS_CODES,
    is_transient_error,
)

# §3b: Python-bug exceptions are NOT worth retrying.


def test_key_error_is_not_transient():
    assert is_transient_error(KeyError("missing")) is False


def test_type_error_is_not_transient():
    assert is_transient_error(TypeError("bad arg")) is False


def test_attribute_error_is_not_transient():
    assert is_transient_error(AttributeError("no such attr")) is False


def test_runtime_error_unknown_message_is_not_transient():
    assert is_transient_error(RuntimeError("totally unknown thing")) is False


def test_runtime_error_connection_reset_is_transient():
    assert is_transient_error(RuntimeError("connection reset")) is True


def test_runtime_error_context_length_is_permanent():
    assert is_transient_error(RuntimeError("context_length_exceeded")) is False


def test_runtime_error_invalid_api_key_is_permanent():
    assert is_transient_error(RuntimeError("Invalid API key provided")) is False


def test_runtime_error_authentication_is_permanent():
    assert is_transient_error(RuntimeError("authentication failed")) is False


def test_runtime_error_model_not_found_is_permanent():
    assert is_transient_error(RuntimeError("model not found: foo")) is False


# §8: 408 (Request Timeout) and 425 (Too Early) are retryable status codes.


def test_408_is_retryable_status_code():
    assert 408 in RETRYABLE_STATUS_CODES


def test_425_is_retryable_status_code():
    """RFC 8470: 0-RTT rejections are safe to retry."""
    assert 425 in RETRYABLE_STATUS_CODES


def test_retryable_status_codes_contains_all_expected():
    assert frozenset({408, 425, 429, 500, 502, 503, 504}) == RETRYABLE_STATUS_CODES


def test_408_status_error_is_transient():
    exc = httpx.HTTPStatusError(
        "Request Timeout",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(408),
    )
    assert is_transient_error(exc) is True


def test_425_status_error_is_transient():
    exc = httpx.HTTPStatusError(
        "Too Early",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(425),
    )
    assert is_transient_error(exc) is True


def test_429_status_error_is_transient():
    exc = httpx.HTTPStatusError(
        "Too Many Requests",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(429),
    )
    assert is_transient_error(exc) is True


def test_500_status_error_is_transient():
    exc = httpx.HTTPStatusError(
        "Server Error",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(500),
    )
    assert is_transient_error(exc) is True


def test_401_status_error_is_not_transient():
    exc = httpx.HTTPStatusError(
        "Unauthorized",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(401),
    )
    assert is_transient_error(exc) is False


def test_404_status_error_is_not_transient():
    exc = httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "http://x"),
        response=httpx.Response(404),
    )
    assert is_transient_error(exc) is False
