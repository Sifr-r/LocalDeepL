"""Shared helpers for scripts in this directory.

Every standalone diagnostic / debug / visualization script under ``scripts/``
needs the same two things on import: a stable project root path, and a
``sys.path`` entry that lets ``import omniscribe.…`` resolve from ``src/``.

Rather than copy-paste::

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

into every script, callers can do::

    from _common import PROJECT_ROOT, setup_sys_path

    setup_sys_path()

``PROJECT_ROOT`` is the absolute path to the OmniScribe repo root (the
directory *above* this file's parent ``scripts/`` directory). ``setup_sys_path``
is idempotent and safe to call multiple times.

How to run any script that uses this helper::

    uv run python scripts/visualize_bboxes.py
    uv run python scripts/debug_alignment.py examples/hybrid.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Absolute path to the OmniScribe repo root."""

# Convenience alias for existing scripts that already use ``ROOT = …``.
ROOT: Path = PROJECT_ROOT

_SRC = PROJECT_ROOT / "src"


def setup_sys_path() -> None:
    """Add ``<project_root>/src`` to :data:`sys.path` if not already present.

    Idempotent. Imports the package from the working tree instead of relying
    on ``pip install -e .`` so the scripts work on a fresh clone.
    """
    src_str = str(_SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
