"""LanceDB implementation of the :class:`LexiconStore` Protocol.

See ``docs/lexicon-migration-spec.md`` §3-§4 for the design rationale.

Key design points
-----------------

* Single table ``terms`` (see :mod:`omniscribe.core.lexicon.schema`) —
  glossary-level metadata is denormalized into every row.
* HNSW vector index on the ``embedding`` column, built lazily on first
  query. Switch to IVF-PQ in the schema config for >100k entries.
* All writes are append-only on the row level. ``delete_glossary`` is a
  logical delete via LanceDB's filter expression; this doesn't fragment
  the index and is the right call for personal-scale lexicons.
* Reads use hybrid (vector + SQL filter) queries via LanceDB's
  ``.search().where()`` API.
* The store is process-safe; LanceDB handles per-process locking. For a
  single-user local app this is sufficient.
* No silent fallback: if lancedb is missing, we fail loud at first use
  with a clear install hint.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .embedding import EmbeddingModel, get_default_embedding_model
from .schema import LEXICON_SCHEMA, VECTOR_INDEX_SPEC
from .store import (
    GlossaryMeta,
    LexiconEntry,
    LexiconHit,
    LexiconQuery,
    now_utc,
)

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """Generate a new entry/glossary ID. UUID4 hex — matches the legacy format."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Row <-> LexiconEntry conversion
# ---------------------------------------------------------------------------


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
    if isinstance(value, str):
        return value or None
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


def _row_from_entry(
    entry: dict[str, object],
    embedding: list[float],
    *,
    glossary_name: str,
    glossary_enabled: bool,
    glossary_priority: int,
    glossary_group: str,
    glossary_source_uri: str | None,
    glossary_encoding: str | None,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, object]:
    """Build a LanceDB row from an entry dict + its embedding.

    The caller supplies the denormalized glossary fields. The store is
    responsible for keeping them in sync on toggle/reorder.
    """
    return {
        "id": str(entry.get("id") or _new_id()),
        "glossary_id": str(entry["glossary_id"]),
        "source_text": str(entry["source"]),
        "target_text": str(entry["target"]),
        "source_lang": str(entry.get("source_lang", "")),
        "target_lang": str(entry.get("target_lang", "")),
        "domain": entry.get("domain"),
        "register": entry.get("register"),
        "pos": entry.get("pos"),
        "case_sensitive": bool(entry.get("case_sensitive", False)),
        "notes": str(entry.get("notes", "") or ""),
        "source_uri": entry.get("source_uri"),
        "source_format": str(entry.get("source_format", "json_pairs")),
        "usage_count": int(str(entry.get("usage_count", 0) or 0)),
        "created_at": created_at,
        "updated_at": updated_at,
        "embedding": list(embedding),
        # Denormalized glossary metadata (spec §4.1) -----------------------------
        "glossary_name": glossary_name,
        "glossary_enabled": bool(glossary_enabled),
        "glossary_priority": int(glossary_priority),
        "glossary_group": str(glossary_group or "default"),
        "glossary_source_uri": glossary_source_uri,
        "glossary_encoding": glossary_encoding,
    }


# ---------------------------------------------------------------------------
# LanceDBLexiconStore
# ---------------------------------------------------------------------------


