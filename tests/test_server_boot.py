"""Server boot: the FastAPI lifespan mounts and disposes the plugin tree."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    with TestClient(create_app()) as client:
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
    with TestClient(create_app()):
        assert disposed == []
    assert disposed == ["disposed"]


def test_bad_state_backend_fails_boot_loud(
    boot_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ``redis`` passes RuntimeSettings validation but the harness only ships
    # memory/sqlite backends — the state_backend row must fail loud at boot.
    monkeypatch.setenv("OMNISCRIBE_STATE_BACKEND", "redis")
    with pytest.raises(PluginLoadError, match="state_backend"):
        with TestClient(create_app()):
            pass
