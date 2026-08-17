"""F1.1 audit fix (P0): static regression test for the layering inversion.

Before the fix, ``core/llm_client.py`` and
``core/ocr/multi_format_client.py`` imported ``ProviderConfig`` and
``ProviderFormatEnum`` from ``omniscribe.api.schemas`` at runtime,
inverting the documented ``core`` < ``api`` layering. This made
``omniscribe.core`` unimportable in isolation (every consumer pulled
in the FastAPI / Pydantic / settings stack).

This test walks every module under ``src/omniscribe/core/`` and fails
if any of them imports from ``omniscribe.api`` at runtime. Imports
inside ``if TYPE_CHECKING:`` are allowed — they only run for type
checkers, not at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

# Walk the source tree. This test is intentionally static (no
# `importlib.import_module`) so it doesn't pay the cost of importing
# every core module and so a layering regression can't accidentally
# prevent the test itself from collecting.
CORE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "omniscribe"
    / "core"
)

# Lines that, if present at runtime, invert the layering. Both
# `from omniscribe.api...` and `import omniscribe.api...` are forbidden.
_UPWARD_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+omniscribe\.api|import\s+omniscribe\.api)\b"
)


def _is_inside_type_checking_block(source: str, line_index: int) -> bool:
    """Return True if the line at ``line_index`` is inside an
    ``if TYPE_CHECKING:`` (or ``if typing.TYPE_CHECKING:``) guard.

    TYPE_CHECKING is the special constant from ``typing`` that is
    ``False`` at runtime, so imports under it only run for static type
    checkers. They don't actually pull the API module at runtime, so
    they don't violate the layering.
    """
    lines = source.splitlines()
    for i in range(line_index - 1, -1, -1):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            continue
        return "TYPE_CHECKING" in line and line.startswith("if")
    return False


def _collect_core_modules() -> list[Path]:
    """List every Python file under ``src/omniscribe/core/``.

    Excludes ``__pycache__`` and ``__init__.py`` is included (we
    want to catch upward imports there too).
    """
    return sorted(
        p
        for p in CORE_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def test_core_does_not_import_api() -> None:
    """No ``omniscribe/core/*`` module imports from ``omniscribe.api`` at runtime.

    Allowed: imports inside ``if TYPE_CHECKING:`` blocks (static hints
    only, never executed at runtime). Forbidden: any other upward
    import. On violation, the test prints every offending line with
    its file:line so the regression is easy to fix.
    """
    violations: list[str] = []
    for path in _collect_core_modules():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines()):
            if not _UPWARD_IMPORT_RE.match(line):
                continue
            if _is_inside_type_checking_block(text, i):
                continue
            rel = path.relative_to(CORE_ROOT.parent.parent)
            violations.append(f"{rel}:{i + 1}: {line.strip()}")

    assert not violations, (
        "core/ modules must not import from omniscribe.api at runtime "
        "(layering inversion). Move the import target to omniscribe.core "
        "or guard it with `if TYPE_CHECKING:`. Violations:\n"
        + "\n".join(violations)
    )
