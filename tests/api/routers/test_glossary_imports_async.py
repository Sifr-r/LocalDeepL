# tests/api/routers/test_glossary_imports_async.py
"""Glossary imports must use direct async SSRF — no threadpool shim."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers.glossary_imports import router
from omniscribe.api.services.envelope import register_envelope_handlers


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(router)
    return TestClient(app)


def test_threadpool_shim_is_gone() -> None:
    """The sync `_sync_ssrf_blocked` threadpool shim must be deleted."""
    from omniscribe.api.routers import glossary_imports

    assert not hasattr(glossary_imports, "_sync_ssrf_blocked"), (
        "Threadpool SSRF shim must be deleted in Task 7"
    )
    assert not hasattr(glossary_imports, "_validate_ssrf"), (
        "Sync SSRF helper must be deleted in Task 7"
    )


def test_glossary_git_import_returns_envelope_on_ssrf(client: TestClient) -> None:
    """Direct git_glossary URL SSRF deny → envelope."""
    from omniscribe.api.routers import glossary_imports
    from omniscribe.utils.security import SSRFCheckResult

    denied = SSRFCheckResult(allowed=False, resolved_ip=None, reason="loopback")
    with patch.object(
        glossary_imports,
        "is_ssrf_target",
        new=AsyncMock(return_value=denied),
    ):
        resp = client.post(
            "/api/glossary/import",
            json={
                "source": {
                    "format": "git_glossary",
                    "git_url": "http://127.0.0.1:1",
                    "git_path": "GLOSSARY.md",
                }
            },
        )
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["error"] == "ssrf_blocked"
    assert "detail" in body


def test_import_glossary_is_async() -> None:
    """`import_glossary` must be `async def` so it can await SSRF directly."""
    import inspect

    from omniscribe.api.routers.glossary_imports import import_glossary

    assert inspect.iscoroutinefunction(import_glossary), (
        "import_glossary must be async to use `await is_ssrf_target(...)`"
    )
