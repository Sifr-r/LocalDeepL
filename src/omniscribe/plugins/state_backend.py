"""StateBackend Protocol + in-memory and SQLite implementations.

Three persistence domains live behind one Protocol: artifacts (token-gated
blobs), jobs (async OCR job records), and progress channels (one-shot WS
handshake records). Selection is via the plugin row config
(``OMNISCRIBE_STATE_BACKEND=memory|sqlite``); redis is deferred.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sqlite3
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from omniscribe.config import load_settings
from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin

_LOGGER = logging.getLogger("omniscribe.plugins.state")

JobStatus = Literal["queued", "running", "complete", "error", "cancelled"]

_MEMORY_BLOB_CAP_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class ArtifactRecord:
    """Metadata for one stored artifact; blob bytes live elsewhere."""

    id: str
    token: str
    owner_job_id: str
    content_type: str
    created_at: float
    ttl_seconds: int


@dataclass(frozen=True)
class ArtifactBlob:
    """Artifact metadata plus its raw bytes."""

    record: ArtifactRecord
    blob: bytes


@dataclass(frozen=True)
class JobRecord:
    """One async OCR job's lifecycle state."""

    job_id: str
    status: JobStatus
    request_meta: dict[str, Any] = field(default_factory=dict)
    result_artifact_id: str | None = None
    result_artifact_token: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: str | None = None


@dataclass(frozen=True)
class ChannelRecord:
    """One progress channel handshake; ``consume_channel`` is one-shot."""

    channel_id: str
    session_token: str
    job_id: str
    created_at: float
    ttl_seconds: int
    consumed: bool = False


@runtime_checkable
class StateBackend(Protocol):
    """Persistence seam for artifacts, jobs, and progress channels."""

    # Artifacts
    async def put_artifact(
        self,
        *,
        id: str,
        token: str,
        owner_job_id: str,
        content_type: str,
        blob: bytes,
        ttl_seconds: int,
    ) -> None: ...

    async def get_artifact(self, id: str, token: str) -> ArtifactBlob | None: ...

    async def delete_artifact(self, id: str) -> None: ...

    async def prune_expired_artifacts(self, now: float) -> int: ...

    # Jobs
    async def upsert_job(self, record: JobRecord) -> None: ...

    async def get_job(self, job_id: str) -> JobRecord | None: ...

    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]: ...

    async def clear_jobs(self) -> int: ...

    async def delete_job(self, job_id: str) -> None: ...

    # Progress channels
    async def put_channel(
        self, channel_id: str, session_token: str, job_id: str, ttl_seconds: int
    ) -> None: ...

    async def get_channel(self, channel_id: str) -> ChannelRecord | None: ...

    async def consume_channel(
        self, channel_id: str, session_token: str
    ) -> ChannelRecord | None: ...

    async def delete_channel(self, channel_id: str) -> None: ...

    async def prune_expired_channels(self, now: float) -> int: ...

    async def aclose(self) -> None: ...


