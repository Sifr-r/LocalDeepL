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
from typing import Any, Final

logger = logging.getLogger(__name__)

# Standard falsy / disable string values recognized across configuration and env checks.
__all__ = [
    "DISABLE_STRINGS",
    "ENABLE_STRINGS",
    "env_bool",
    "env_int",
    "env_list_csv",
    "env_str",
    "load_dotenv",
    "parse_bool",
    "update_dotenv",
]

ENABLE_STRINGS: Final[frozenset[str]] = frozenset(
    {"1", "true", "yes", "on", "y", "enabled"}
)
DISABLE_STRINGS: Final[frozenset[str]] = frozenset(
    {"0", "false", "no", "off", "n", "disabled"}
)


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


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse a boolean or string into a bool using ENABLE_STRINGS / DISABLE_STRINGS."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    val_str = str(value).strip().lower()
    if val_str in ENABLE_STRINGS:
        return True
    if val_str in DISABLE_STRINGS:
        return False
    return default


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean env var with canonical truthy/falsy conversion."""
    value = os.getenv(name)
    if value is None:
        return default
    return parse_bool(value, default=default)


def env_list_csv(name: str) -> list[str]:
    """Read a comma-separated list env var. Trims each item; drops empties."""
    raw = os.getenv(name)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def update_dotenv(
    entries: dict[str, Any],
    dotenv_path: str | os.PathLike[str] | None = None,
) -> bool:
    """Update or insert key-value pairs into a .env file and sync to os.environ.

    Preserves existing comments, section headers, and untouched variables.

    Args:
        entries: Dictionary of environment variable names to their new values.
        dotenv_path: Path to the .env file. If None, searches current directory
            and parent directories; if not found, creates .env in current directory.

    Returns:
        True if the .env file was successfully updated.
    """
    if not entries:
        return True

    if dotenv_path is not None:
        target_path = Path(dotenv_path)
    else:
        found = _find_dotenv()
        target_path = found if found is not None else (Path.cwd() / ".env")

    # Format values for .env
    formatted_entries: dict[str, str] = {}
    for k, v in entries.items():
        if v is None:
            formatted_entries[k] = ""
        elif isinstance(v, bool):
            formatted_entries[k] = "true" if v else "false"
        else:
            formatted_entries[k] = str(v)

    lines: list[str] = []
    if target_path.is_file():
        try:
            content = target_path.read_text(encoding="utf-8")
            lines = content.splitlines()
        except OSError as exc:
            logger.warning("Failed to read .env file at %s: %s", target_path, exc)
            lines = []

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        prefix = ""
        eval_line = stripped
        if eval_line.startswith("export ") or eval_line.startswith("export\t"):
            prefix = eval_line[:7]
            eval_line = eval_line[7:].lstrip()

        if "=" in eval_line:
            key = eval_line.split("=", 1)[0].strip()
            if key in formatted_entries:
                val = formatted_entries[key]
                new_lines.append(f"{prefix}{key}={val}")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    # Append any keys that weren't present in the original file
    missing_keys = [k for k in formatted_entries if k not in updated_keys]
    if missing_keys:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for k in missing_keys:
            new_lines.append(f"{k}={formatted_entries[k]}")

    try:
        target_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write .env file at %s: %s", target_path, exc)
        return False

    # Sync to live os.environ
    for k, v in formatted_entries.items():
        os.environ[k] = v

    return True
