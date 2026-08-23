"""SQLite-backed :class:`StateBackend` implementation.

This is the third pluggable backend in OmniScribe, sitting alongside
:class:`LocalStateBackend` (process-memory) and
:class:`RedisStateBackend` (Redis-server). It exists for the
"local-first" deployment shape where an operator wants
:func:`build_state_backend` to survive a process restart without
having to also run a Redis server.

Persistence shape
-----------------

A single SQLite database file (default
``<artifact_dir>/omniscribe-state.db``) holds four tables:

- ``omniscribe_artifact_text`` / ``omniscribe_artifact_meta`` /
  ``omniscribe_artifact_export`` — one per :class:`TextArtifactStore`,
  schema: ``id`` (32-char hex PK) / ``token`` / ``path`` (on-disk JSON
  file) / ``created_at`` (epoch s) / ``expires_at`` (epoch s).
  Backed by indexes on ``expires_at`` (TTL sweep) and ``created_at``
  (overflow eviction).
- ``omniscribe_jobs`` — append-only with ``id`` (PK) / ``inserted_at``
  (epoch s) / ``payload`` (JSON). Capped via SQL on every insert
  (oldest rows past ``max_jobs`` are deleted). The index is
  ``inserted_at DESC`` so ``list()`` is a single index scan.

Process-local stores
--------------------

The :class:`ProgressService` and :class:`OCRJobQueue` remain in-memory;
:class:`LexiconStore` is embedded LanceDB. The "recovery boundary" stays
one level up from this module: only artifact metadata, artifact files,
the on-disk lexicon database, and job history survive a restart.

Threading
---------

Each operation opens and closes its own ``sqlite3.Connection``.
WAL mode is enabled so concurrent readers never block writers and
crash safety is improved (``-journal`` file → ``-wal`` file).
``check_same_thread`` is the default; the connection is used
synchronously inside the caller's thread, which matches the
existing uvicorn single-worker request loop.

The :class:`StateBackend` Protocol in
:mod:`omniscribe.api.services.state.base` is the single source
of truth for the surface this module exposes.

See the *Known Tech Debt* section of ``AGENTS.md`` for the
project-level acknowledgement: "Job/artifact state is in-memory
only (``api/routers/state.py`` singletons) — restarts lose
history; no horizontal scaling." This backend is the persistent
opt-in for the local-first deployment shape; the Redis backend
remains the answer when you need horizontal scaling.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from omniscribe.api.services.artifacts import (
    DEFAULT_ARTIFACT_TTL_SECONDS,
    DEFAULT_MAX_ARTIFACT_ENTRIES,
    ArtifactAccessDeniedError,
    ArtifactNotFoundError,
    TextArtifactHandle,
    TextArtifactStore,
    _delete_file,
    _validate_artifact_id,
    _validate_token,
)
from omniscribe.api.services.config_store import SQLiteConfigStore
from omniscribe.api.services.jobs import (
    JobHistory,
    JobRecord,
    JobStatus,
    _clean_duration,
    _clean_failed_pages,
    _clean_optional_text,
    _clean_required_text,
    _clean_status,
    _current_timestamp,
)
from omniscribe.api.services.ocr.jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService
from omniscribe.core.lexicon import (
    LanceDBLexiconStore,
    LexiconStore,
    get_default_embedding_model,
)

_ARTIFACT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS {table}_expires_at_idx ON {table}(expires_at);
CREATE INDEX IF NOT EXISTS {table}_created_at_idx ON {table}(created_at);
"""

