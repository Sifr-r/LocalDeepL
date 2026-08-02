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
