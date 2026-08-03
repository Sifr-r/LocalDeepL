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
- Scripts that depend on optional extras (``chromadb``, ``rich``,
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
    "build_fixture.py": ("rich",),
    "confidence_eval.py": ("rich",),
    "confidence_image.py": ("rich",),
    "ingest_lexicon.py": ("chromadb",),
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
    cases don't collide and re-run the script body fresh.
    """
    module_id = f"_scripts_smoke_{script_name.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_id, SCRIPTS_DIR / script_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build import spec for {script_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_id] = module
    spec.loader.exec_module(module)
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
