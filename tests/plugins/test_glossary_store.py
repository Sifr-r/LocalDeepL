"""``LexiconProvider`` lazy-load semantics.

The provider defers the ``omniscribe.core.lexicon`` import to first
use so the plugin can boot in images without the ``lexicon`` extra
(pyarrow is a hard import inside that module). Pedantic review 9.6:
the previous code cached ``_tried = True`` *before* the import
attempt, so a single ``ImportError`` permanently disabled the
provider — a later ``uv sync --extra lexicon`` (operator installs
the extra mid-run) had no chance to take effect. The fix retries
the import on every call until the store materialises.

These tests simulate the failure / recovery sequence by patching
``omniscribe.core.lexicon`` out of ``sys.modules`` for the failure
phase and reinstating it for the recovery phase.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from omniscribe.plugins.glossary.store import LexiconProvider


@pytest.fixture
def fresh_provider(tmp_path: Path) -> LexiconProvider:
    return LexiconProvider(tmp_path / "lexicon")


def test_get_returns_none_on_import_error(
    fresh_provider: LexiconProvider, caplog: pytest.LogCaptureFixture
) -> None:
    """When the import fails, the provider returns ``None`` and the
    route surfaces 503 with the install hint. The fix (pedantic
    9.6) does NOT cache the failure so a later retry can succeed.
    """
    with patch.dict(sys.modules, {"omniscribe.core.lexicon": None}):
        with caplog.at_level("WARNING", logger="omniscribe.plugins.glossary"):
            result = fresh_provider.get()
    assert result is None
    assert any("lexicon" in rec.message.lower() for rec in caplog.records)


def test_get_retries_after_initial_import_error(
    fresh_provider: LexiconProvider,
) -> None:
    """Pedantic 9.6: an ``ImportError`` on the first call must not
    permanent-cache the failure. A second call after the operator
    installs the extra must retry the import and succeed.

    Strategy: with ``omniscribe.core.lexicon`` patched out, the
    first call fails. We then reinject a stub module (simulating
    the operator running ``uv sync --extra lexicon``) and verify
    the second call returns the store.
    """
    fake_module = type(sys)("omniscribe.core.lexicon")
    fake_store = object()
    fake_module.LanceDBLexiconStore = lambda path: fake_store  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"omniscribe.core.lexicon": None}):
        first = fresh_provider.get()
    assert first is None
    # The provider must NOT have cached the failure — ``_tried``
    # is still False so the next call retries.
    assert fresh_provider._tried is False

    with patch.dict(sys.modules, {"omniscribe.core.lexicon": fake_module}):
        second = fresh_provider.get()
    assert second is fake_store
    # Now the successful import is cached.
    assert fresh_provider._tried is True


def test_get_caches_successful_initialisation(
    fresh_provider: LexiconProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once the import succeeds, the same store object is returned
    on every subsequent call without re-invoking the constructor.
    """
    fake_module = type(sys)("omniscribe.core.lexicon")
    construction_calls: list[Path] = []

    class _FakeStore:
        def __init__(self, path: Path) -> None:
            construction_calls.append(path)

    fake_module.LanceDBLexiconStore = _FakeStore  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "omniscribe.core.lexicon", fake_module)

    a = fresh_provider.get()
    b = fresh_provider.get()
    c = fresh_provider.get()

    assert a is b is c
    assert construction_calls == [fresh_provider._store_path]
