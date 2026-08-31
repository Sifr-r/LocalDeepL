"""In-memory ``StateBackend`` implementation.

Audit catalog (Sprint 6 long-file split): separated from
``state_backend.py`` so the file at the ``state_backend`` import
path is just the Protocol + dataclasses + plugin + re-exports.
The two backends and the SQLite row helpers live in their own
modules so each can be reasoned about in isolation.

Public surface preserved: ``MemoryStateBackend`` is re-exported
from ``omniscribe.plugins.state_backend``.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import replace

from .state_backend import (
    ArtifactBlob,
    ArtifactRecord,
    ChannelRecord,
    JobRecord,
)

_MEMORY_BLOB_CAP_BYTES = 256 * 1024 * 1024


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

    async def list_jobs(self, *, limit: int = 100, offset: int = 0) -> list[JobRecord]:
        async with self._lock:
            ordered = sorted(
                self._jobs.values(), key=lambda r: r.created_at, reverse=True
            )
            return ordered[offset : offset + limit]

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


__all__ = ["MemoryStateBackend"]
