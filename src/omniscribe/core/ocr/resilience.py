"""Resilience primitives for LLM endpoint calls: retry + circuit breaker.

Local VLM servers (LM Studio, Ollama, vLLM) occasionally return transient
errors mid-job — GPU OOM on one page, a model-swap restart, a brief rate
limit. Without retry, a single 500 degrades a page; without a circuit
breaker, a *dead* endpoint makes every remaining page wait for its full
timeout before failing. These two mechanisms compose:

- :func:`is_transient_error` classifies which exceptions are worth retrying.
- :class:`CircuitBreaker` tracks consecutive failures and fails fast once
  the endpoint is deemed down, with a half-open probe after a cooldown.

Tunables are env-driven (``OMNISCRIBE_LLM_MAX_RETRIES``,
``OMNISCRIBE_LLM_RETRY_BASE_DELAY``, ``OMNISCRIBE_CB_FAILURE_THRESHOLD``,
``OMNISCRIBE_CB_COOLDOWN``) so deployments can adapt without code changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    """Three-state model for :class:`CircuitBreaker`.

    ``CLOSED`` is the healthy default; ``OPEN`` blocks calls; ``HALF_OPEN``
    allows a single probe through after the cooldown expires. Inherits
    from :class:`StrEnum` so the enum value compares equal to its name in
    logs and serializes to its string form.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

# HTTP status codes that indicate a transient server-side condition.
# 425 Too Early (RFC 8470) is included: 0-RTT handshakes that the server
# rejects are safe to retry after a short backoff.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Python-level exception types that are never worth retrying — they
# indicate a local programming bug rather than an upstream outage.
# Listing them by type (not by message substring) catches the
# "keyerror for missing dict key" / "typeerror on bad arg" cases
# regardless of wording.
_PYTHON_BUG_EXCEPTION_TYPES = (
    KeyError,
    TypeError,
    AttributeError,
    NameError,
    IndexError,
    ValueError,
    AssertionError,
)

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
    Python-level bugs (KeyError, TypeError, AttributeError, ...) return
    ``False`` because retrying them only hides a real code defect.
    Unknown errors default to retryable: the cost of one extra attempt
    is small compared to silently degrading a page.
    """
    # Always-not-transient exception types (programming bugs).
    if isinstance(exc, _PYTHON_BUG_EXCEPTION_TYPES):
        return False

    # Status code: try the common attribute names. httpx.HTTPStatusError
    # exposes the status via ``.response.status_code``; OpenAI / LiteLLM
    # errors use ``.status_code`` directly. Walk both.
    status: int | None = None
    direct = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(direct, int):
        status = direct
    else:
        response = getattr(exc, "response", None)
        if response is not None:
            resp_status = getattr(response, "status_code", None)
            if isinstance(resp_status, int):
                status = resp_status

    if status is not None:
        if status in RETRYABLE_STATUS_CODES:
            return True
        if 400 <= status < 500:
            # 4xx other than RETRYABLE_STATUS_CODES is a client-side permanent failure.
            return False

    msg = str(exc).lower()
    if any(term in msg for term in _PERMANENT_TERMS):
        return False
    if any(term in msg for term in _TRANSIENT_TERMS):
        return True

    # Timeout exceptions from httpx/openai/litellm without a status code.
    if "timeout" in msg or "timed out" in msg:
        return True

    # Bare generic exceptions (RuntimeError / Exception with no signal in
    # the message) are NOT worth retrying: an unidentified RuntimeError
    # is almost always a code bug or an upstream API edge case that
    # retrying will not resolve. Treat as permanent.
    # Default: retry unknown non-RuntimeError exceptions once rather
    # than degrade silently.
    return not isinstance(exc, RuntimeError)


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
        env_threshold = os.getenv("OMNISCRIBE_CB_FAILURE_THRESHOLD")
        env_cooldown = os.getenv("OMNISCRIBE_CB_COOLDOWN")
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
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current breaker state.

        ``OPEN`` while the cooldown is still in effect; ``HALF_OPEN`` once
        the cooldown has elapsed (a single probe is allowed through);
        ``CLOSED`` when the breaker is healthy. The state is recomputed on
        each read using :attr:`_clock` so the transition to ``HALF_OPEN``
        is observed lazily without a background timer.
        """
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock() - self._opened_at < self.cooldown_seconds:
            return CircuitState.OPEN
        return CircuitState.HALF_OPEN

    @property
    def is_open(self) -> bool:
        """True when the breaker is in the ``OPEN`` state (cooldown not yet
        expired). Prefer :attr:`state` for explicit ``CLOSED`` / ``OPEN`` /
        ``HALF_OPEN`` introspection; this bool property is kept for
        back-compat with call sites that only need a yes/no answer."""
        return self.state is CircuitState.OPEN

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def check(self) -> None:
        """Raise :class:`CircuitOpenError` if the circuit is open."""
        async with self._lock:
            if self.is_open:
                assert self._opened_at is not None
                retry_after = self.cooldown_seconds - (self._clock() - self._opened_at)
                raise CircuitOpenError(
                    self._consecutive_failures, max(0.0, retry_after)
                )

    async def record_success(self) -> None:
        """Record a successful call; closes the circuit if it was probing."""
        async with self._lock:
            if self._opened_at is not None:
                logger.info("LLM circuit breaker closed after successful probe")
            self._consecutive_failures = 0
            self._opened_at = None

    async def record_failure(self) -> None:
        """Record a failed call; opens the circuit at the threshold.

        A failure while half-open (cooldown expired, probe in flight)
        immediately re-opens the circuit with a fresh cooldown.
        """
        async with self._lock:
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

    # Async-friendly shims. Async OCR call sites awaiting the breaker
    # API surface are first-class: pipeline code uniformly awaits
    # ``cb.acheck()`` / ``cb.arecord_failure()`` regardless of whether
    # the underlying implementation needs the event loop. The shims
    # simply proxy to the synchronous implementations when there is
    # no actual awaitable work; the registry's lock guarantees the
    # bookkeeping stays consistent even under concurrent awaits.
    async def acheck(self) -> None:
        await self.check()

    async def arecord_success(self) -> None:
        await self.record_success()

    async def arecord_failure(self) -> None:
        await self.record_failure()


