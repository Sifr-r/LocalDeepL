"""Every swept error site in routers/config.py must return the canonical envelope shape.

Phase C / Task 2: refactor ``routers/config.py`` so every
``JSONResponse(status_code=..., content={"error": ...})`` site is replaced
with a typed envelope exception (``SSRFBlocked`` for the 403 SSRF sites,
``BackendUnavailable`` for the 503 ``_ConfigBackendIncompatible`` sites).

The 8 SSRF sites + 6 503 sites enumerated below were located by reading
``src/omniscribe/api/routers/config.py`` after the Phase C Task 1
canonical envelope landed. Auth endpoints (``/api/config/*/auth``) have
no SSRF check (they only persist ``auth_token``); their 503 site is
covered by ``test_503_site_returns_envelope`` below. The transcription
models route does not exist in this router.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import config as config_module
from omniscribe.api.routers.config import _ConfigBackendIncompatible
from omniscribe.api.routers.config import router as config_router
from omniscribe.api.routers.providers import router as providers_router
from omniscribe.api.routers.transcription import router as transcription_router
from omniscribe.api.services.envelope import (
    BackendUnavailable,
    SSRFBlocked,
    register_envelope_handlers,
)
from omniscribe.utils.security import SSRFCheckResult


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(config_router)
    return TestClient(app)


def _denied_ssrf() -> SSRFCheckResult:
    return SSRFCheckResult(allowed=False, resolved_ip=None, reason="loopback")


# ---------------------------------------------------------------------------
# SSRF sweep — 8 sites across 5 routes.
# ---------------------------------------------------------------------------
#
#   POST /api/config            : line 488-489 (1 site)
#   POST /api/config/ocr        : line 534 → 583 (1 site, via _is_ssrf)
#   GET  /api/models            : lines 773-774, 786-788 (2 sites)
#   GET  /api/models/ocr        : lines 812-814, 824-825 (2 sites)
#   GET  /api/models/translation: lines 848-850, 860-861 (2 sites)
#
# Each row is one HTTP call against the swept route. The patched
# ``is_ssrf_target`` always denies, so whichever SSRF branch the route
# enters first turns into a 403 envelope.
SSRF_CASES = [
    pytest.param(
        "POST",
        "/api/config",
        {"api_base": "http://127.0.0.1:1"},
        id="POST /api/config",
    ),
    pytest.param(
        "POST",
        "/api/config/ocr",
        {"ocr_api_base": "http://127.0.0.1:1"},
        id="POST /api/config/ocr",
    ),
    pytest.param("GET", "/api/models", None, id="GET /api/models"),
    pytest.param("GET", "/api/models/ocr", None, id="GET /api/models/ocr"),
    pytest.param(
        "GET", "/api/models/translation", None, id="GET /api/models/translation"
    ),
]


@pytest.mark.parametrize("method,path,payload", SSRF_CASES)
def test_ssrf_site_returns_envelope(
    client: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    """Mock ``is_ssrf_target`` to deny; assert 403 + canonical envelope."""
    with patch.object(
        config_module,
        "is_ssrf_target",
        new=AsyncMock(return_value=_denied_ssrf()),
    ):
        if method == "GET":
            resp = client.get(path)
        else:
            assert payload is not None
            resp = client.post(path, json=payload)

    assert resp.status_code == 403, (
        f"{method} {path}: expected 403, got {resp.status_code} body={resp.text}"
    )
    body: dict[str, Any] = resp.json()
    assert body == {
        "error": "ssrf_blocked",
        "detail": "URL targets a blocked address: loopback",
    }, f"{method} {path}: envelope shape mismatch: {body}"


# ---------------------------------------------------------------------------
# 503 sweep — 6 sites across 6 routes.
# ---------------------------------------------------------------------------
#
#   POST /api/config                       : lines 509-512
#   POST /api/config/ocr                   : lines 587-590
#   POST /api/config/translation           : lines 630-633
#   POST /api/config/ocr/auth              : lines 663-666
#   POST /api/config/translation/auth      : lines 680-683
#   POST /api/config/transcription/auth    : lines 698-701
BACKEND_INCOMPATIBLE_MESSAGE = (
    "Config updates require a persistent state backend (test stub)."
)


def _raise_backend_incompatible(_updates: dict[str, Any]) -> None:
    raise _ConfigBackendIncompatible(BACKEND_INCOMPATIBLE_MESSAGE)


C503_CASES = [
    pytest.param("POST", "/api/config", {}, id="POST /api/config"),
    pytest.param(
        "POST",
        "/api/config/ocr",
        {},
        id="POST /api/config/ocr",
    ),
    pytest.param(
        "POST",
        "/api/config/translation",
        {},
        id="POST /api/config/translation",
    ),
    pytest.param(
        "POST",
        "/api/config/ocr/auth",
        {"auth_token": None},
        id="POST /api/config/ocr/auth",
    ),
    pytest.param(
        "POST",
        "/api/config/translation/auth",
        {"auth_token": None},
        id="POST /api/config/translation/auth",
    ),
    pytest.param(
        "POST",
        "/api/config/transcription/auth",
        {"auth_token": None},
        id="POST /api/config/transcription/auth",
    ),
]


@pytest.mark.parametrize("method,path,payload", C503_CASES)
def test_503_site_returns_envelope(
    client: TestClient, method: str, path: str, payload: dict[str, Any]
) -> None:
    """Force ``_persist_config`` to raise; assert 503 + canonical envelope."""
    with patch.object(
        config_module,
        "_persist_config",
        new=_raise_backend_incompatible,
    ):
        resp = client.post(path, json=payload)

    assert resp.status_code == 503, (
        f"{method} {path}: expected 503, got {resp.status_code} body={resp.text}"
    )
    body: dict[str, Any] = resp.json()
    assert body == {
        "error": "backend_unavailable",
        "detail": BACKEND_INCOMPATIBLE_MESSAGE,
    }, f"{method} {path}: envelope shape mismatch: {body}"


# ---------------------------------------------------------------------------
# Sanity checks — the exception classes used in the sweep carry the
# right wire metadata so the handler produces the shape we assert above.
# ---------------------------------------------------------------------------


def test_ssrf_blocked_envelope_matches_assertion() -> None:
    err = SSRFBlocked(url="http://127.0.0.1:1", reason="loopback")
    assert err.status_code == 403
    assert err.error == "ssrf_blocked"
    assert err.detail == "URL targets a blocked address: loopback"


def test_backend_unavailable_envelope_matches_assertion() -> None:
    err = BackendUnavailable(detail=BACKEND_INCOMPATIBLE_MESSAGE)
    assert err.status_code == 503
    assert err.error == "backend_unavailable"
    assert err.detail == BACKEND_INCOMPATIBLE_MESSAGE


# ---------------------------------------------------------------------------
# Transcription router sweep (Phase C / Task 3)
# ---------------------------------------------------------------------------
#
# Replaces the 6 HTTPException(status_code=...) sites in
# src/omniscribe/api/routers/transcription.py with typed envelope exceptions:
#   line  60 (UploadValidationError) → BadRequest
#   line  72 (SSRF on transcribe)     → SSRFBlocked
#   line  90 (AudioValidationError)  → BadRequest
#   line  92 (TranscriptionError)    → BackendUnavailable
#   line 208 (SSRF on config update) → SSRFBlocked
#   line 230 (ConfigBackendIncompat) → BackendUnavailable


@pytest.fixture
def transcription_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(transcription_router)
    return TestClient(app)


def test_transcribe_route_returns_envelope_on_missing_file(
    transcription_client: TestClient,
) -> None:
    """An empty POST to /api/transcribe (no multipart file) should return
    a 400 or 422 envelope, not a raw FastAPI HTTPException detail string.
    """
    resp = transcription_client.post("/api/transcribe")
    # FastAPI may treat missing-file as 422 (validation) at the route level
    # OR the route may catch MissingFile and re-raise as 400 (BadRequest).
    assert resp.status_code in {400, 422}, (
        f"expected 400 or 422, got {resp.status_code}: {resp.text}"
    )
    body: dict[str, Any] = resp.json()
    assert body["error"] in {"validation_failed", "bad_request"}, (
        f"expected envelope error, got body={body}"
    )
    assert "detail" in body


# ---------------------------------------------------------------------------
# Providers router sweep (Phase C / Task 4)
# ---------------------------------------------------------------------------
#
# Replaces the 6 swept sites in src/omniscribe/api/routers/providers.py
# with typed envelope exceptions:
#   line  90 (404 in update_active_provider)   → NotFound
#   line  99 (403 SSRF in create_or_update)    → SSRFBlocked
#   line 112 (404 in delete_provider)         → NotFound
#   line 124 (404 in list_provider_models)    → NotFound
#   line 129 (403 SSRF in list_provider_models) → SSRFBlocked
#   line 141 (404 in get_provider_details)    → NotFound


@pytest.fixture
def providers_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(providers_router)
    return TestClient(app)


def test_providers_unknown_returns_envelope(providers_client: TestClient) -> None:
    resp = providers_client.get("/api/providers/no-such-provider")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_providers_bad_payload_returns_envelope(
    providers_client: TestClient,
) -> None:
    # POST /api/providers/active with unknown provider → 404 envelope
    # (swept NotFound site at line 90 in routers/providers.py).
    resp = providers_client.post(
        "/api/providers/active", json={"provider_id": "no-such-provider"}
    )
    assert resp.status_code in {400, 404, 422}
    body = resp.json()
    assert body["error"] in {"not_found", "bad_request", "validation_failed"}
