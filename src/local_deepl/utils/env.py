"""
Pure-Python stdlib .env parser and environment loader.

Provides dotenv file searching, line parsing (key-value pairs, comments,
quoted strings, escape sequences), and os.environ population without external
dependencies.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["env_bool", "env_int", "env_list_csv", "env_str", "load_dotenv"]


def _find_dotenv(start_dir: Path | None = None) -> Path | None:
    """Locate a .env file by checking start_dir and its parent directories."""
    current = (start_dir or Path.cwd()).resolve()
    while True:
        candidate = current / ".env"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse a single key=value line from a .env file."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if line.startswith("export ") or line.startswith("export\t"):
        line = line[6:].lstrip()

    if "=" not in line:
        return None

    key, rest = line.split("=", 1)
    key = key.strip()
    if not key:
        return None

    rest = rest.strip()
    if not rest:
        return key, ""

    if rest.startswith("'"):
        end_idx = rest.find("'", 1)
        if end_idx != -1:
            return key, rest[1:end_idx]
        return key, rest[1:]

    if rest.startswith('"'):
        end_idx = -1
        i = 1
        while i < len(rest):
            if rest[i] == '"':
                backslashes = 0
                j = i - 1
                while j >= 1 and rest[j] == "\\":
                    backslashes += 1
                    j -= 1
                if backslashes % 2 == 0:
                    end_idx = i
                    break
            i += 1

        raw_val = rest[1:end_idx] if end_idx != -1 else rest[1:]

        val = (
            raw_val.replace("\\\\", "\x00")
            .replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace("\x00", "\\")
        )
        return key, val

    # Unquoted value: inline comment must be preceded by whitespace
    comment_pos = -1
    for match_str in (" #", "\t#"):
        pos = rest.find(match_str)
        if pos != -1 and (comment_pos == -1 or pos < comment_pos):
            comment_pos = pos

    if comment_pos != -1:
        rest = rest[:comment_pos].rstrip()

    return key, rest


def load_dotenv(
    dotenv_path: str | os.PathLike[str] | None = None,
    override: bool = False,
) -> bool:
    """Load environment variables from a .env file into os.environ.

    Args:
        dotenv_path: Absolute or relative path to the .env file. If None,
            searches current working directory and parent directories.
        override: If True, overwrite existing variables in os.environ.

    Returns:
        True if a .env file was found and processed, False otherwise.
    """
    if dotenv_path is not None:
        target_path = Path(dotenv_path)
    else:
        found = _find_dotenv()
        if found is None:
            return False
        target_path = found

    if not target_path.is_file():
        return False

    try:
        content = target_path.read_text(encoding="utf-8")
    except OSError:
        return False

    for line in content.splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value

    return True


def env_str(name: str) -> str | None:
    """Read a trimmed string env var. None if unset or empty after strip."""
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def env_int(name: str, default: int) -> int:
    """Read an integer env var with fallback and warning on invalid format."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        logger.warning("Ignoring invalid integer environment value for %s", name)
        return default


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean env var with truthy/falsy conversion."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_list_csv(name: str) -> list[str]:
    """Read a comma-separated list env var. Trims each item; drops empties."""
    raw = os.getenv(name)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]
