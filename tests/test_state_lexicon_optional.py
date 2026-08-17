"""Regression test: state.py must boot when the [lexicon] extra is missing.

Phase 5 dropped the legacy fallback in ``state.py`` to enforce the
[lexicon] install. That broke the server boot for users who don't use
the glossary feature at all (the import chain through
``omniscribe.core.lexicon`` reaches ``pyarrow`` unconditionally).

The real-world regression is captured in production by the boot
sequence: when ``omniscribe.core.lexicon`` is unimportable, the
module-level ``try``/``except`` in ``state.py`` logs a warning and
falls back to a ``_UnavailableGlossaryLibrary`` stub that raises a
clear ``uv sync --extra lexicon`` ``RuntimeError`` on any operation.

These tests verify the contract directly by calling the module-level
helpers. We don't simulate the missing-extra case in-process (the
``omniscribe.core.lexicon`` module is already cached in ``sys.modules``
once any other test in the suite has imported it, so a fresh
import-failure is hard to reproduce from inside the test session).
The fallback is exercised in production by anyone who installs
without ``uv sync --extra lexicon``.
"""

from __future__ import annotations

import pytest


def test_unavailable_glossary_library_raises_with_install_hint() -> None:
    """The stub library raises RuntimeError with a ``uv sync --extra lexicon`` hint."""
    from omniscribe.api.routers.state import _UnavailableGlossaryLibrary

    stub = _UnavailableGlossaryLibrary()
    with pytest.raises(RuntimeError, match=r"uv sync --extra lexicon"):
        stub.save(  # type: ignore[attr-defined]
            name="X", format="json_pairs", entries=[{"source": "a", "target": "A"}]
        )
    with pytest.raises(RuntimeError, match=r"uv sync --extra lexicon"):
        stub.get("any-id")  # type: ignore[attr-defined]
    # repr also surfaces the hint, so a debugger / log line is helpful.
    assert "uv sync --extra lexicon" in repr(stub)


def test_build_lexicon_store_returns_none_when_unavailable() -> None:
    """When [lexicon] isn't importable, ``_build_lexicon_store`` returns None."""
    from omniscribe.api.routers import state

    # Force the "unavailable" state by setting the availability flag.
    original_available = state._LEXICON_AVAILABLE
    state._LEXICON_AVAILABLE = False
    try:
        result = state._build_lexicon_store()
        assert result is None
    finally:
        state._LEXICON_AVAILABLE = original_available


def test_build_glossary_library_returns_stub_when_unavailable() -> None:
    """When [lexicon] isn't importable, ``_build_glossary_library`` returns the stub."""
    from omniscribe.api.routers import state
    from omniscribe.api.routers.state import _UnavailableGlossaryLibrary

    original_available = state._LEXICON_AVAILABLE
    state._LEXICON_AVAILABLE = False
    try:
        lib = state._build_glossary_library()
        assert isinstance(lib, _UnavailableGlossaryLibrary)
    finally:
        state._LEXICON_AVAILABLE = original_available