class MemoryStateBackend:
    """Default in-process backend; blobs capped per artifact for safety."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._blobs: dict[str, bytes] = {}
        self._jobs: dict[str, JobRecord] = {}
        self._channels: dict[str, ChannelRecord] = {}

    # -- artifacts ----------------------------------------------------------

    async def put_artifact(
        self,
        *,
        id: str,
        token: str,
        owner_job_id: str,
        content_type: str,
        blob: bytes,
        ttl_seconds: int,
    ) -> None:
        if len(blob) > _MEMORY_BLOB_CAP_BYTES:
            raise ValueError(
                f"artifact {id!r} exceeds the {_MEMORY_BLOB_CAP_BYTES}-byte "
                "in-memory blob cap"
            )
        async with self._lock:
            self._artifacts[id] = ArtifactRecord(
                id=id,
                token=token,
                owner_job_id=owner_job_id,
                content_type=content_type,
                created_at=time.time(),
                ttl_seconds=ttl_seconds,
            )
            self._blobs[id] = blob

    async def get_artifact(self, id: str, token: str) -> ArtifactBlob | None:
        async with self._lock:
            record = self._artifacts.get(id)
            if record is None or record.token != token:
                return None
            return ArtifactBlob(record=record, blob=self._blobs[id])

    async def delete_artifact(self, id: str) -> None:
        async with self._lock:
            self._artifacts.pop(id, None)
            self._blobs.pop(id, None)

    async def prune_expired_artifacts(self, now: float) -> int:
        async with self._lock:
            expired = [
                artifact_id
                for artifact_id, record in self._artifacts.items()
                if now >= record.created_at + record.ttl_seconds
            ]
            for artifact_id in expired:
                self._artifacts.pop(artifact_id, None)
                self._blobs.pop(artifact_id, None)
            return len(expired)

    # -- jobs -----------------------------------------------------------------

    async def upsert_job(self, record: JobRecord) -> None:
        async with self._lock:
            self._jobs[record.job_id] = record

    async def get_job(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]:
        async with self._lock:
            ordered = sorted(
                self._jobs.values(), key=lambda r: r.created_at, reverse=True
            )
            return ordered[:limit]

    async def clear_jobs(self) -> int:
        async with self._lock:
            count = len(self._jobs)
            self._jobs.clear()
            return count

    async def delete_job(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)

    # -- channels ---------------------------------------------------------------

    async def put_channel(
        self, channel_id: str, session_token: str, job_id: str, ttl_seconds: int
    ) -> None:
        async with self._lock:
            self._channels[channel_id] = ChannelRecord(
                channel_id=channel_id,
                session_token=session_token,
                job_id=job_id,
                created_at=time.time(),
                ttl_seconds=ttl_seconds,
            )

    async def get_channel(self, channel_id: str) -> ChannelRecord | None:
        async with self._lock:
            return self._channels.get(channel_id)

    async def consume_channel(
        self, channel_id: str, session_token: str
    ) -> ChannelRecord | None:
        async with self._lock:
            record = self._channels.get(channel_id)
            if (
                record is None
                or record.consumed
                or not secrets.compare_digest(record.session_token, session_token)
            ):
                return None
            self._channels[channel_id] = replace(record, consumed=True)
            return record

    async def delete_channel(self, channel_id: str) -> None:
        async with self._lock:
            self._channels.pop(channel_id, None)

    async def prune_expired_channels(self, now: float) -> int:
        async with self._lock:
            expired = [
                channel_id
                for channel_id, record in self._channels.items()
                if now >= record.created_at + record.ttl_seconds
            ]
            for channel_id in expired:
                self._channels.pop(channel_id, None)
            return len(expired)

    async def aclose(self) -> None:
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    owner_job_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    blob_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    ttl_seconds INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    request_meta TEXT NOT NULL,
    result_artifact_id TEXT,
    result_artifact_token TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS progress_channels (
    channel_id TEXT PRIMARY KEY,
    session_token TEXT NOT NULL,
    job_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    ttl_seconds INTEGER NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);
"""


