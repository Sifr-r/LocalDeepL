"""Canonical error envelope contract."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.services.envelope import (
    APIError,
    BackendUnavailable,
    ErrorEnvelope,
    NotFound,
    RateLimited,
    SSRFBlocked,
    ValidationFailed,
    envelope_error,
    register_envelope_handlers,
)


def test_envelope_model_drops_none_detail() -> None:
    env = ErrorEnvelope(error="forbidden")
    assert env.model_dump(exclude_none=True) == {"error": "forbidden"}


def test_envelope_error_returns_canonical_shape() -> None:
    resp = envelope_error(status_code=403, error="forbidden", detail="no access")
    assert resp.status_code == 403
    body: dict[str, Any] = json.loads(resp.body)
    assert body == {"error": "forbidden", "detail": "no access"}


def test_envelope_error_omits_detail_when_none() -> None:
    resp = envelope_error(status_code=503, error="unavailable")
    body: dict[str, Any] = json.loads(resp.body)
    assert body == {"error": "unavailable"}


@pytest.mark.parametrize(
    "exc_cls",
    [SSRFBlocked, BackendUnavailable, NotFound, RateLimited, ValidationFailed],
)
def test_api_error_subclasses_carry_defaults(exc_cls: type[APIError]) -> None:
    exc = exc_cls(url="x", reason="y") if exc_cls is SSRFBlocked else exc_cls("x")
    assert exc.status_code >= 400
    assert exc.error != "internal_error"
    assert exc.detail is not None


def test_ssrf_blocked_carries_url_and_reason() -> None:
    err = SSRFBlocked(url="http://localhost:6379", reason="loopback")
    assert err.url == "http://localhost:6379"
    assert err.reason == "loopback"
    assert err.status_code == 403
    assert "loopback" in err.detail


def test_register_envelope_handlers_converts_apierror() -> None:
    app = FastAPI()
    register_envelope_handlers(app)

    @app.get("/boom")
    async def _boom() -> None:
        raise SSRFBlocked(url="http://10.0.0.1", reason="private")

    client = TestClient(app)
    resp = client.get("/boom")
    assert resp.status_code == 403
    assert resp.json() == {
        "error": "ssrf_blocked",
        "detail": "URL targets a blocked address: private",
    }


def test_register_envelope_handlers_converts_request_validation() -> None:
    app = FastAPI()
    register_envelope_handlers(app)

    @app.get("/echo/{n}")
    async def _echo(n: int) -> dict[str, int]:
        return {"n": n}

    client = TestClient(app)
    resp = client.get("/echo/notanumber")
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_failed"
    assert "detail" in body
    assert resp.headers.get("x-validation-errors") == "1"
