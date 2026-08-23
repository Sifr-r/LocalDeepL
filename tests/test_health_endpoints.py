"""Tests for the liveness and readiness probes.

Pins the contract added alongside audit fixes C-25 / A-20:

* ``GET /health`` and ``GET /healthz`` return ``{"status": "ok"}`` with
  HTTP 200 — no dependencies, no auth required even when a global
  bearer token is set (orchestrators must always be able to probe).
* ``GET /ready`` and ``GET /readyz`` return HTTP 200 when the OCR job
  queue worker is alive, with entry counts from each artifact store in
  the payload. HTTP 503 + ``reasons`` when the worker is missing.
* Health paths bypass ``BearerAuthMiddleware`` so a configured token
  cannot accidentally lock the orchestrator out.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from omniscribe.api.services.security_middleware import BearerAuthMiddleware

# F4.15 audit fix: ``pytestmark = pytest.mark.asyncio`` is redundant
# under ``asyncio_mode = "auto"`` (set in pyproject.toml). The
# mode already treats every ``async def test_*`` as an asyncio
# test, so the module-level marker is a no-op. Drop it; the
# regression test in ``test_tier_discipline.py`` catches a
# re-introduction.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CollectSend:
    """Capture ASGI send events so a test can inspect status / body."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    @property
    def status(self) -> int:
        for event in self.events:
            if event.get("type") == "http.response.start":
                return int(event.get("status", 0))
        return 0

    @property
    def body(self) -> bytes:
        chunks: list[bytes] = []
        for event in self.events:
            if event.get("type") == "http.response.body":
                body = event.get("body", b"")
                if isinstance(body, (bytes, bytearray)):
                    chunks.append(bytes(body))
        return b"".join(chunks)

    @property
    def body_json(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.body or b"{}"))


class _MarkerApp:
    """Terminal ASGI app that records whether the middleware passed through."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_scope: dict[str, Any] | None = None

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        self.calls += 1
        self.last_scope = scope
        # Mimic a minimal FastAPI 200 OK response so callers can read body.
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", b"2"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})


def _build_scope(
    path: str, headers: list[tuple[bytes, bytes]] | None = None
) -> dict[str, Any]:
    """Construct a minimal HTTP scope for ASGI middleware tests."""
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "headers": list(headers or []),
        "query_string": b"",
    }


async def _receive_empty() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


# ---------------------------------------------------------------------------
# Auth-exempt contract
# ---------------------------------------------------------------------------


async def test_bearer_auth_middleware_allows_health_paths_when_token_set() -> None:
    """A configured global token must not block /health, /ready, or aliases."""
    for health_path in ("/health", "/healthz", "/ready", "/readyz"):
        inner = _MarkerApp()
        middleware = BearerAuthMiddleware(inner, expected_token="super-secret-token")

        send = _CollectSend()
        await middleware(_build_scope(health_path), _receive_empty, send)

        # _MarkerApp mimics a minimal FastAPI 200 OK response — the
        # point is that we got there at all (no 401 in between).
        assert send.status == 200, (
            f"{health_path} should pass through to the inner app; "
            f"got status={send.status}"
        )
        assert inner.calls == 1, (
            f"{health_path} should reach the inner app exactly once"
        )


async def test_bearer_auth_middleware_still_protects_other_paths() -> None:
    """The exempt set is exactly {/health*, /ready*} — other routes still require auth."""
    inner = _MarkerApp()
    middleware = BearerAuthMiddleware(inner, expected_token="super-secret-token")

    send = _CollectSend()
    await middleware(_build_scope("/api/jobs"), _receive_empty, send)

    assert send.status == 401, "non-health paths must remain protected"
    assert inner.calls == 0, "401 response must short-circuit before the inner app"
    assert send.body_json == {"error": "Unauthorized"}


# ---------------------------------------------------------------------------
# Liveness probe
# ---------------------------------------------------------------------------


async def test_liveness_probe_returns_ok() -> None:
    """``GET /health`` returns a small JSON body with status=ok and HTTP 200."""
    from omniscribe.api.routers.health import liveness

    response = await liveness()
    body = cast(dict[str, Any], json.loads(bytes(response.body)))
    assert response.status_code == 200
    assert body == {"status": "ok"}


async def test_liveness_probe_does_not_require_artifact_state() -> None:
    """The liveness handler must not depend on in-memory artifact store state.

    If the artifact stores are uninitialised (e.g. during early
    startup) the liveness probe should still answer — that's the
    whole point of having a separate liveness probe distinct from
    readiness.
    """
    from omniscribe.api.routers import health

    # Smoke test: the handler runs without raising even with empty state.
    response = await health.liveness()
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Readiness probe
# ---------------------------------------------------------------------------


async def test_readiness_probe_reports_subsystem_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GET /ready`` returns 200 + the artifact counts + queue flag."""
    from omniscribe.api.routers import health, state

    class _FakeStore:
        def __len__(self) -> int:
            return 7

    # Replace the live state holders with deterministic fakes so the
    # test does not depend on the order other tests run in.
    monkeypatch.setattr(state, "text_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(state, "metadata_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(state, "export_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(
        state, "ocr_job_queue", type("Q", (), {"running": True})(), raising=False
    )

    response = await health.readiness()
    body = cast(dict[str, Any], json.loads(bytes(response.body)))
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["artifacts"] == {
        "text_entries": 7,
        "metadata_entries": 7,
        "export_entries": 7,
    }
    assert body["ocr_job_queue_running"] is True
    assert "reasons" not in body


async def test_readiness_probe_reports_503_when_queue_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the OCR job queue worker has died, readiness must report degraded."""
    from omniscribe.api.routers import health, state

    class _FakeStore:
        def __len__(self) -> int:
            return 0

    monkeypatch.setattr(state, "text_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(state, "metadata_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(state, "export_artifacts", _FakeStore(), raising=False)
    monkeypatch.setattr(
        state, "ocr_job_queue", type("Q", (), {"running": False})(), raising=False
    )

    response = await health.readiness()
    body = cast(dict[str, Any], json.loads(bytes(response.body)))
    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["ocr_job_queue_running"] is False
    assert "ocr_job_queue not running" in body["reasons"]
