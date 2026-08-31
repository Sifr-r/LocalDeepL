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


# ---------------------------------------------------------------------------
# Pedantic 7.12: OMNISCRIBE_QUALITY_* declared in RuntimeSettings
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_quality_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OMNISCRIBE_QUALITY_LOOP",
        "OMNISCRIBE_QUALITY_TARGET",
        "OMNISCRIBE_QUALITY_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)


def test_quality_defaults_match_documented_contract(
    clean_quality_env: None,
) -> None:
    """Default quality values must match the contract advertised in
    ``cordis.yml``, ``.env.example``, and AGENTS.md:
    ``loop=true``, ``target=0.85``, ``max_retries=2``.
    """
    settings = RuntimeSettings()
    assert settings.ocr_quality_loop_enabled is True
    assert settings.ocr_quality_target == 0.85
    assert settings.ocr_quality_max_retries == 2


def test_quality_env_overrides_are_loaded(
    clean_quality_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each documented env var must reach its corresponding field.
    Previously the three were declared in ``cordis.yml`` and
    ``.env.example`` but not in :class:`RuntimeSettings`, so a caller
    that used :func:`load_settings` (settings dump, ops tooling) saw
    no record of them. They are now first-class fields.
    """
    monkeypatch.setenv("OMNISCRIBE_QUALITY_LOOP", "false")
    monkeypatch.setenv("OMNISCRIBE_QUALITY_TARGET", "0.92")
    monkeypatch.setenv("OMNISCRIBE_QUALITY_MAX_RETRIES", "3")
    settings = RuntimeSettings()
    assert settings.ocr_quality_loop_enabled is False
    assert settings.ocr_quality_target == 0.92
    assert settings.ocr_quality_max_retries == 3


def test_quality_target_out_of_range_rejected(
    clean_quality_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OMNISCRIBE_QUALITY_TARGET`` outside ``[0.5, 1.0]`` is invalid;
    :class:`RuntimeSettings` must reject it the same way the boot-time
    ``OCRSchema`` does.
    """
    from pydantic import ValidationError

    monkeypatch.setenv("OMNISCRIBE_QUALITY_TARGET", "1.5")
    with pytest.raises(ValidationError):
        RuntimeSettings()


def test_quality_max_retries_above_cap_rejected(
    clean_quality_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OMNISCRIBE_QUALITY_MAX_RETRIES`` above 5 is invalid; mirrors
    the ``OCRSchema`` ``le=5`` cap and turns a previously
    plugin-load-time error into a startup-time error.
    """
    from pydantic import ValidationError

    monkeypatch.setenv("OMNISCRIBE_QUALITY_MAX_RETRIES", "7")
    with pytest.raises(ValidationError):
        RuntimeSettings()
