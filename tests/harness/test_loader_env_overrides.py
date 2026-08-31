"""Regression: env overrides must match row ids case-insensitively.

Pedantic review 1.2 (2026-08-30): overrides were keyed by lowercased id
but matched against the row's original casing, so a capitalized row id
silently dropped every OMNISCRIBE_PLUGIN_<ID>__<FIELD> override.
"""

from __future__ import annotations

import pytest

from omniscribe.harness.loader import _apply_env_overrides, parse_rows


def test_env_override_matches_mixed_case_row_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    yml = tmp_path / "cordis.yml"
    yml.write_text(
        "plugins:\n"
        "  - id: Runtime\n"
        "    use: omniscribe.plugins.runtime:plugin\n"
        "    config:\n"
        "      cleanup_interval_seconds: 60\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNISCRIBE_PLUGIN_RUNTIME__CLEANUP_INTERVAL_SECONDS", "5")
    rows = parse_rows(yml.read_text(encoding="utf-8"))
    folded = _apply_env_overrides(rows)
    assert folded[0].config["cleanup_interval_seconds"] == "5"
