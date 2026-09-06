"""Tiny entry-point wrapper for the PyInstaller bundle.

Phase 4.4 of the remediation plan introduces a single-binary Windows
distribution of the OmniScribe FastAPI server (RFC 001, Option A).
The PyInstaller spec at the repo root analyses this file as its
single entry point, so that:

1. The spec stays small and reviewable (one explicit entry, no
   ``-m`` magic to debug).
2. Users running from source can also do ``python scripts/run_server.py``
   instead of going through the ``omniscribe-server`` console
   script, which is a friendlier dev affordance on platforms where
   the venv's bin/ isn't on ``PATH`` (e.g. some IDE run-configs).
3. The actual server module (``omniscribe.server``) is unchanged.
   PyInstaller's static analysis picks it up via the
   ``from omniscribe.server import main`` line below, plus the
   ``hiddenimports`` list in the spec for the cordis-plugin modules
   that are loaded dynamically at runtime.

See ``omniscribe_server.spec`` for the bundle build, and
``docs/deployment/windows-bundle.md`` for the end-user-facing
install + run guide.
"""

from __future__ import annotations

import argparse

from omniscribe.server import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the OmniScribe API server",
        add_help=False,
    )
    parser.parse_known_args()
    main()