class SQLiteStateBackend:
    """Single-file persistent backend (WAL mode).

    Blob bytes live on disk at ``<blob_dir>/<id>.bin``; the database holds
    paths and metadata only, keeping the file small.
    """

    def __init__(self, db_path: Path | str, blob_dir: Path | str) -> None:
        self._db_path = Path(db_path)
        self._blob_dir = Path(blob_dir)
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    async def open(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._open_sync)

    def _open_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._blob_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteStateBackend is not open")
        return self._conn

    def _blob_path(self, artifact_id: str) -> Path:
        return self._blob_dir / f"{artifact_id}.bin"

    # -- artifacts ----------------------------------------------------------

    async def put_artifact(
        self,
        *,
        id: str,
        token: str,
        owner_job_id: str,
        content_type: str,
        blob: bytes,
        ttl_seconds: int,
    ) -> None:
        async with self._lock:

            def _put() -> None:
                conn = self._require_conn()
                path = self._blob_path(id)
                path.write_bytes(blob)
                conn.execute(
                    "INSERT OR REPLACE INTO artifacts "
                    "(id, token, owner_job_id, content_type, blob_path, created_at, ttl_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        id,
                        token,
                        owner_job_id,
                        content_type,
                        str(path),
                        time.time(),
                        ttl_seconds,
                    ),
                )
                conn.commit()

            await asyncio.to_thread(_put)

    async def get_artifact(self, id: str, token: str) -> ArtifactBlob | None:
        async with self._lock:

            def _get() -> ArtifactBlob | None:
                conn = self._require_conn()
                row = conn.execute(
                    "SELECT id, token, owner_job_id, content_type, blob_path, "
                    "created_at, ttl_seconds FROM artifacts WHERE id = ?",
                    (id,),
                ).fetchone()
                if row is None or row[1] != token:
                    return None
                record = ArtifactRecord(
                    id=row[0],
                    token=row[1],
                    owner_job_id=row[2],
                    content_type=row[3],
                    created_at=row[5],
                    ttl_seconds=row[6],
                )
                path = Path(row[4])
                if not path.is_file():
                    return None
                return ArtifactBlob(record=record, blob=path.read_bytes())

            return await asyncio.to_thread(_get)

    async def delete_artifact(self, id: str) -> None:
        async with self._lock:

            def _delete() -> None:
                conn = self._require_conn()
                row = conn.execute(
                    "SELECT blob_path FROM artifacts WHERE id = ?", (id,)
                ).fetchone()
                conn.execute("DELETE FROM artifacts WHERE id = ?", (id,))
                conn.commit()
                if row is not None:
                    Path(row[0]).unlink(missing_ok=True)

            await asyncio.to_thread(_delete)

    async def prune_expired_artifacts(self, now: float) -> int:
        async with self._lock:

            def _prune() -> int:
                conn = self._require_conn()
                rows = conn.execute(
                    "SELECT id, blob_path FROM artifacts WHERE created_at + ttl_seconds <= ?",
                    (now,),
                ).fetchall()
                if not rows:
                    return 0
                conn.execute(
                    "DELETE FROM artifacts WHERE created_at + ttl_seconds <= ?", (now,)
                )
                conn.commit()
                for _artifact_id, blob_path in rows:
                    Path(blob_path).unlink(missing_ok=True)
                return len(rows)

            return await asyncio.to_thread(_prune)

    # -- jobs -----------------------------------------------------------------

    async def upsert_job(self, record: JobRecord) -> None:
        async with self._lock:

            def _upsert() -> None:
                conn = self._require_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO jobs "
                    "(job_id, status, request_meta, result_artifact_id, "
                    "result_artifact_token, created_at, updated_at, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.job_id,
                        record.status,
                        json.dumps(record.request_meta),
                        record.result_artifact_id,
                        record.result_artifact_token,
                        record.created_at,
                        record.updated_at,
                        record.error,
                    ),
                )
                conn.commit()

            await asyncio.to_thread(_upsert)

    async def get_job(self, job_id: str) -> JobRecord | None:
        async with self._lock:

            def _get() -> JobRecord | None:
                row = (
                    self._require_conn()
                    .execute(
                        "SELECT job_id, status, request_meta, result_artifact_id, "
                        "result_artifact_token, created_at, updated_at, error "
                        "FROM jobs WHERE job_id = ?",
                        (job_id,),
                    )
                    .fetchone()
                )
                return _job_from_row(row) if row is not None else None

            return await asyncio.to_thread(_get)

    async def list_jobs(self, *, limit: int = 100) -> list[JobRecord]:
        async with self._lock:

            def _list() -> list[JobRecord]:
                rows = (
                    self._require_conn()
                    .execute(
                        "SELECT job_id, status, request_meta, result_artifact_id, "
                        "result_artifact_token, created_at, updated_at, error "
                        "FROM jobs ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    )
                    .fetchall()
                )
                return [_job_from_row(row) for row in rows]

            return await asyncio.to_thread(_list)

    async def clear_jobs(self) -> int:
        async with self._lock:

            def _clear() -> int:
                conn = self._require_conn()
                cursor = conn.execute("DELETE FROM jobs")
                conn.commit()
                return cursor.rowcount if cursor.rowcount >= 0 else 0

            return await asyncio.to_thread(_clear)

    async def delete_job(self, job_id: str) -> None:
        async with self._lock:

            def _delete() -> None:
                conn = self._require_conn()
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
                conn.commit()

            await asyncio.to_thread(_delete)

    # -- channels ---------------------------------------------------------------

    async def put_channel(
        self, channel_id: str, session_token: str, job_id: str, ttl_seconds: int
    ) -> None:
        async with self._lock:

            def _put() -> None:
                conn = self._require_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO progress_channels "
                    "(channel_id, session_token, job_id, created_at, ttl_seconds, consumed) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (channel_id, session_token, job_id, time.time(), ttl_seconds),
                )
                conn.commit()

            await asyncio.to_thread(_put)

    async def get_channel(self, channel_id: str) -> ChannelRecord | None:
        async with self._lock:

            def _get() -> ChannelRecord | None:
                row = (
                    self._require_conn()
                    .execute(
                        "SELECT channel_id, session_token, job_id, created_at, "
                        "ttl_seconds, consumed FROM progress_channels WHERE channel_id = ?",
                        (channel_id,),
                    )
                    .fetchone()
                )
                return _channel_from_row(row) if row is not None else None

            return await asyncio.to_thread(_get)

    async def consume_channel(
        self, channel_id: str, session_token: str
    ) -> ChannelRecord | None:
        async with self._lock:

            def _consume() -> ChannelRecord | None:
                conn = self._require_conn()
                row = conn.execute(
                    "SELECT channel_id, session_token, job_id, created_at, "
                    "ttl_seconds, consumed FROM progress_channels "
                    "WHERE channel_id = ?",
                    (channel_id,),
                ).fetchone()
                if (
                    row is None
                    or row[5]
                    or not secrets.compare_digest(row[1], session_token)
                ):
                    return None
                conn.execute(
                    "UPDATE progress_channels SET consumed = 1 WHERE channel_id = ?",
                    (channel_id,),
                )
                conn.commit()
                return _channel_from_row(row)

            return await asyncio.to_thread(_consume)

    async def delete_channel(self, channel_id: str) -> None:
        async with self._lock:

            def _delete() -> None:
                conn = self._require_conn()
                conn.execute(
                    "DELETE FROM progress_channels WHERE channel_id = ?", (channel_id,)
                )
                conn.commit()

            await asyncio.to_thread(_delete)

    async def prune_expired_channels(self, now: float) -> int:
        async with self._lock:

            def _prune() -> int:
                conn = self._require_conn()
                cursor = conn.execute(
                    "DELETE FROM progress_channels WHERE created_at + ttl_seconds <= ?",
                    (now,),
                )
                conn.commit()
                return cursor.rowcount if cursor.rowcount >= 0 else 0

            return await asyncio.to_thread(_prune)

    async def aclose(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await asyncio.to_thread(conn.close)


def _job_from_row(row: Any) -> JobRecord:
    return JobRecord(
        job_id=row[0],
        status=row[1],
        request_meta=json.loads(row[2]) if row[2] else {},
        result_artifact_id=row[3],
        result_artifact_token=row[4],
        created_at=row[5],
        updated_at=row[6],
        error=row[7],
    )


def _channel_from_row(row: Any) -> ChannelRecord:
    return ChannelRecord(
        channel_id=row[0],
        session_token=row[1],
        job_id=row[2],
        created_at=row[3],
        ttl_seconds=row[4],
        consumed=bool(row[5]),
    )


_ALLOWED_BACKENDS = {"memory", "sqlite"}


class StateBackendSchema(BaseModel):
    backend: Literal["memory", "sqlite"] = "memory"
    sqlite_path: str = ""


class StateBackendPlugin(Plugin):
    """Builds the configured backend and registers it under ``StateBackend``."""

    Schema = StateBackendSchema

    async def apply(self, ctx: Context) -> None:
        backend_name = str(self.config.get("backend", "memory")).strip().lower()
        if backend_name not in _ALLOWED_BACKENDS:
            raise ValueError(
                "state backend must be one of "
                f"{sorted(_ALLOWED_BACKENDS)} in this build, got {backend_name!r} "
                "(redis support ships in a follow-up)"
            )
        settings = load_settings()
        if backend_name == "memory":
            backend: StateBackend = MemoryStateBackend()
        else:
            sqlite_path = str(self.config.get("sqlite_path") or "").strip()
            db_path = (
                Path(sqlite_path)
                if sqlite_path
                else settings.artifact_base_dir / "omniscribe-state.db"
            )
            sqlite_backend = SQLiteStateBackend(
                db_path=db_path, blob_dir=settings.artifact_base_dir
            )
            await sqlite_backend.open()
            backend = sqlite_backend
            _LOGGER.info("state backend sqlite db=%s", db_path)
        ctx.service(StateBackend, backend)
        ctx.effect(backend.aclose)


plugin = StateBackendPlugin()
