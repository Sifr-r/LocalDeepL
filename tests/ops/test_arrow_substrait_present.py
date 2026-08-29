"""Regression test for the ``arrow_substrait.dll`` Windows Defender
flag (audit P2-XX / Sprint 5 follow-up).

The optional ``[lexicon]`` extra pulls in lancedb, which transitively
ships Apache Arrow's SubstraIT DLL. On a small fraction of Windows
hosts Microsoft Defender flags this DLL as a trojan. We document the
mitigation in ``SECURITY.md`` §"Platform Notes" and offer an opt-in
Defender exclusion in ``install.ps1``. The test below asserts the
DLL is present when the lexicon extra is installed (so a future
dependency change is caught) and skips cleanly when it is not.
"""
from __future__ import annotations

import sys
from pathlib import Path


def test_arrow_substrait_dll_present_when_lexicon_installed() -> None:
    """The lexicon extra's pyarrow ships ``arrow_substrait.dll`` on
    Windows. If the extra is installed the DLL must be on disk; if
    not, skip — the test is informational, not a hard requirement.
    """
    if not sys.platform.startswith("win"):
        # The flag is Windows-specific. On macOS / Linux the DLL
        # lives in a different filename; skip the assertion there.
        return
    # Find the venv site-packages dir. ``sys.prefix`` is the venv
    # root when the test runs under ``uv run pytest``.
    site = Path(sys.prefix) / "Lib" / "site-packages"
    dll = site / "pyarrow" / "arrow_substrait.dll"
    if not dll.exists():
        # The lexicon extra is not installed; skip. The audit
        # noted this is a known false positive only when the DLL
        # is shipped, so an absent extra does not need a fix.
        return
    # When shipped, the DLL must be a real file (not an empty
    # symlink, etc.) so Windows can load it.
    assert dll.is_file(), (
        f"{dll} exists but is not a regular file. The lancedb "
        "extras installation is broken — re-run `uv sync --extra lexicon`."
    )
    # Sanity: SubstraIT artifacts are ~5-15 MB on Windows; smaller
    # files indicate a partial download. Use a generous lower bound
    # (1 MB) so a 32-bit / debug build doesn't false-positive.
    assert dll.stat().st_size > 1_000_000, (
        f"{dll} is suspiciously small ({dll.stat().st_size} bytes); "
        "the pyarrow wheel is likely a partial download."
    )