_JOBS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS omniscribe_jobs (
    id TEXT PRIMARY KEY,
    inserted_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS omniscribe_jobs_inserted_at_idx
    ON omniscribe_jobs(inserted_at DESC);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a short-lived SQLite connection with WAL mode enabled."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=30.0)
    # WAL mode gives concurrent readers + a single writer without
    # blocking the request loop, and survives process crashes (the
    # next open auto-recovers the WAL). foreign_keys is not needed
    # for our schema but is set for forward-compat.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class SQLiteTextArtifactStore(TextArtifactStore):
    """Token-bound text-artifact metadata in SQLite, JSON files on disk.

    Mirrors the in-memory :class:`TextArtifactStore` contract: TTL
    is enforced on every read, ``max_entries`` is enforced via
    SQLite on every write, and ``clear()`` removes both the rows
    and the backing files. The base class's ``create`` method is
    reused unchanged because it only touches ``put`` (overridden
    here) and the on-disk ``write_page_text_atomic`` helper.
    """

    def __init__(
        self,
        db_path: Path,
        table: str,
        *,
        ttl_seconds: float = DEFAULT_ARTIFACT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ARTIFACT_ENTRIES,
        clock: Callable[[], float] = time.time,
        artifact_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
            clock=clock,
            artifact_dir=artifact_dir,
        )
        self._db_path = db_path
        self._table = table
        with _connect(db_path) as conn:
            conn.executescript(_ARTIFACT_TABLE_SCHEMA.format(table=table))

    def _execute(
        self,
        conn: sqlite3.Connection,
        sql: str,
        parameters: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        return conn.execute(sql, parameters)

    def put(
        self,
        *,
        artifact_id: str,
        token: str,
        path: str | os.PathLike[str],
    ) -> TextArtifactHandle:
        self.cleanup_expired()
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        artifact_path = self._resolve_artifact_path(path)
        now = self._clock()
        expires_at = now + self._ttl_seconds

        with _connect(self._db_path) as conn:
            existing = self._execute(
                conn,
                f"SELECT path FROM {self._table} WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            if existing is not None and Path(existing[0]) != artifact_path:
                _delete_file(Path(existing[0]))
            self._execute(
                conn,
                f"INSERT OR REPLACE INTO {self._table} "
                "(id, token, path, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (artifact_id, token, str(artifact_path), now, expires_at),
            )

        self._evict_overflow_sqlite()
        return TextArtifactHandle(
            artifact_id=artifact_id,
            token=token,
            path=str(artifact_path),
            expires_at=expires_at,
        )

    async def get(self, artifact_id: str, token: str) -> str:
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        self.cleanup_expired()
        now = self._clock()
        with _connect(self._db_path) as conn:
            row = self._execute(
                conn,
                f"SELECT token, path, expires_at FROM {self._table} WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise ArtifactNotFoundError("Artifact was not found.")
        if not secrets.compare_digest(row[0], token):
            raise ArtifactAccessDeniedError("Artifact token does not match.")
        if row[2] <= now:
            # Best-effort expiry cleanup; ignore failure (the TTL
            # sweep on the next put() will catch it).
            with _connect(self._db_path) as conn:
                self._execute(
                    conn,
                    f"DELETE FROM {self._table} WHERE id = ?",
                    (artifact_id,),
                )
            _delete_file(Path(row[1]))
            raise ArtifactNotFoundError("Artifact has expired.")
        return cast(str, row[1])

    def pop(self, artifact_id: str, token: str) -> str | None:
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        self.cleanup_expired()
        with _connect(self._db_path) as conn:
            row = self._execute(
                conn,
                f"SELECT token, path FROM {self._table} WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        if not secrets.compare_digest(row[0], token):
            raise ArtifactAccessDeniedError("Artifact token does not match.")
        with _connect(self._db_path) as conn:
            self._execute(
                conn,
                f"DELETE FROM {self._table} WHERE id = ?",
                (artifact_id,),
            )
        return cast(str, row[1])

    async def delete(self, artifact_id: str, token: str) -> bool:
        path = self.pop(artifact_id, token)
        if path is None:
            return False
        _delete_file(Path(path))
        return True

    def cleanup_expired(self) -> list[str]:
        now = self._clock()
        with _connect(self._db_path) as conn:
            expired = self._execute(
                conn,
                f"SELECT id, path FROM {self._table} WHERE expires_at <= ?",
                (now,),
            ).fetchall()
            if expired:
                self._execute(
                    conn,
                    f"DELETE FROM {self._table} WHERE expires_at <= ?",
                    (now,),
                )
        removed_paths = [str(row[1]) for row in expired]
        for path in removed_paths:
            _delete_file(Path(path))
        return removed_paths

    def clear(self) -> list[str]:
        with _connect(self._db_path) as conn:
            rows = self._execute(conn, f"SELECT path FROM {self._table}").fetchall()
            self._execute(conn, f"DELETE FROM {self._table}")
        removed_paths = [str(row[0]) for row in rows]
        for path in removed_paths:
            _delete_file(Path(path))
        return removed_paths

    def __len__(self) -> int:
        self.cleanup_expired()
        with _connect(self._db_path) as conn:
            (count,) = self._execute(
                conn, f"SELECT COUNT(*) FROM {self._table}"
            ).fetchone()
        return int(count)

    def _evict_overflow_sqlite(self) -> None:
        """Enforce ``max_entries`` in SQL on every insert.

        Cheaper than the in-memory ``_evict_overflow`` because the
        "oldest" rows are already keyed by ``created_at`` (indexed
        in the schema).
        """
        while True:
            with _connect(self._db_path) as conn:
                (count,) = self._execute(
                    conn,
                    f"SELECT COUNT(*) FROM {self._table}",
                ).fetchone()
                if count <= self._max_entries:
                    return
                row = self._execute(
                    conn,
                    f"SELECT id, path FROM {self._table} "
                    "ORDER BY created_at ASC LIMIT 1",
                ).fetchone()
            if row is None:
                return
            with _connect(self._db_path) as conn:
                self._execute(
                    conn,
                    f"DELETE FROM {self._table} WHERE id = ?",
                    (row[0],),
                )
            _delete_file(Path(row[1]))


class SQLiteJobHistory(JobHistory):
    """Job history persisted in SQLite.

    Reads (``list()``) are a single indexed ``SELECT ... ORDER BY
    rowid DESC`` and the cap is enforced with a single
    indexed ``DELETE`` on every ``record()`` using SQLite's monotonic rowid.
    The default ``max_jobs`` matches :class:`JobHistory` (1000) so the
    persistent backend does not silently drop history that the
    in-memory backend would have kept.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        max_jobs: int = 1000,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(max_jobs=max_jobs, now=now)
        self._db_path = db_path
        with _connect(db_path) as conn:
            conn.executescript(_JOBS_TABLE_SCHEMA)

    def record(
        self,
        *,
        job_id: str,
        filename: str,
        model: str,
        pipeline_mode: str,
        pages: str | None,
        duration_s: float,
        status: JobStatus,
        failed_pages: Sequence[int] = (),
        text_artifact_id: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            id=_clean_required_text(job_id, "job_id"),
            filename=_clean_required_text(filename, "filename"),
            model=_clean_required_text(model, "model"),
            pipeline_mode=_clean_required_text(pipeline_mode, "pipeline_mode"),
            pages=_clean_optional_text(pages, "pages"),
            duration_s=_clean_duration(duration_s),
            timestamp=_current_timestamp(self._now),
            status=_clean_status(status),
            failed_pages=_clean_failed_pages(failed_pages),
            text_artifact_id=(
                _clean_optional_text(text_artifact_id, "text_artifact_id")
                if text_artifact_id is not None
                else None
            ),
        )
        payload = json.dumps(record.to_dict())
        inserted_at = time.time()
        with _connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO omniscribe_jobs "
                "(id, inserted_at, payload) VALUES (?, ?, ?)",
                (record.id, inserted_at, payload),
            )
            # Cap: keep only the newest ``max_jobs`` rows using SQLite's native rowid.
            conn.execute(
                "DELETE FROM omniscribe_jobs WHERE rowid IN ("
                "  SELECT rowid FROM omniscribe_jobs "
                "  ORDER BY rowid DESC "
                "  LIMIT -1 OFFSET ?"
                ")",
                (self.max_jobs,),
            )
        return record

    def list(self) -> list[dict[str, Any]]:
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT payload FROM omniscribe_jobs ORDER BY rowid DESC"
            ).fetchall()
        return [cast(dict[str, Any], json.loads(row[0])) for row in rows]

    def clear(self) -> None:
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM omniscribe_jobs")


class SQLiteStateBackend:
    """Persistent single-file :class:`StateBackend` (no Redis required).

    Default artifact directory: ``$OMNISCRIBE_ARTIFACT_DIR`` (with
    the ``omniscribe`` subdirectory suffix) or the OS temp dir.
    The :class:`TextArtifactStore` and :class:`JobHistory`
    implementations are SQLite-backed; the live-channel services
    (:class:`ProgressService`, :class:`OCRJobQueue`) stay in-memory by design,
    and :class:`LexiconStore` is LanceDB-backed — see the module docstring.
    """

    text_artifacts: SQLiteTextArtifactStore
    metadata_artifacts: SQLiteTextArtifactStore
    export_artifacts: SQLiteTextArtifactStore
    job_history: SQLiteJobHistory
    progress_service: ProgressService
    lexicon_store: LexiconStore
    ocr_job_queue: OCRJobQueue
    # Duck-typed config-store attribute (see
    # ``api/services/state/base.py`` module docstring). Not part of the
    # :class:`StateBackend` Protocol.
    config_store: SQLiteConfigStore

    def __init__(
        self,
        db_path: str | Path | None = None,
        artifact_dir: str | Path | None = None,
        lexicon_store: LexiconStore | None = None,
    ) -> None:
        import os

        if artifact_dir is not None:
            resolved = Path(artifact_dir).expanduser().resolve()
        else:
            resolved = Path(
                os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())
            ).resolve()
        self._artifact_dir = resolved

        if db_path is None:
            self.db_path = resolved / "omniscribe-state.db"
        else:
            self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.text_artifacts = SQLiteTextArtifactStore(
            self.db_path,
            "omniscribe_artifact_text",
            artifact_dir=resolved,
        )
        self.metadata_artifacts = SQLiteTextArtifactStore(
            self.db_path,
            "omniscribe_artifact_meta",
            artifact_dir=resolved,
        )
        self.export_artifacts = SQLiteTextArtifactStore(
            self.db_path,
            "omniscribe_artifact_export",
            artifact_dir=resolved,
        )
        self.job_history = SQLiteJobHistory(self.db_path)
        self.progress_service = ProgressService()
        self.lexicon_store = lexicon_store or LanceDBLexiconStore(
            path=resolved / "lexicon.lance",
            embedding_model=get_default_embedding_model(),
        )
        self.ocr_job_queue = OCRJobQueue()
        self.config_store = SQLiteConfigStore(self.db_path)

    @property
    def artifact_dir(self) -> Path:
        return self._artifact_dir


__all__ = ["SQLiteJobHistory", "SQLiteStateBackend", "SQLiteTextArtifactStore"]
