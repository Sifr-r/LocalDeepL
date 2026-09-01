"""Regression test for C2: destructive fallback in ``toggle_glossary``.

The audit found that the fallback path in ``LanceDBLexiconStore.toggle_glossary``
performs ``self._table.delete(where=...)`` followed by ``self._table.add(records)``
with no rollback. If ``add`` fails after ``delete`` succeeds, the glossary rows are
silently lost.

The fix re-orders the operations: build a fresh Arrow table from the updated
records, ``add`` it, and only ``delete`` the originals AFTER the new rows are
durably appended. A failed ``add`` leaves the original table untouched.

These tests inject a fake ``_table`` mock so we can simulate the failure mode
without spinning up a real LanceDB instance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

pa = pytest.importorskip("pyarrow")

from omniscribe.core.lexicon.lancedb_store import (  # noqa: E402
    GlossaryNotFoundError,
    LanceDBLexiconStore,
)


@pytest.fixture
def store_with_mock_table() -> LanceDBLexiconStore:
    """Build a store whose ``_ensure_open`` is a no-op so we can inject a fake table."""
    s = LanceDBLexiconStore.__new__(LanceDBLexiconStore)
    s._initialized = True
    s._db = MagicMock()
    s._init_lock = MagicMock()
    s._clock = MagicMock(return_value="2026-08-28T00:00:00Z")
    s._embedding = MagicMock()
    s._embedding.dim = 4
    s._embedding.model_name = "fake"
    return s


def _make_arrow_table(rows: list[dict[str, Any]]) -> pa.Table:  # type: ignore[name-defined]
    """Build a minimal pyarrow Table that mirrors the lexicon schema."""
    return pa.Table.from_pylist(rows)


def _mock_table_with_arrow(arrow_tbl: pa.Table) -> MagicMock:  # type: ignore[name-defined]
    """Build a mock ``_table`` whose ``to_arrow()`` returns ``arrow_tbl``."""
    tbl = MagicMock()
    tbl.to_arrow.return_value = arrow_tbl
    return tbl


def test_C2_toggle_glossary_atomic_swap_calls_add_before_delete(
    store_with_mock_table: LanceDBLexiconStore,
) -> None:
    """C2 fix: in the fallback path, ``add`` MUST run BEFORE ``delete``.

    The audit's bug: the old code did ``delete`` then ``add``. If ``add`` failed,
    rows were lost. The fix reverses the order so a failure of ``add`` is
    non-destructive.
    """
    from omniscribe.core.lexicon.store import GlossaryMeta

    rows = [
        {"glossary_id": "g1", "glossary_enabled": True, "updated_at": "earlier"},
        {"glossary_id": "g1", "glossary_enabled": True, "updated_at": "earlier"},
    ]
    arrow_tbl = _make_arrow_table(rows)
    fake_table = _mock_table_with_arrow(arrow_tbl)
    # Force the fallback: ``update`` raises.
    fake_table.update.side_effect = RuntimeError("simulated update failure")
    # ``add`` succeeds.
    fake_table.add = MagicMock(return_value=None)
    # ``delete`` records calls.
    fake_table.delete = MagicMock(return_value=None)

    store_with_mock_table._table = fake_table
    # Stub get_glossary so it returns a sentinel without trying to parse mocks.
    sentinel_meta = GlossaryMeta(
        id="g1",
        name="g1",
        format="json_pairs",
        source_uri=None,
        encoding=None,
        enabled=False,
        priority=0,
        group="default",
        entry_count=2,
        created_at="2026-08-28T00:00:00Z",  # type: ignore[arg-type]
        updated_at="2026-08-28T00:00:00Z",  # type: ignore[arg-type]
    )
    store_with_mock_table.get_glossary = MagicMock(return_value=sentinel_meta)  # type: ignore[method-assign]

    meta = store_with_mock_table.toggle_glossary("g1", enabled=False)
    assert meta is not None

    # Both ``add`` and ``delete`` were called.
    assert fake_table.add.called, "fallback path must call add()"
    assert fake_table.delete.called, "fallback path must call delete()"

    # The order MUST be add-before-delete.
    call_names = [c[0] for c in fake_table.mock_calls]
    assert call_names.index("add") < call_names.index("delete"), (
        f"Expected add-before-delete, got call order: {call_names}"
    )


def test_C2_toggle_glossary_preserves_original_rows_when_add_fails(
    store_with_mock_table: LanceDBLexiconStore,
) -> None:
    """C2 fix: when ``add`` fails, ``delete`` MUST NOT be called.

    This is the regression the audit flagged: a failed ``add`` after a successful
    ``delete`` leaves the table empty. The fix ensures ``delete`` is gated on a
    successful ``add``.
    """
    rows = [
        {"glossary_id": "g1", "glossary_enabled": True, "updated_at": "earlier"},
        {"glossary_id": "g1", "glossary_enabled": True, "updated_at": "earlier"},
    ]
    arrow_tbl = _make_arrow_table(rows)
    fake_table = _mock_table_with_arrow(arrow_tbl)
    fake_table.update.side_effect = RuntimeError("simulated update failure")
    fake_table.add.side_effect = RuntimeError("simulated add failure")
    fake_table.delete = MagicMock(return_value=None)

    store_with_mock_table._table = fake_table

    with pytest.raises(RuntimeError, match="simulated add failure"):
        store_with_mock_table.toggle_glossary("g1", enabled=False)

    # ``delete`` MUST NOT have been called — the original rows must remain intact.
    assert not fake_table.delete.called, (
        "C2 regression: ``delete`` was called despite ``add`` failing — "
        "this would have wiped the original glossary rows."
    )


def test_C2_toggle_glossary_missing_glossary_raises_even_in_fallback(
    store_with_mock_table: LanceDBLexiconStore,
) -> None:
    """C2 fix: if the glossary id does not exist, ``GlossaryNotFoundError`` is raised
    BEFORE any destructive ``delete`` is attempted."""
    # Empty arrow table → no rows to match → GlossaryNotFoundError.
    fake_table = _mock_table_with_arrow(_make_arrow_table([]))
    fake_table.update.side_effect = RuntimeError("simulated update failure")
    fake_table.add = MagicMock(return_value=None)
    fake_table.delete = MagicMock(return_value=None)

    store_with_mock_table._table = fake_table

    with pytest.raises(GlossaryNotFoundError):
        store_with_mock_table.toggle_glossary("nonexistent", enabled=False)

    # Neither add nor delete should have been called when no rows match.
    assert not fake_table.add.called
    assert not fake_table.delete.called
