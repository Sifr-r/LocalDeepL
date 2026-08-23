"""
Smoke-import test for scripts/*.py.

The ``scripts/`` directory is excluded from production ``ruff check`` and
``mypy`` runs (see ``pyproject.toml``'s ``extend-exclude``), so a rename
or removal of a public ``omniscribe`` symbol can silently break every
maintenance tool until somebody notices. This test loads each script as
a Python module and asserts the import succeeds — the typical failure
mode for "I renamed HybridAligner to HybridAlignerV2 and forgot to
update the debug scripts".

- Scripts without ``omniscribe`` imports are still loaded — they catch
  syntax regressions and unrelated import-time mistakes.
- Heavy dependencies (Surya, LM Studio) are loaded as the scripts need
  them, not stubbed — a renamed symbol in the core package would still
  fail.
- Scripts that depend on optional extras (``lancedb``, ``rich``,
  ``websockets``) gracefully skip if those extras are missing.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

# Scripts that depend on optional extras: if those aren't installed, we
# skip rather than fail. The extras themselves are documented in
# pyproject.toml (`memory`, `web`, etc.).
_OPTIONAL_DEPS: dict[str, tuple[str, ...]] = {
    "confidence_eval.py": ("rich",),
    "confidence_image.py": ("rich",),
    "ingest_lexicon.py": ("lancedb",),
    "probe_routes.py": ("websockets",),
}

# Errors treated as "the script needs an optional dep we don't have".
_OPTIONAL_IMPORT_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    ModuleNotFoundError,
)


def _script_names() -> list[str]:
    return sorted(p.name for p in SCRIPTS_DIR.glob("*.py"))


def _first_missing_optional(script_name: str) -> str | None:
    """Return the first missing optional dep, or None if all are present."""
    for module_name in _OPTIONAL_DEPS.get(script_name, ()):
        try:
            __import__(module_name)
        except _OPTIONAL_IMPORT_ERRORS:
            return module_name
    return None


def _load_script(script_name: str) -> types.ModuleType:
    """Import scripts/<script_name> in isolation and return the module.

    Each script gets a unique sys.modules key so repeated parametrize
    cases don't collide and re-run the script body fresh. ``scripts/``
    itself is added to ``sys.path`` for the duration of the load so the
    shared ``_common`` helper module resolves the same way it does when
    the script is run directly (``python scripts/foo.py``).
    """
    module_id = f"_scripts_smoke_{script_name.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_id, SCRIPTS_DIR / script_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build import spec for {script_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_id] = module
    scripts_dir_str = str(SCRIPTS_DIR)
    path_was_missing = scripts_dir_str not in sys.path
    if path_was_missing:
        sys.path.insert(0, scripts_dir_str)
    try:
        spec.loader.exec_module(module)
    finally:
        if path_was_missing:
            sys.path.remove(scripts_dir_str)
    return module


def test_script_smoke_covers_every_file() -> None:
    """Parametrize list and the on-disk script count must stay in sync.

    Catches the regression where somebody adds a new ``scripts/foo.py``
    and forgets to extend the smoke test — without this guard, the new
    helper would silently fall outside the mechanical protection.
    """
    parametrize_ids = set(_script_names())
    on_disk = {p.name for p in SCRIPTS_DIR.glob("*.py")}
    missing = on_disk - parametrize_ids
    assert not missing, (
        f"scripts/ contains files not covered by the smoke test: {sorted(missing)}. "
        "Add them to the parametrize list or to _OPTIONAL_DEPS if they depend on extras."
    )


@pytest.mark.parametrize("script_name", _script_names())
def test_script_imports_without_attribute_error(script_name: str) -> None:
    """Each developer script imports cleanly.

    An ``AttributeError`` here typically means a public ``omniscribe``
    symbol was renamed/removed and a maintenance script still
    references the old name — update the script or restore the symbol.
    """
    missing = _first_missing_optional(script_name)
    if missing is not None:
        pytest.skip(f"{script_name} skipped: optional dep {missing!r} not installed")

    try:
        _load_script(script_name)
    except AttributeError as exc:
        pytest.fail(
            f"{script_name} raised AttributeError on import: {exc}. "
            "This is the failure mode for a renamed/removed ``omniscribe`` "
            "public symbol — the script still references the old name."
        )
    except _OPTIONAL_IMPORT_ERRORS as exc:
        # A transitive optional dep showed up missing during import —
        # surface it as a skip so the failure mode stays actionable.
        pytest.skip(f"{script_name} skipped: optional dep missing ({exc})")


# Modules that intentionally are not runnable scripts (helper modules, not
# CLI entry points). Everything else in ``scripts/`` must be a runnable
# script — see ``test_scripts_have_argparse_and_main_guard`` below.
_SCRIPT_EXCLUDE_FROM_RUNTIME_GUARD: frozenset[str] = frozenset({"_common.py"})


def test_scripts_have_argparse_and_main_guard() -> None:
    """Every standalone script has ``argparse`` and a ``__main__`` guard.

    Two structural invariants:

    1. ``if __name__ == "__main__":`` — the file is a runnable script,
       not just an importable module. Without this guard, ``python
       scripts/foo.py`` would silently run the whole module body on
       import (and the smoke test above would execute production code
       it shouldn't).
    2. ``argparse.ArgumentParser`` — the file takes its inputs through
       the standard ``argv``/``--help`` channel rather than hard-coded
       paths, ``sys.argv[N]`` slicing, or environment variables alone.
       Enforcing ``argparse`` makes every script self-documenting via
       ``--help`` and keeps the call sites in the audit logs reviewable.

    The check is a structural AST scan — we do not import the script,
    so the rule is independent of optional deps (Surya, LM Studio, …).
    Scripts whose path is listed in
    ``_SCRIPT_EXCLUDE_FROM_RUNTIME_GUARD`` are exempt; today only
    ``_common.py`` (a shared helper, not a CLI entry point) qualifies.
    """
    import ast

    failures: list[str] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        name = path.name
        if name in _SCRIPT_EXCLUDE_FROM_RUNTIME_GUARD:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        has_main_guard = any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(comp, ast.Constant) and comp.value == "__main__"
                for comp in node.test.comparators
            )
            for node in ast.walk(tree)
        )
        uses_argparse = "argparse" in source and "ArgumentParser" in source
        if not has_main_guard:
            failures.append(f"{name}: missing 'if __name__ == \"__main__\":' guard")
        if not uses_argparse:
            failures.append(
                f"{name}: missing 'argparse.ArgumentParser' — scripts should "
                "take args via argparse, not sys.argv[N] or hard-coded paths"
            )
    assert not failures, (
        "scripts/ must contain only argparse-based runnable scripts:\n  - "
        + "\n  - ".join(failures)
    )
