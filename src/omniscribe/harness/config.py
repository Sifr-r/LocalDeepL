"""Plugin config helpers: ``${VAR:-default}`` environment expansion."""

from __future__ import annotations

import os
import re
from typing import Any

from omniscribe.harness.errors import PluginLoadError

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand_string(text: str, *, row_id: str) -> str:
    def _substitute(match: re.Match[str]) -> str:
        var_name, default = match.group(1), match.group(2)
        value = os.environ.get(var_name)
        if value is not None:
            return value
        if default is not None:
            return default
        raise PluginLoadError(
            row_id=row_id,
            reason=f"environment variable {var_name!r} is not set and has no default",
        )

    return _ENV_PATTERN.sub(_substitute, text)


def expand_env(value: Any, *, row_id: str) -> Any:
    """Recursively expand ``${VAR:-default}`` placeholders in strings.

    Dicts and lists are walked structurally; non-string leaves pass through
    unchanged. An unset variable with no ``:-default`` fails loud with the
    owning row id.
    """
    if isinstance(value, str):
        return _expand_string(value, row_id=row_id)
    if isinstance(value, dict):
        return {key: expand_env(item, row_id=row_id) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item, row_id=row_id) for item in value]
    return value