class CircuitBreakerRegistry:
    """Process-wide pool of :class:`CircuitBreaker` keyed by endpoint.

    Two ``OCRProcessor`` instances constructed against the same
    ``(api_base, model)`` should share a circuit breaker: a breaker
    tripped by one processor must be visible to a second processor
    that started after the first had already exhausted its retries. A
    dedicated registry makes this sharing explicit; the default
    registry returned by :func:`get_default_circuit_breaker_registry`
    is a process-wide singleton so production pipeline runs naturally
    share breakers across HTTP requests.

    Thread-safety: the registry holds a :class:`threading.Lock` for
    registration / lookup, held only for the duration of a dict
    mutation so contention is minimal.
    """

    def __init__(self) -> None:
        self._breakers: dict[tuple[str, str], CircuitBreaker] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(api_base: str, model: str) -> tuple[str, str]:
        return (api_base, model)

    def get_or_create(self, api_base: str, model: str) -> CircuitBreaker:
        """Return the breaker for ``(api_base, model)``; create on first call."""
        key = self._key(api_base, model)
        with self._lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker()
                self._breakers[key] = breaker
            return breaker

    def get(self, api_base: str, model: str) -> CircuitBreaker | None:
        """Return the breaker for ``(api_base, model)`` or ``None`` if absent."""
        with self._lock:
            return self._breakers.get(self._key(api_base, model))

    def clear(self) -> None:
        """Drop every registered breaker. Test helper."""
        with self._lock:
            self._breakers.clear()


_default_registry: CircuitBreakerRegistry | None = None
_default_registry_lock = threading.Lock()


def get_default_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Return the process-wide default :class:`CircuitBreakerRegistry`.

    Lazily constructed on first call; subsequent calls return the
    same instance so two ``OCRProcessor`` objects built from
    different request handlers share one breaker when configured
    against the same endpoint.
    """
    global _default_registry
    if _default_registry is None:
        with _default_registry_lock:
            if _default_registry is None:
                _default_registry = CircuitBreakerRegistry()
    return _default_registry


def reset_default_circuit_breaker_registry() -> None:
    """Drop the default registry. Test helper."""
    global _default_registry
    with _default_registry_lock:
        _default_registry = None


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "CircuitState",
    "get_default_circuit_breaker_registry",
    "is_transient_error",
    "reset_default_circuit_breaker_registry",
]
