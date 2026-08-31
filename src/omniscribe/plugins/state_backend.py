"""StateBackend Protocol + plugin (frontend).

Three persistence domains live behind one Protocol: artifacts (token-gated
blobs), jobs (async OCR job records), and progress channels (one-shot WS
handshake records). Selection is via the plugin row config
(``OMNISCRIBE_STATE_BACKEND=memory|sqlite``); redis is deferred.

Audit catalog (Sprint 6 long-file split): the two implementations
now live in sibling modules:

- ``state_backend_memory.py`` — :class:`MemoryStateBackend`
- ``state_backend_sqlite.py`` — :class:`SQLiteStateBackend`

This file holds the Protocol, dataclasses, plugin, and the re-exports
that preserve the public surface (``from
omniscribe.plugins.state_backend import MemoryStateBackend``,
``SQLiteStateBackend``).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from omniscribe.config import load_settings
from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin

_LOGGER = logging.getLogger("omniscribe.plugins.state")

JobStatus = Literal["queued", "running", "complete", "error", "cancelled"]


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

    async def list_jobs(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[JobRecord]: ...

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
            # C-3 audit fix: validate sqlite_path so a misconfigured
            # operator (or a malicious patch file) cannot point the
            # database at an arbitrary filesystem location. The
            # default path under ``settings.artifact_base_dir`` is
            # always allowed; an operator-supplied override must be
            # an absolute path whose parent directory is the same as
            # ``artifact_base_dir`` (no path-traversal escape). A bare
            # file at the artifact base is also accepted; a file
            # *outside* is rejected.
            db_path: Path
            if sqlite_path:
                candidate = Path(sqlite_path).expanduser().resolve(strict=False)
                base = settings.artifact_base_dir.expanduser().resolve(strict=False)
                try:
                    candidate.relative_to(base)
                except ValueError as exc:
                    raise RuntimeError(
                        f"OMNISCRIBE_STATE_BACKEND sqlite_path={sqlite_path!r} "
                        f"resolves outside the artifact base {base}. "
                        "Pin the file under the artifact directory or "
                        "set sqlite_path to a path inside it."
                    ) from exc
                db_path = candidate
            else:
                db_path = settings.artifact_base_dir / "omniscribe-state.db"
            sqlite_backend = SQLiteStateBackend(
                db_path=db_path, blob_dir=settings.artifact_base_dir
            )
            await sqlite_backend.open()
            backend = sqlite_backend
            _LOGGER.info("state backend sqlite db=%s", db_path)
        ctx.service(StateBackend, backend)
        ctx.effect(backend.aclose)


plugin = StateBackendPlugin()


# Re-export the implementations for the existing public surface.
# Done after the dataclasses + plugin class are defined so the
# sibling modules can import their dependencies (ArtifactBlob,
# ChannelRecord, JobRecord) from this module's already-populated
# namespace without a circular-import ImportError.
from .state_backend_memory import MemoryStateBackend  # noqa: E402
from .state_backend_sqlite import SQLiteStateBackend  # noqa: E402

__all__ = [
    "ArtifactBlob",
    "ArtifactRecord",
    "ChannelRecord",
    "JobRecord",
    "JobStatus",
    "MemoryStateBackend",
    "SQLiteStateBackend",
    "StateBackend",
    "StateBackendPlugin",
    "StateBackendSchema",
]
