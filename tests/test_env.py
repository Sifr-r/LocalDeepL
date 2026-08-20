"""
Tests for homegrown omniscribe.utils.env load_dotenv implementation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omniscribe.utils import load_dotenv
from omniscribe.utils.env import _parse_env_line


def test_parse_env_line_basic() -> None:
    assert _parse_env_line("# comment") is None
    assert _parse_env_line("") is None
    assert _parse_env_line("   ") is None
    assert _parse_env_line("NO_EQUALS") is None
    assert _parse_env_line("FOO=bar") == ("FOO", "bar")
    assert _parse_env_line("export FOO=bar") == ("FOO", "bar")
    assert _parse_env_line("export\tFOO=bar") == ("FOO", "bar")
    assert _parse_env_line("EMPTY=") == ("EMPTY", "")


def test_parse_env_line_quotes_and_escapes() -> None:
    assert _parse_env_line("SINGLE='hello world'") == ("SINGLE", "hello world")
    assert _parse_env_line('DOUBLE="hello\\nworld"') == ("DOUBLE", "hello\nworld")
    assert _parse_env_line('ESCAPED_QUOTE="hello \\"world\\""') == (
        "ESCAPED_QUOTE",
        'hello "world"',
    )
    assert _parse_env_line('BACKSLASH="C:\\\\path\\\\file"') == (
        "BACKSLASH",
        "C:\\path\\file",
    )
    assert _parse_env_line('WITH_HASH="foo # bar"') == ("WITH_HASH", "foo # bar")
    assert _parse_env_line("SINGLE_HASH='foo # bar'") == ("SINGLE_HASH", "foo # bar")


def test_parse_env_line_inline_comments() -> None:
    assert _parse_env_line("FOO=bar # comment") == ("FOO", "bar")
    assert _parse_env_line("FOO=bar\t# comment") == ("FOO", "bar")
    # No space before # -> value includes #
    assert _parse_env_line("COLOR=#ffffff") == ("COLOR", "#ffffff")


def test_load_dotenv_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / ".env.missing"
    assert not load_dotenv(missing)


def test_load_dotenv_sets_and_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEST_ENV_KEY1", raising=False)
    monkeypatch.setenv("TEST_ENV_KEY2", "initial")

    env_file = tmp_path / ".env"
    env_file.write_text(
        "TEST_ENV_KEY1=val1\nTEST_ENV_KEY2=val2\n",
        encoding="utf-8",
    )

    # Without override
    assert load_dotenv(env_file, override=False)
    assert os.environ.get("TEST_ENV_KEY1") == "val1"
    assert os.environ.get("TEST_ENV_KEY2") == "initial"

    # With override
    assert load_dotenv(env_file, override=True)
    assert os.environ.get("TEST_ENV_KEY2") == "val2"


def test_load_dotenv_auto_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEST_DISCOVERY_KEY", raising=False)

    sub_dir = tmp_path / "a" / "b" / "c"
    sub_dir.mkdir(parents=True)

    env_file = tmp_path / "a" / ".env"
    env_file.write_text("TEST_DISCOVERY_KEY=discovered\n", encoding="utf-8")

    monkeypatch.chdir(sub_dir)
    assert load_dotenv(dotenv_path=None, override=True)
    assert os.environ.get("TEST_DISCOVERY_KEY") == "discovered"


def test_update_dotenv_replaces_and_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omniscribe.utils.env import update_dotenv

    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Heading\nLLM_API_BASE=http://old-host/v1\nLLM_MODEL=old-model\n",
        encoding="utf-8",
    )

    success = update_dotenv(
        {"LLM_API_BASE": "http://new-host/v1", "LLM_API_KEY": "secret-key"},
        dotenv_path=env_file,
    )
    assert success is True

    content = env_file.read_text(encoding="utf-8")
    assert "# Heading" in content
    assert "LLM_API_BASE=http://new-host/v1" in content
    assert "LLM_MODEL=old-model" in content
    assert "LLM_API_KEY=secret-key" in content
    assert os.environ.get("LLM_API_BASE") == "http://new-host/v1"
    assert os.environ.get("LLM_API_KEY") == "secret-key"


def test_provider_manager_set_active_provider_syncs_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omniscribe.api.services.provider_manager import ProviderManager

    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    custom_yaml = tmp_path / "providers.yaml"
    custom_env = tmp_path / ".env"
    custom_env.write_text("LLM_API_BASE=http://localhost:1234/v1\n", encoding="utf-8")

    mgr = ProviderManager(config_path=custom_yaml)
    monkeypatch.setattr("omniscribe.utils.env._find_dotenv", lambda: custom_env)

    provider = mgr.set_active_provider("openai", model="gpt-4o")
    assert provider.id == "openai"

    content = custom_env.read_text(encoding="utf-8")
    assert "LLM_API_BASE=https://api.openai.com/v1" in content
    assert "LLM_MODEL=gpt-4o" in content
