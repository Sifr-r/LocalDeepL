"""Smoke test for the minimal anyio PyInstaller bundle.

Boots the binary produced by ``minimal_anyio.spec`` and reports whether
the program ran to completion (printing "anyio ... loaded ok") or
exited with a ModuleNotFoundError before reaching main().

Usage:
    uv run python smoke.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
BIN_NAME = "minimal-anyio.exe" if sys.platform == "win32" else "minimal-anyio"
BINARY = DIST / BIN_NAME


def main() -> int:
    if not BINARY.exists():
        print(f"FAIL: binary not found at {BINARY}")
        return 2
    print(f"binary: {BINARY}")
    print(f"size:   {BINARY.stat().st_size / 1024:.1f} KB")
    print(f"running: {BINARY.name}")
    result = subprocess.run([str(BINARY)], capture_output=True, text=True, timeout=30)
    print(f"exit:    {result.returncode}")
    print(f"stdout:  {result.stdout!r}")
    print(f"stderr:  {result.stderr!r}")
    if result.returncode == 0 and "loaded ok" in result.stdout:
        print("\nPASS: bundle imports anyio.abc at runtime")
        return 0
    if "ModuleNotFoundError" in result.stderr and "anyio" in result.stderr:
        print("\nFAIL: ModuleNotFoundError on anyio — bug reproduces")
        return 1
    print("\nFAIL: unexpected outcome")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
