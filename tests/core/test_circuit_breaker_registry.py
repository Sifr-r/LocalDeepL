"""Tests for the CircuitBreakerRegistry (§3a)."""

from __future__ import annotations

import pytest

from omniscribe.core.ocr.processor import OCRProcessor
from omniscribe.core.ocr.resilience import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    get_default_circuit_breaker_registry,
)


def test_get_or_create_returns_same_instance_per_key():
    reg = CircuitBreakerRegistry()
    b1 = reg.get_or_create(api_base="http://a/v1", model="m")
    b2 = reg.get_or_create(api_base="http://a/v1", model="m")
    assert b1 is b2
    assert isinstance(b1, CircuitBreaker)


def test_get_or_create_distinguishes_model():
    reg = CircuitBreakerRegistry()
    b1 = reg.get_or_create(api_base="http://a/v1", model="m1")
    b2 = reg.get_or_create(api_base="http://a/v1", model="m2")
    assert b1 is not b2


def test_get_or_create_distinguishes_api_base():
    reg = CircuitBreakerRegistry()
    b1 = reg.get_or_create(api_base="http://a/v1", model="m")
    b2 = reg.get_or_create(api_base="http://b/v1", model="m")
    assert b1 is not b2


async def test_breaker_open_state_visible_to_fresh_caller():
    """Sharing: a breaker tripped by one caller is open for another."""
    reg = CircuitBreakerRegistry()
    cb = reg.get_or_create(api_base="http://a/v1", model="m")
    for _ in range(5):
        await cb.record_failure()
    # A "fresh caller" using the same registry sees the same tripped breaker.
    cb_fresh = reg.get_or_create(api_base="http://a/v1", model="m")
    with pytest.raises(CircuitOpenError):
        await cb_fresh.check()


def test_default_registry_is_module_singleton():
    reg1 = get_default_circuit_breaker_registry()
    reg2 = get_default_circuit_breaker_registry()
    assert reg1 is reg2


def test_ocr_processors_share_breaker_for_same_endpoint():
    """§3a — two OCRProcessors against the same (api_base, model) must
    share one circuit breaker."""
    reg = CircuitBreakerRegistry()
    p1 = OCRProcessor(
        api_base="http://test:1234/v1",
        api_key="k",
        model="m",
        circuit_breaker_registry=reg,
    )
    p2 = OCRProcessor(
        api_base="http://test:1234/v1",
        api_key="k",
        model="m",
        circuit_breaker_registry=reg,
    )
    assert p1.circuit_breaker is p2.circuit_breaker


def test_ocr_processors_distinct_for_different_models():
    reg = CircuitBreakerRegistry()
    p1 = OCRProcessor(
        api_base="http://test:1234/v1",
        api_key="k",
        model="m1",
        circuit_breaker_registry=reg,
    )
    p2 = OCRProcessor(
        api_base="http://test:1234/v1",
        api_key="k",
        model="m2",
        circuit_breaker_registry=reg,
    )
    assert p1.circuit_breaker is not p2.circuit_breaker
