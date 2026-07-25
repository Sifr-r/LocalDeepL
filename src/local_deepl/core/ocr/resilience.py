"""Resilience primitives for LLM endpoint calls: retry + circuit breaker.

Local VLM servers (LM Studio, Ollama, vLLM) occasionally return transient
errors mid-job — GPU OOM on one page, a model-swap restart, a brief rate
limit. Without retry, a single 500 degrades a page; without a circuit
breaker, a *dead* endpoint makes every remaining page wait for its full
timeout before failing. These two mechanisms compose:

- :func:`is_transient_error` classifies which exceptions are worth retrying.
- :class:`CircuitBreaker` tracks consecutive failures and fails fast once
  the endpoint is deemed down, with a half-open probe after a cooldown.

Tunables are env-driven (``LOCAL_DEEPL_LLM_MAX_RETRIES``,
``LOCAL_DEEPL_LLM_RETRY_BASE_DELAY``, ``LOCAL_DEEPL_CB_FAILURE_THRESHOLD``,
``LOCAL_DEEPL_CB_COOLDOWN``) so deployments can adapt without code changes.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# HTTP status codes that indicate a transient server-side condition.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Substrings in error messages that indicate transient transport failures.
_TRANSIENT_TERMS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "overloaded",
    "server overloaded",
    "connection reset",
    "connection refused",
    "connection aborted",
    "connection error",
    "connecterror",
    "remote end closed connection",
    "eof occurred",
    "broken pipe",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
    "readtimeout",
    "connecttimeout",
    "network failure",
    "econnreset",
    "econnrefused",
)

# Substrings that indicate a permanent condition — never retry these.
_PERMANENT_TERMS = (
    "context size",
    "context_length_exceeded",
    "context length",
    "maximum context",
    "invalid api key",
    "unauthorized",
    "authentication",
    "permission denied",
    "model not found",
    "does not exist",
    "invalid request",
)


def is_transient_error(exc: BaseException) -> bool:
    """Classify whether an LLM call exception is worth retrying.

    Permanent failures (context-length exceeded, auth, invalid model)
    return ``False`` — retrying them wastes time and budget. Transient
    failures (rate limits, 5xx, connection drops, timeouts) return ``True``.
    Unknown errors default to retryable: the cost of one extra attempt is
    small compared to silently degrading a page.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int):
        if status in RETRYABLE_STATUS_CODES:
            return True
        if 400 <= status < 500:
            # 4xx other than 429 is a client-side permanent failure.
            return False

    msg = str(exc).lower()
    if any(term in msg for term in _PERMANENT_TERMS):
        return False
    if any(term in msg for term in _TRANSIENT_TERMS):
        return True

    # Timeout exceptions from httpx/openai/litellm without a status code.
    if "timeout" in msg or "timed out" in msg:
        return True

    # Default: retry unknown errors once rather than degrade silently.
    return True


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is open and calls fail fast.

    Subclasses ``RuntimeError`` (not ``LLMCallError``) so callers that
    catch ``LLMCallError`` for per-page degradation still see this as a
    distinct, infrastructure-level condition.
    """

    def __init__(self, failures: int, retry_after: float) -> None:
        self.failures = failures
        self.retry_after = retry_after
        super().__init__(
            f"LLM endpoint circuit breaker open after {failures} consecutive "
            f"failures; retrying in {retry_after:.0f}s"
        )


class CircuitBreaker:
    """Per-endpoint circuit breaker with closed / open / half-open states.

    - **Closed** (healthy): calls pass through; each failure increments the
      counter; a success resets it.
    - **Open** (down): calls fail fast with :class:`CircuitOpenError` until
      the cooldown expires.
    - **Half-open** (probing): the first call after cooldown is allowed
      through; success closes the circuit, failure re-opens it.

    Thread-safety note: instances are per-request (constructed with the
    ``OCRProcessor``), and calls within a request are serialized through
    the retry loop, so no locking is required.
    """

    def __init__(
        self,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        env_threshold = os.getenv("LOCAL_DEEPL_CB_FAILURE_THRESHOLD")
        env_cooldown = os.getenv("LOCAL_DEEPL_CB_COOLDOWN")
        self.failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else int(env_threshold)
            if env_threshold
            else 5
        )
        self.cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else float(env_cooldown)
            if env_cooldown
            else 30.0
        )
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        """True when the breaker is open AND the cooldown has not expired."""
        if self._opened_at is None:
            return False
        # Cooldown elapsed → half-open: allow a probe through.
        return self._clock() - self._opened_at < self.cooldown_seconds

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def check(self) -> None:
        """Raise :class:`CircuitOpenError` if the circuit is open."""
        if self.is_open:
            assert self._opened_at is not None
            retry_after = self.cooldown_seconds - (self._clock() - self._opened_at)
            raise CircuitOpenError(self._consecutive_failures, max(0.0, retry_after))

    def record_success(self) -> None:
        """Record a successful call; closes the circuit if it was probing."""
        if self._opened_at is not None:
            logger.info("LLM circuit breaker closed after successful probe")
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call; opens the circuit at the threshold.

        A failure while half-open (cooldown expired, probe in flight)
        immediately re-opens the circuit with a fresh cooldown.
        """
        self._consecutive_failures += 1
        if self._opened_at is not None:
            # Half-open probe failed → re-open with a fresh cooldown.
            self._opened_at = self._clock()
            logger.warning(
                "LLM circuit breaker re-opened after failed probe "
                "(%d consecutive failures, cooldown %.0fs)",
                self._consecutive_failures,
                self.cooldown_seconds,
            )
        elif self._consecutive_failures >= self.failure_threshold:
            self._opened_at = self._clock()
            logger.warning(
                "LLM circuit breaker OPEN after %d consecutive failures "
                "(cooldown %.0fs)",
                self._consecutive_failures,
                self.cooldown_seconds,
            )


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "CircuitBreaker",
    "CircuitOpenError",
    "is_transient_error",
]
