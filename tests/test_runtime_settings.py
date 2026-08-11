"""Tests for the centralized Pydantic runtime settings boundary."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from omniscribe.config import RuntimeSettings, load_settings

_RUNTIME_ENV_NAMES = (
    "LLM_API_BASE",
    "LLM_API_KEY",
    "LLM_MODEL",
    "OMNISCRIBE_LLM_API_BASE",
    "OMNISCRIBE_LLM_API_KEY",
    "OMNISCRIBE_LLM_MODEL",
    "OMNISCRIBE_GROUNDED_MODEL",
    "OMNISCRIBE_VLM_PAGE_TIMEOUT",
    "OMNISCRIBE_VLM_CROP_TIMEOUT",
    "OMNISCRIBE_LLM_MAX_RETRIES",
    "OMNISCRIBE_LLM_RETRY_BASE_DELAY",
    "OMNISCRIBE_CB_FAILURE_THRESHOLD",
    "OMNISCRIBE_CB_COOLDOWN",
    "OMNISCRIBE_ARTIFACT_DIR",
    "OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S",
    "OMNISCRIBE_CHUNK_PAGES",
    "OMNISCRIBE_CHROMA_DB",
    "REDIS_URL",
    "ALLOW_SSRF_LOCAL",
    "OMNISCRIBE_LOG_LEVEL",
    "OMNISCRIBE_LOG_FORMAT",
    "OMNISCRIBE_AUTH_TOKEN",
    "LOCAL_DEEPL_AUTH_TOKEN",
    "OMNISCRIBE_OCR_AUTH_TOKEN",
    "LOCAL_DEEPL_OCR_AUTH_TOKEN",
    "OMNISCRIBE_TRANSLATION_AUTH_TOKEN",
    "LOCAL_DEEPL_TRANSLATION_AUTH_TOKEN",
    "OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN",
    "LOCAL_DEEPL_TRANSCRIPTION_AUTH_TOKEN",
    "OMNISCRIBE_CORS_ORIGINS",
    "LOCAL_DEEPL_CORS_ORIGINS",
    "OMNISCRIBE_MAX_UPLOAD_MB",
    "LOCAL_DEEPL_MAX_UPLOAD_MB",
    "OMNISCRIBE_RATE_LIMIT_PER_MIN",
    "LOCAL_DEEPL_RATE_LIMIT_PER_MIN",
)


@pytest.fixture
def clean_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _RUNTIME_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_runtime_settings_defaults_are_stable(clean_runtime_env: None) -> None:
    settings = RuntimeSettings()

    assert settings.llm_api_base == "http://localhost:1234/v1"
    assert settings.llm_api_key == "lm-studio"
    assert settings.llm_model == "allenai/olmocr-2-7b"
    assert settings.grounded_model == "qwen/qwen3-vl-8b"
    assert settings.vlm_page_timeout == 240.0
    assert settings.vlm_crop_timeout == 60.0
    assert settings.artifact_directory == Path(tempfile.gettempdir()) / "omniscribe"
    assert settings.cors_origins == []
    assert settings.rate_limit_per_min is None


def test_load_settings_allows_field_name_overrides(
    clean_runtime_env: None,
) -> None:
    settings = load_settings(
        llm_api_base="http://override/v1",
        llm_api_key="override-key",
        llm_model="override-model",
        grounded_model="override-grounded-model",
        max_upload_mb=7,
        rate_limit_per_min=12,
    )

    assert settings.llm_api_base == "http://override/v1"
    assert settings.llm_api_key == "override-key"
    assert settings.llm_model == "override-model"
    assert settings.grounded_model == "override-grounded-model"
    assert settings.max_upload_mb == 7
    assert settings.rate_limit_per_min == 12


def test_shared_llm_model_alias_configures_both_engines(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL", "shared-model")

    settings = RuntimeSettings()

    assert settings.llm_model == "shared-model"
    assert settings.grounded_model == "shared-model"


def test_grounded_model_can_be_configured_independently(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNISCRIBE_GROUNDED_MODEL", "grounded-model")

    settings = RuntimeSettings()

    assert settings.llm_model == "allenai/olmocr-2-7b"
    assert settings.grounded_model == "grounded-model"


def test_legacy_security_aliases_and_csv_are_supported(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_DEEPL_AUTH_TOKEN", " legacy-token ")
    monkeypatch.setenv(
        "LOCAL_DEEPL_CORS_ORIGINS", " https://one.test, ,https://two.test "
    )
    monkeypatch.setenv("LOCAL_DEEPL_MAX_UPLOAD_MB", "123")
    monkeypatch.setenv("LOCAL_DEEPL_RATE_LIMIT_PER_MIN", "9")

    settings = RuntimeSettings()

    assert settings.auth_token == "legacy-token"
    assert settings.cors_origins == ["https://one.test", "https://two.test"]
    assert settings.max_upload_mb == 123
    assert settings.rate_limit_per_min == 9


def test_invalid_security_integers_keep_legacy_fallbacks(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNISCRIBE_MAX_UPLOAD_MB", "not-an-int")
    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "not-an-int")

    settings = RuntimeSettings()

    assert settings.max_upload_mb == 10_240
    assert settings.rate_limit_per_min is None


def test_invalid_positive_timeout_fails_validation(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNISCRIBE_VLM_PAGE_TIMEOUT", "0")

    with pytest.raises(ValidationError):
        RuntimeSettings()


def test_startup_validation_logs_only_non_secret_settings(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "a" * 40)
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(server, "configure_logging", lambda **_: None)
    monkeypatch.setattr(
        server._log,
        "info",
        lambda _message, *, extra: logged.append(extra),
    )

    settings = server._validate_runtime_settings()

    assert settings.artifact_base_dir == tmp_path
    assert logged == [
        {
            "llm_api_base": "http://localhost:1234/v1",
            "llm_model": "allenai/olmocr-2-7b",
            "grounded_model": "qwen/qwen3-vl-8b",
            "vlm_page_timeout": 240.0,
            "vlm_crop_timeout": 60.0,
            "artifact_base_dir": str(tmp_path),
            "allow_ssrf_local": False,
            "state_backend": "memory",
            "auth_enabled": True,
        }
    ]
    assert "a" * 40 not in str(logged)


def test_startup_validation_rejects_artifact_file(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from omniscribe import server

    artifact_file = tmp_path / "artifacts"
    artifact_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("OMNISCRIBE_ARTIFACT_DIR", str(artifact_file))

    with pytest.raises(RuntimeError, match="must point to a directory"):
        server._validate_runtime_settings()


def test_startup_validation_rejects_unknown_log_format(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omniscribe import server

    monkeypatch.setenv("OMNISCRIBE_LOG_FORMAT", "xml")

    with pytest.raises(ValueError, match="Unknown log format"):
        server._validate_runtime_settings()


def test_negative_rate_limit_disables_rate_limiting(
    clean_runtime_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNISCRIBE_RATE_LIMIT_PER_MIN", "-1")

    assert RuntimeSettings().rate_limit_per_min is None
