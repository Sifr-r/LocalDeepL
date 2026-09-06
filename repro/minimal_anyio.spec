# -*- mode: python ; coding: utf-8 -*-
# Minimal PyInstaller spec for the anyio bundling bug.
# Run with:  uv run --with pyinstaller --no-sync pyinstaller minimal_anyio.spec
# Output:    dist/minimal-anyio/minimal-anyio.exe (or no .exe on POSIX)
#
# This spec is the smallest possible PyInstaller invocation that should
# bundle ``anyio.abc``. It exercises every mechanism PyInstaller provides
# for module discovery:
#
#   1. The entry script (``run_minimal.py``) explicitly imports
#      ``anyio.abc`` at the top level, so the static analyzer sees the
#      import edge.
#   2. ``collect_submodules("anyio")`` is the documented "exhaustive
#      walk" hook that pulls in every submodule reachable by import.
#   3. An explicit ``hiddenimports`` list names every anyio submodule
#      so even if (2) misses something, the spec covers it.
#
# On a working bundler, the resulting binary prints:
#     anyio <ver>: anyio.abc loaded ok
# On the bug, the binary exits with:
#     ModuleNotFoundError: No module named 'anyio'
#     (or 'anyio.abc', depending on whether the lazy import resolves
#     to a stub before failing)

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["run_minimal.py"],
    pathex=["."],
    hiddenimports=collect_submodules("anyio")
    + [
        "anyio",
        "anyio.abc",
        "anyio.streams",
        "anyio.from_thread",
        "anyio._backends",
        "anyio._backends.asyncio",
        "anyio._backends.trio",
        "anyio._core",
        "anyio._core._eventloop",
    ],
    excludes=[],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="minimal-anyio",
    console=True,
)
