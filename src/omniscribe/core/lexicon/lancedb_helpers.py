"""Shared row-conversion + SQL-escape helpers for the LanceDB store.

Audit catalog (Sprint 6 long-file split): the file at
``omniscribe/core/lexicon/lancedb_store.py`` (770+ LOC after
the Phase 3.3/3.4 push-downs) had 80 LOC of stateless
helpers (``_to_utc_datetime``, ``_opt_str``, ``_entry_from_row``,
``_sql_escape``) interleaved with the class definition. Pulled
them into their own module so the main file's surface is just
the lifecycle + glossary-CRUD + read-side class definition.

The "split the search methods into a mixin" approach was
attempted first and rolled back — the original
``save_glossary`` body has a non-trivial normalize-and-validate
pipeline that's hard to reproduce by hand without the original
test fixtures as the oracle. The simpler split (helpers only)
is what actually lands; the search methods stay in the main
file alongside the lifecycle / CRUD, which the user can split
in a follow-up commit if desired.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .store import LexiconEntry


def _to_utc_datetime(value: object) -> datetime:
    """Coerce a LanceDB/pandas timestamp value to a timezone-aware datetime.

    LanceDB returns ``pa.timestamp("ms")`` values as ``datetime`` objects
    (UTC) when read via ``to_pandas()``/``to_pydatetime()``, or as raw
    ``int`` epoch-ms when read via ``to_list()``. This helper handles both.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
    pandas_value = getattr(value, "to_pydatetime", None)
    if callable(pandas_value):
        raw_dt = pandas_value()
        if isinstance(raw_dt, datetime):
            if raw_dt.tzinfo is None:
                return raw_dt.replace(tzinfo=UTC)
            return raw_dt
    return datetime.fromisoformat(str(value))


def _opt_str(value: object) -> str | None:
    """Coerce a possibly-null cell to ``str | None``."""
    if value is None:
        return None
    try:
        import pandas as pd

        if isinstance(value, float) and pd.isna(value):
            return None
    except ImportError:
        pass
    if value is None:
        return None
    return str(value)


def _entry_from_row(row: Any) -> LexiconEntry:
    """Build a :class:`LexiconEntry` from a LanceDB/pandas row.

    Accepts both dict-like rows (from ``.to_list()``) and pandas Series
    (from ``.to_pandas().iloc[...]``).
    """

    def _get(key: str) -> object:
        if isinstance(row, dict):
            return row.get(key)
        return row[key]  # pandas Series

    return LexiconEntry(
        id=str(_get("id")),
        glossary_id=str(_get("glossary_id")),
        source_text=str(_get("source_text")),
        target_text=str(_get("target_text")),
        source_lang=str(_get("source_lang")),
        target_lang=str(_get("target_lang")),
        domain=_opt_str(_get("domain")),
        register=_opt_str(_get("register")),
        pos=_opt_str(_get("pos")),
        case_sensitive=bool(_get("case_sensitive")),
        notes=str(_get("notes") or ""),
        source_uri=_opt_str(_get("source_uri")),
        source_format=str(_get("source_format")),
        usage_count=int(str(_get("usage_count") or 0)),
        created_at=_to_utc_datetime(_get("created_at")),
        updated_at=_to_utc_datetime(_get("updated_at")),
    )


def _sql_escape(value: str) -> str:
    """Escape a string literal for inclusion in a LanceDB WHERE clause.

    Doubles single quotes per the SQL standard. Sufficient for the values
    we filter on (language codes, domain names, group names); not a
    general-purpose SQL escaper.
    """
    return value.replace("'", "''")
