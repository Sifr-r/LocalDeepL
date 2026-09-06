"""Server boot: the FastAPI lifespan mounts and disposes the plugin tree."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omniscribe.harness.errors import PluginLoadError
from omniscribe.harness.plugin import Plugin
from omniscribe.server import create_app


@pytest.fixture
def boot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic harness boot: no backend/patch/config overrides."""
    for name in (
        "OMNISCRIBE_STATE_BACKEND",
        "OMNISCRIBE_STATE_DB_PATH",
        "OMNISCRIBE_CORDIS_CONFIG",
        "OMNISCRIBE_CORDIS_PATCH",
        "OMNISCRIBE_ARTIFACT_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(Path.cwd() / ".test-artifacts"))


def test_boot_serves_health_and_unknown_job_status(boot_env: None) -> None:
    with TestClient(create_app()) as client:  # type: ignore[arg-type]
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        # Readiness flips during lifespan startup.
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}

        status = client.get("/api/process/status/unknown-job")
        assert status.status_code == 404


def test_lifespan_dispose_runs_effect_cleanups(
    boot_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    disposed: list[str] = []

    class ProbePlugin(Plugin):
        async def apply(self, ctx: object) -> None:
            async def _cleanup() -> None:
                disposed.append("disposed")

            ctx.effect(_cleanup)  # type: ignore[attr-defined]

    probe_module = types.ModuleType("boot_probe_plugin")
    probe_module.plugin = ProbePlugin()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boot_probe_plugin", probe_module)

    cordis_yml = tmp_path / "cordis.yml"
    cordis_yml.write_text(
        "plugins:\n  - id: probe\n    use: boot_probe_plugin:plugin\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNISCRIBE_CORDIS_CONFIG", str(cordis_yml))

    assert disposed == []
    with TestClient(create_app()):  # type: ignore[arg-type]
        assert disposed == []
    assert disposed == ["disposed"]


def test_bad_state_backend_fails_boot_loud(
    boot_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ``redis`` is not implemented in the harness — must fail loud at boot.
    monkeypatch.setenv("OMNISCRIBE_STATE_BACKEND", "redis")
    with pytest.raises((PluginLoadError, ValidationError)):
        with TestClient(create_app()):  # type: ignore[arg-type]
            pass


def test_circuit_open_error_handler(boot_env: None) -> None:
    from omniscribe.core.ocr.resilience import CircuitOpenError

    app = create_app()

    @app.get("/test-circuit-open")  # type: ignore[attr-defined]
    async def _fail_circuit() -> None:
        raise CircuitOpenError(failures=5, retry_after=45.2)

    with TestClient(app) as client:  # type: ignore[arg-type]
        res = client.get("/test-circuit-open")
        assert res.status_code == 503
        assert res.headers["retry-after"] == "46"
        assert res.json() == {
            "error": "service_unavailable",
            "detail": "Model circuit breaker is open; retry later",
        }


# ---------------------------------------------------------------------------
# Audit S13: CORS ``*`` + credentials
# ---------------------------------------------------------------------------


def test_cors_wildcard_strips_allow_credentials(
    boot_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit S13: ``*`` in ``OMNISCRIBE_CORS_ORIGINS`` must NOT combine
    with ``Access-Control-Allow-Credentials: true``. Browsers reject
    the combo in practice, but the CORS spec discourages it and the
    server-side misconfiguration is a footgun for authenticated
    deployments. The handler forces ``allow_credentials=False`` when
    ``*`` appears in the allowlist; explicit origins keep credentials
    on.
    """
    monkeypatch.setenv("OMNISCRIBE_CORS_ORIGINS", "*")
    with TestClient(create_app()) as client:  # type: ignore[arg-type]
        # Preflight OPTIONS from a sample origin.
        preflight = client.options(
            "/api/health",
            headers={
                "Origin": "http://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        # The wildcard permits the origin (good) but must NOT echo
        # credentials (the audit's fix).
        assert preflight.headers.get("access-control-allow-origin") == "*"
        assert (
            preflight.headers.get("access-control-allow-credentials") is None
        )


def test_cors_explicit_origins_allow_credentials(
    boot_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The complement of the S13 test: explicit origins (no ``*``)
    keep ``Access-Control-Allow-Credentials: true`` so the
    authenticated single-tenant deployment (Profile 2) keeps
    working.
    """
    monkeypatch.setenv("OMNISCRIBE_CORS_ORIGINS", "http://app.example.com")
    with TestClient(create_app()) as client:  # type: ignore[arg-type]
        preflight = client.options(
            "/api/health",
            headers={
                "Origin": "http://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert (
            preflight.headers.get("access-control-allow-origin")
            == "http://app.example.com"
        )
        assert (
            preflight.headers.get("access-control-allow-credentials") == "true"
        )
