"""${VAR:-default} environment expansion."""

from __future__ import annotations

import pytest

from omniscribe.harness.config import expand_env
from omniscribe.harness.errors import PluginLoadError


def test_unset_var_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNISCRIBE_TEST_MISSING", raising=False)
    assert expand_env("${OMNISCRIBE_TEST_MISSING:-fallback}", row_id="x") == "fallback"


def test_set_var_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNISCRIBE_TEST_PRESENT", "real")
    assert expand_env("${OMNISCRIBE_TEST_PRESENT:-fallback}", row_id="x") == "real"


def test_no_placeholder_unchanged() -> None:
    assert expand_env("plain text", row_id="x") == "plain text"


def test_unset_var_without_default_fails() -> None:
    with pytest.raises(PluginLoadError) as excinfo:
        expand_env("${OMNISCRIBE_TEST_NEVER_SET}", row_id="row-a")
    assert excinfo.value.row_id == "row-a"


def test_recursive_expansion_through_dicts_and_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNISCRIBE_TEST_A", "one")
    value = {
        "a": "${OMNISCRIBE_TEST_A}",
        "nested": {"b": ["${OMNISCRIBE_TEST_A:-two}", 3, None]},
    }
    assert expand_env(value, row_id="x") == {
        "a": "one",
        "nested": {"b": ["one", 3, None]},
    }


def test_non_string_leaves_pass_through() -> None:
    assert expand_env(42, row_id="x") == 42
    assert expand_env(True, row_id="x") is True
