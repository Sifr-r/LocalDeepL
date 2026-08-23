"""RuntimeSettings cordis config-path fields: defaults and env overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from omniscribe.config import RuntimeSettings

_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "omniscribe"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OMNISCRIBE_CORDIS_CONFIG", "OMNISCRIBE_CORDIS_PATCH"):
        monkeypatch.delenv(name, raising=False)


def test_cordis_config_path_defaults_to_shipped_file(clean_env: None) -> None:
    settings = RuntimeSettings()
    assert settings.cordis_config_path == _PACKAGE_DIR / "resources" / "cordis.yml"
    assert settings.cordis_config_path.is_file()


def test_cordis_config_path_env_override(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom.yml"
    custom.write_text("plugins: []\n", encoding="utf-8")
    monkeypatch.setenv("OMNISCRIBE_CORDIS_CONFIG", str(custom))
    settings = RuntimeSettings()
    assert settings.cordis_config_path == custom


def test_patch_paths_default_is_empty_when_file_missing(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    settings = RuntimeSettings()
    assert settings.cordis_patch_paths == ()


def test_patch_paths_default_picks_up_operator_patch(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    patch = tmp_path / "cordis.patch.yml"
    patch.write_text("plugins: []\n", encoding="utf-8")
    settings = RuntimeSettings()
    assert settings.cordis_patch_paths == (patch,)


def test_patch_paths_env_override_filters_missing_entries(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "one.yml"
    second = tmp_path / "two.yml"
    first.write_text("plugins: []\n", encoding="utf-8")
    second.write_text("plugins: []\n", encoding="utf-8")
    missing = tmp_path / "missing.yml"
    monkeypatch.setenv("OMNISCRIBE_CORDIS_PATCH", f"{first}, {missing}, {second}")
    settings = RuntimeSettings()
    assert settings.cordis_patch_paths == (first, second)