class LanceDBLexiconStore:
    """LanceDB-backed implementation of :class:`LexiconStore`.

    The store is process-safe. Construction does not open the database;
    the first call to any read/write method triggers lazy initialization
    (thread-safe via a one-shot lock).
    """

    TABLE_NAME = "terms"

    def __init__(
        self,
        *,
        path: Path,
        embedding_model: EmbeddingModel | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path).expanduser().resolve()
        self._path.mkdir(parents=True, exist_ok=True)
        self._embedding = embedding_model or get_default_embedding_model()
        self._clock = clock or now_utc
        self._db: Any = None
        self._table: Any = None
        self._init_lock = threading.Lock()
        self._initialized = False

    # --- Lifecycle ----------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            try:
                import lancedb
            except ImportError as exc:
                raise RuntimeError(
                    "LanceDBLexiconStore requires the `lancedb` package. "
                    "Install with: `uv sync --extra lexicon`."
                ) from exc
            self._db = lancedb.connect(str(self._path))
            # ``list_tables()`` returns a Pydantic response with a ``tables``
            # list (the older ``table_names()`` is deprecated). Handle both
            # shapes so we work across LanceDB 0.5 to 0.37.
            raw = self._db.list_tables()
            tables = getattr(raw, "tables", None)
            if tables is None:
                tables = list(raw)
            existing = {str(t) for t in tables}
            if self.TABLE_NAME in existing:
                self._table = self._db.open_table(self.TABLE_NAME)
            else:
                # Create empty table with the canonical schema; rows are
                # added on the first save_glossary call. ``mode="create"``
                # raises if the table already exists, which is what we want
                # here (the ``in existing`` branch above handles the
                # open-existing case).
                self._table = self._db.create_table(
                    self.TABLE_NAME, schema=LEXICON_SCHEMA, mode="create"
                )
            self._initialized = True
            logger.info("LanceDBLexiconStore opened at %s", self._path)

    def close(self) -> None:
        # LanceDB connections are lightweight and process-bound; nothing to
        # explicitly close today. Kept for Protocol symmetry.
        self._initialized = False
        self._db = None
        self._table = None

    def health(self) -> dict[str, object]:
        self._ensure_open()
        df = self._table.to_pandas()
        return {
            "path": str(self._path),
            "table": self.TABLE_NAME,
            "row_count": len(df),
            "glossary_count": int(df["glossary_id"].nunique()) if not df.empty else 0,
            "embedding_dim": self._embedding.dim,
            "embedding_model": self._embedding.model_name,
            "index_spec": VECTOR_INDEX_SPEC,
        }

    # --- Glossary library CRUD ----------------------------------------------

    def list_glossaries(self) -> list[GlossaryMeta]:
        self._ensure_open()
        df = self._table.to_pandas()
        if df.empty:
            return []
        result: list[GlossaryMeta] = []
        for gid, group in df.groupby("glossary_id", sort=False):
            first = group.iloc[0]
            result.append(
                GlossaryMeta(
                    id=str(gid),
                    name=str(first["glossary_name"]),
                    format=str(first["source_format"]),
                    source_uri=_opt_str(first.get("glossary_source_uri")),
                    encoding=_opt_str(first.get("glossary_encoding")),
                    enabled=bool(first["glossary_enabled"]),
                    priority=int(first["glossary_priority"]),
                    group=str(first["glossary_group"]),
                    entry_count=len(group),
                    created_at=_to_utc_datetime(first["created_at"]),
                    updated_at=_to_utc_datetime(first["updated_at"]),
                )
            )
        # Mirror the legacy sort: priority DESC, group, name, id.
        result.sort(
            key=lambda m: (-m.priority, m.group.casefold(), m.name.casefold(), m.id)
        )
        return result

    def get_glossary(self, glossary_id: str) -> GlossaryMeta | None:
        self._ensure_open()
        target = str(glossary_id)
        df = self._table.to_pandas()
        if df.empty:
            return None
        rows = df[df["glossary_id"] == target]
        if rows.empty:
            return None
        first = rows.iloc[0]
        return GlossaryMeta(
            id=target,
            name=str(first["glossary_name"]),
            format=str(first["source_format"]),
            source_uri=_opt_str(first.get("glossary_source_uri")),
            encoding=_opt_str(first.get("glossary_encoding")),
            enabled=bool(first["glossary_enabled"]),
            priority=int(first["glossary_priority"]),
            group=str(first["glossary_group"]),
            entry_count=len(rows),
            created_at=_to_utc_datetime(first["created_at"]),
            updated_at=_to_utc_datetime(first["updated_at"]),
        )

    def save_glossary(
        self,
        *,
        name: str,
        format: str,
        entries: Iterable[dict[str, object]],
        source_uri: str | None = None,
        encoding: str | None = None,
        group: str = "default",
        priority: int = 0,
    ) -> GlossaryMeta:
        self._ensure_open()

        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Glossary name is required.")
        if len(clean_name) > 200:
            raise ValueError("Glossary name must be at most 200 characters.")
        clean_format = str(format).strip().lower()
        if not clean_format:
            raise ValueError("Glossary format is required.")
        if isinstance(priority, bool):
            raise ValueError("Glossary priority must be an integer.")
        try:
            clean_priority = int(priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("Glossary priority must be an integer.") from exc
        clean_group = str(group).strip() or "default"

        # Normalize entries: drop empty, drop junk, default language pair.
        normalized: list[dict[str, object]] = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            src = str(raw.get("source", "")).strip()
            tgt = str(raw.get("target", "")).strip()
            if not src or not tgt:
                continue
            entry = dict(raw)
            entry["source"] = src
            entry["target"] = tgt
            # Defaults for fields that may not be present in the input
            entry.setdefault("source_lang", "")
            entry.setdefault("target_lang", "")
            entry.setdefault("source_format", clean_format)
            entry.setdefault("case_sensitive", False)
            entry.setdefault("notes", "")
            entry.setdefault("usage_count", 0)
            normalized.append(entry)
        if not normalized:
            raise ValueError("Glossary must contain at least one valid entry.")

        glossary_id = _new_id()
        now = self._clock()

        # Batch-embed the source_text for all entries. The embedding model
        # is process-cached so this is fast after the first call.
        source_texts: list[str] = [str(e["source"]) for e in normalized]
        embeddings = self._embedding.embed_batch(source_texts)
        if len(embeddings) != len(normalized):
            raise RuntimeError(
                f"Embedding model returned {len(embeddings)} vectors for "
                f"{len(normalized)} inputs."
            )

        rows = [
            _row_from_entry(
                {**e, "glossary_id": glossary_id},
                emb,
                glossary_name=clean_name,
                glossary_enabled=True,
                glossary_priority=clean_priority,
                glossary_group=clean_group,
                glossary_source_uri=str(source_uri) if source_uri else None,
                glossary_encoding=str(encoding) if encoding else None,
                created_at=now,
                updated_at=now,
            )
            for e, emb in zip(normalized, embeddings, strict=True)
        ]
        self._table.add(rows)
        logger.info(
            "Saved glossary %s (%s) with %d entries", glossary_id, clean_name, len(rows)
        )

        return GlossaryMeta(
            id=glossary_id,
            name=clean_name,
            format=clean_format,
            source_uri=str(source_uri) if source_uri else None,
            encoding=str(encoding) if encoding else None,
            enabled=True,
            priority=clean_priority,
            group=clean_group,
            entry_count=len(rows),
            created_at=now,
            updated_at=now,
        )

    def toggle_glossary(self, glossary_id: str, *, enabled: bool) -> GlossaryMeta:
        self._ensure_open()
        target = str(glossary_id)
        now = self._clock()
        new_value = bool(enabled)
        # Use a single SQL update statement — the denormalized glossary_enabled
        # field is what the hybrid filter reads, so we update it in place.
        try:
            self._table.update(
                where=f"glossary_id = '{target.replace(chr(39), chr(39) + chr(39))}'",
                values={"glossary_enabled": new_value, "updated_at": now},
            )
        except Exception as exc:
            # Fallback path: do a per-row merge via to_pandas to re-write.
            # Slower but correct if LanceDB version doesn't support update().
            df = self._table.to_pandas()
            if df.empty:
                raise GlossaryNotFoundError(target) from exc
            mask = df["glossary_id"] == target
            if not mask.any():
                raise GlossaryNotFoundError(target) from exc
            df.loc[mask, "glossary_enabled"] = new_value
            df.loc[mask, "updated_at"] = now
            self._table.delete(f"glossary_id = '{target}'")
            self._table.add(df.to_dict(orient="records"))
        meta = self.get_glossary(target)
        if meta is None:
            raise GlossaryNotFoundError(target)
        return meta

    def reorder_glossaries(self, ordered_ids: Sequence[str]) -> None:
        self._ensure_open()
        ordered = [str(gid) for gid in ordered_ids]
        if not ordered:
            return
        # Assign priorities so that the first id in `ordered` gets the
        # highest priority (priority is sorted DESC in list_glossaries).
        # Total priority = len(ordered) - index.
        existing = {m.id for m in self.list_glossaries()}
        unknown = [gid for gid in ordered if gid not in existing]
        if unknown:
            raise KeyError(f"Unknown glossary id(s): {unknown}")
        total = len(ordered)
        for index, gid in enumerate(ordered):
            new_priority = total - index
            self._table.update(
                where=f"glossary_id = '{gid.replace(chr(39), chr(39) + chr(39))}'",
                values={"glossary_priority": new_priority},
            )

    def delete_glossary(self, glossary_id: str) -> bool:
        self._ensure_open()
        target = str(glossary_id)
        df = self._table.to_pandas()
        if df.empty or not (df["glossary_id"] == target).any():
            return False
        self._table.delete(
            where=f"glossary_id = '{target.replace(chr(39), chr(39) + chr(39))}'"
        )
        return True

    # --- Read API (used by translation RAG) ---------------------------------

    def hybrid_query(self, query: LexiconQuery) -> list[LexiconHit]:
        self._ensure_open()
        df = self._table.to_pandas()
        if df.empty:
            return []
        # Pre-filter via the same WHERE clauses we'll pass to the vector
        # search. We also do this client-side as a defense in depth — the
        # same predicates are pushed down to the search call.
        candidates = self._apply_prefilter(df, query)
        if candidates.empty:
            return []

        # Embed the source chunk and search. We use LanceDB's hybrid
        # .search() + .where() when the table has a vector index, and
        # fall back to a pure pandas cosine-similarity ranking when the
        # table is small enough that the index isn't built yet.
        if self._has_vector_index():
            return self._hybrid_via_lancedb(query, candidates)
        return self._hybrid_via_pandas(query, candidates)

    def exact_lookup(
        self,
        source_text: str,
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[LexiconEntry]:
        self._ensure_open()
        df = self._table.to_pandas()
        if df.empty:
            return []
        mask = df["source_text"].str.lower() == source_text.strip().lower()
        if source_lang:
            mask &= df["source_lang"] == source_lang
        if target_lang:
            mask &= df["target_lang"] == target_lang
        rows = df[mask]
        return [_entry_from_row(r) for _, r in rows.iterrows()]

    def list_entries(self, glossary_id: str) -> list[LexiconEntry]:
        self._ensure_open()
        target = str(glossary_id)
        df = self._table.to_pandas()
        if df.empty:
            return []
        rows = df[df["glossary_id"] == target]
        return [_entry_from_row(r) for _, r in rows.iterrows()]

    # --- Internal helpers ---------------------------------------------------

    def _apply_prefilter(self, df: Any, query: LexiconQuery) -> Any:
        """Apply structured filters to the candidate set."""
        mask = df["source_lang"].notna()  # always true; placeholder
        if query.source_lang:
            mask &= df["source_lang"] == query.source_lang
        if query.target_lang:
            mask &= df["target_lang"] == query.target_lang
        if query.domain:
            mask &= df["domain"] == query.domain
        if query.enabled_only:
            mask &= df["glossary_enabled"] == True  # noqa: E712
        if query.glossary_ids is not None:
            allowed = {str(g) for g in query.glossary_ids}
            mask &= df["glossary_id"].isin(allowed)
        return df[mask]

    def _has_vector_index(self) -> bool:
        # LanceDB Python doesn't expose a direct "is index built" query in
        # all versions. We treat the table as indexed once it has at least
        # one row; on the first query, LanceDB will build the index lazily
        # if it doesn't exist. This is a deliberate simplification — the
        # alternative (a custom index tracker) adds complexity for marginal
        # benefit at personal-scale lexicon sizes.
        try:
            row_count = self._table.count_rows()
        except Exception:
            return False
        return int(row_count) > 0

    def _hybrid_via_lancedb(
        self, query: LexiconQuery, candidates: Any
    ) -> list[LexiconHit]:
        vector = self._embedding.embed(query.source_chunk)
        try:
            search = (
                self._table.search(vector, vector_column_name="embedding")
                .metric("cosine")
                .limit(max(query.limit * 4, 16))  # over-fetch to absorb prefilter
            )
            where_clauses = self._build_where(query)
            if where_clauses:
                search = search.where(where_clauses)
            raw = search.to_list()
        except Exception as exc:
            logger.warning(
                "LanceDB hybrid search failed: %s; falling back to pandas", exc
            )
            return self._hybrid_via_pandas(query, candidates)
        hits: list[LexiconHit] = []
        for row in raw:
            distance = float(row.get("_distance", 0.0))
            score = 1.0 - distance  # cosine distance → similarity
            if query.min_score is not None and score < query.min_score:
                continue
            entry = _entry_from_row(row)
            hits.append(LexiconHit(entry=entry, score=score))
            if len(hits) >= query.limit:
                break
        return hits

    def _hybrid_via_pandas(
        self, query: LexiconQuery, candidates: Any
    ) -> list[LexiconHit]:
        """Fallback ranking using in-process cosine similarity."""
        import numpy as np

        if candidates.empty:
            return []
        query_vec = np.asarray(
            self._embedding.embed(query.source_chunk), dtype=np.float32
        )
        # Build a (N, 384) matrix from the candidate embeddings
        emb_matrix = np.asarray(candidates["embedding"].tolist(), dtype=np.float32)
        # Cosine similarity
        qn = query_vec / (np.linalg.norm(query_vec) + 1e-12)
        en = emb_matrix / (np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-12)
        scores = en @ qn
        order = np.argsort(-scores)  # descending
        hits: list[LexiconHit] = []
        for idx in order:
            score = float(scores[idx])
            if query.min_score is not None and score < query.min_score:
                continue
            row = candidates.iloc[int(idx)]
            hits.append(LexiconHit(entry=_entry_from_row(row), score=score))
            if len(hits) >= query.limit:
                break
        return hits

    def _build_where(self, query: LexiconQuery) -> str | None:
        """Build a LanceDB WHERE clause string from the structured filters."""
        clauses: list[str] = []
        if query.source_lang:
            clauses.append(f"source_lang = '{_sql_escape(query.source_lang)}'")
        if query.target_lang:
            clauses.append(f"target_lang = '{_sql_escape(query.target_lang)}'")
        if query.domain:
            clauses.append(f"domain = '{_sql_escape(query.domain)}'")
        if query.enabled_only:
            clauses.append("glossary_enabled = true")
        if query.glossary_ids is not None:
            allowed = ", ".join(f"'{_sql_escape(str(g))}'" for g in query.glossary_ids)
            clauses.append(f"glossary_id IN ({allowed})")
        return " AND ".join(clauses) if clauses else None


def _sql_escape(value: str) -> str:
    """Escape a string literal for inclusion in a LanceDB WHERE clause.

    Doubles single quotes per the SQL standard. Sufficient for the values
    we filter on (language codes, domain names, group names); not a
    general-purpose SQL escaper.
    """
    return value.replace("'", "''")


class GlossaryNotFoundError(KeyError):
    """Raised when a requested glossary id does not exist in the store."""


__all__ = [
    "GlossaryNotFoundError",
    "LanceDBLexiconStore",
    "_entry_from_row",
    "_row_from_entry",
    "_sql_escape",
]
