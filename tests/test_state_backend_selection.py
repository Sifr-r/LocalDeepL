"""Tests for the state backend selection and configuration (audit A-3)."""

from __future__ import annotations

from typing import Any

import pytest

from omniscribe.api.routers.state import build_state_backend
from omniscribe.api.services.state_backend import LocalStateBackend, StateBackend
from omniscribe.config import RuntimeSettings, load_settings


def test_state_backend_default_is_memory():
    """Default ``OMNISCRIBE_STATE_BACKEND`` is ``memory`` (no surprise network calls)."""
    settings = load_settings()
    assert settings.state_backend == "memory"


def test_state_backend_setting_accepts_redis():
    settings = load_settings(OMNISCRIBE_STATE_BACKEND="redis")
    assert settings.state_backend == "redis"


def test_state_backend_setting_normalises_case_and_whitespace():
    settings = load_settings(OMNISCRIBE_STATE_BACKEND="  REDIS  ")
    assert settings.state_backend == "redis"


def test_state_backend_setting_rejects_unknown():
    with pytest.raises(ValueError, match="must be 'memory' or 'redis'"):
        load_settings(OMNISCRIBE_STATE_BACKEND="sqlite")


def test_state_backend_setting_empty_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OMNISCRIBE_STATE_BACKEND", raising=False)
    settings = load_settings()
    assert settings.state_backend == "memory"


def test_build_state_backend_returns_local_for_memory(tmp_path: Any):
    settings = RuntimeSettings(OMNISCRIBE_ARTIFACT_DIR=str(tmp_path))
    backend = build_state_backend(settings)
    assert isinstance(backend, LocalStateBackend)
    # Local backend must satisfy the Protocol surface.
    assert isinstance(backend, StateBackend)


def test_build_state_backend_redis_path_without_redis_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """When OMNISCRIBE_STATE_BACKEND=redis and the ``redis`` package is missing,
    we fail fast with a clear install hint, not an opaque ImportError later."""

    class _FakeFinder:
        def find_module(self, name: str, path: Any = None) -> None:
            if name == "omniscribe.api.services.state_backend_redis":
                return None
            return None

    # Simulate ``redis`` not being importable by raising ImportError for it.
    import builtins

    original_import = builtins.__import__

    def _raise_for_redis(name: str, *args: Any, **kwargs: Any):
        if name == "redis" or name.startswith("redis."):
            raise ImportError(f"No module named {name!r}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_for_redis)

    settings = RuntimeSettings(
        OMNISCRIBE_STATE_BACKEND="redis",
        OMNISCRIBE_ARTIFACT_DIR=str(tmp_path),
    )
    with pytest.raises(RuntimeError, match="OMNISCRIBE_STATE_BACKEND=redis"):
        build_state_backend(settings)


def test_build_state_backend_rejects_unknown_value(tmp_path: Any):
    """A programmatically injected bad name fails at the factory boundary."""

    class _FakeSettings:
        state_backend = "sqlite"
        redis_url = "redis://localhost:6379/0"
        artifact_directory = tmp_path

    with pytest.raises(RuntimeError, match="Unknown OMNISCRIBE_STATE_BACKEND"):
        build_state_backend(_FakeSettings())  # type: ignore[arg-type]


def test_local_state_backend_accepts_custom_artifact_dir(tmp_path: Any):
    """LocalStateBackend now accepts an ``artifact_dir`` and threads it
    through every TextArtifactStore + the GlossaryLibrary."""
    backend = LocalStateBackend(artifact_dir=tmp_path)
    assert backend.text_artifacts.artifact_dir == tmp_path
    assert backend.metadata_artifacts.artifact_dir == tmp_path
    assert backend.export_artifacts.artifact_dir == tmp_path
    # GlossaryLibrary stores the directory privately; verify via ``path``.
    assert backend.glossary_library.path.parent.parent.resolve() == tmp_path.resolve()


def test_local_state_backend_from_env_uses_settings_dir(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
):
    """``from_env`` reads the configured artifact directory at construction time."""
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    backend = LocalStateBackend.from_env()
    assert backend.text_artifacts.artifact_dir == tmp_path / "omniscribe"
