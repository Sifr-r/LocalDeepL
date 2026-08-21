"""`/api/models*` routes — extracted from routers/config.py and routers/transcription.py.

Phase C / Task 9: consolidate the four ``/api/models*`` endpoints into a
dedicated ``routers/models.py``. Three of them (``/api/models``,
``/api/models/ocr``, ``/api/models/translation``) previously lived in
``routers/config.py``; the fourth (``/api/models/transcription``) lived
in ``routers/transcription.py``. The new module preserves the public
HTTP surface (paths, methods, response shapes) so the OpenAPI contract
test and the existing model-discovery tests continue to pass.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import models as models_module
from omniscribe.api.routers.config import router as config_router
from omniscribe.api.routers.models import router as models_router
from omniscribe.api.routers.transcription import router as transcription_router
from omniscribe.api.services.envelope import register_envelope_handlers


@pytest.fixture
def client() -> TestClient:
    """Test client with only ``routers/models.py`` mounted.

    ``register_envelope_handlers`` is required because the SSRF sites
    raise :class:`SSRFBlocked` (from :mod:`omniscribe.api.services.envelope`)
    and the envelope handler converts that into the canonical
    ``{"error": "ssrf_blocked", "detail": "..."}`` JSON body.
    """
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(models_router)
    return TestClient(app)


def test_models_router_registers_all_four_routes() -> None:
    """The new module must expose the four canonical ``/api/models*`` paths."""
    paths = {route.path for route in models_router.routes}
    assert "/api/models" in paths
    assert "/api/models/ocr" in paths
    assert "/api/models/translation" in paths
    assert "/api/models/transcription" in paths


def test_config_router_no_longer_registers_models_paths() -> None:
    """After the extraction, ``routers/config.py`` must NOT register any
    ``/api/models*`` path — the routes have moved to ``routers/models.py``.
    """
    config_paths = {route.path for route in config_router.routes}
    for moved in (
        "/api/models",
        "/api/models/ocr",
        "/api/models/translation",
    ):
        assert moved not in config_paths, (
            f"{moved} still registered by routers/config.py — extraction incomplete"
        )


def test_transcription_router_no_longer_registers_models_transcription() -> None:
    """After the extraction, ``routers/transcription.py`` must NOT register
    ``/api/models/transcription`` — the route moved to ``routers/models.py``.
    """
    paths = {route.path for route in transcription_router.routes}
    assert "/api/models/transcription" not in paths, (
        "/api/models/transcription still registered by routers/transcription.py "
        "— extraction incomplete"
    )


def test_list_ocr_models_returns_envelope_on_ssrf(client: TestClient) -> None:
    """At least one ``/api/models`` route has an SSRF check; mock it to deny
    and verify the canonical 403 envelope shape.

    ``/api/models/ocr`` is picked because its SSRF site fires before any
    external HTTP call (the loopback ``api_base`` short-circuits to
    ``SSRFBlocked``), so the patch has a deterministic effect.
    """
    denied = SimpleNamespace(allowed=False, reason="loopback")
    with patch.object(
        models_module,
        "is_ssrf_target",
        new=AsyncMock(return_value=denied),
    ):
        resp = client.get("/api/models/ocr")

    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["error"] == "ssrf_blocked"
    assert "loopback" in body["detail"]
