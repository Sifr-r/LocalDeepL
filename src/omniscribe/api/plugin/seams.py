"""Capability seam definitions for the plugin context.

A **seam** is a swappable capability that follows the Cordis three-role
pattern:

- **Service Definition** — a :class:`~omniscribe.api.plugin.ServiceDefinition`
  that declares the interface.
- **Service Provider** — a concrete implementation registered into a
  :class:`~omniscribe.api.plugin.PluginContext`.
- **Consumer** — code that looks up the service by its definition class
  instead of importing a concrete implementation.

This package holds the Service Definitions. Concrete providers live in
:mod:`omniscribe.api.plugin.providers`; consumers live in the routers and
services that previously imported the legacy singletons by name.

Phase 1 introduces the OCR job queue seam; Phase 3 introduces the
session log seam; subsequent phases add the remaining capability seams
(auth, document export, glossary import, provider manager, telemetry,
etc.).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from omniscribe.api.plugin.session_log import SessionLog as _SessionLog
from omniscribe.api.services.config_store import ConfigStore as _ConfigStore
from omniscribe.api.services.ocr.jobs import (
    OCRJobRecord,
    OCRJobRunner,
)
from omniscribe.api.services.progress import ProgressChannel as _ProgressChannel

# Re-export so consumers can `from omniscribe.api.plugin.seams import SessionLog`.
SessionLog = _SessionLog

# Re-export the existing ``ConfigStore`` Protocol so consumers can
# import the seam from the same module as the other capabilities.
# The Protocol lives in :mod:`omniscribe.api.services.config_store`
# because that module also defines the concrete implementations;
# re-exporting keeps the public surface in one place.
ConfigStore = _ConfigStore

# Re-export the progress-channel dataclass so consumers don't need
# to know which module the seam version lives in.
ProgressChannel = _ProgressChannel


@runtime_checkable
class JobQueue(Protocol):
    """Service definition for a background OCR job queue.

    The :class:`~omniscribe.api.services.ocr.jobs.OCRJobQueue` is the
    canonical in-process implementation; a future :class:`CeleryJobQueue`
    provider will satisfy the same Protocol so consumers can swap
    implementations via the plugin context without code changes.

    The shape mirrors the public surface every current consumer uses;
    adding a new method here requires updating every provider AND every
    consumer (the Protocol is the contract).
    """

    @property
    def running(self) -> bool:
        """True if the background worker is active."""
        ...

    async def start(self) -> None:
        """Spawn the background worker (idempotent)."""
        ...

    async def stop(self) -> None:
        """Cancel the worker and any in-flight jobs. Idempotent."""
        ...

    async def submit(
        self,
        job_id: str,
        filename: str,
        runner: OCRJobRunner,
    ) -> str:
        """Register a job and enqueue it. Returns the job_id."""
        ...

    async def get(self, job_id: str) -> OCRJobRecord | None:
        """Look up a job by id. Returns None if unknown."""
        ...

    async def list(self) -> list[OCRJobRecord]:
        """Return a snapshot of all known job records."""
        ...

    async def cancel(self, job_id: str) -> OCRJobRecord | None:
        """Mark a job as cancelled. Returns the updated record or None if unknown."""
        ...

    def cleanup_expired(self) -> int:
        """Evict terminal-state records older than the retention window.

        Returns the number of records evicted. Synchronous to match the
        contract other stores expose to the artifact sweeper.
        """
        ...


@runtime_checkable
class ProgressService(Protocol):
    """Service definition for the in-process progress / WebSocket framing service.

    The :class:`~omniscribe.api.services.progress.ProgressService` is
    the canonical implementation; it owns the stage-to-percent math,
    the channel-id / session-token minting, and every WebSocket frame
    builder used by the OCR + translation routes. Phase 5 introduces
    the Protocol so consumers can look up the service by
    :class:`ProgressService` instead of importing the singleton via
    ``state.progress_service``.

    The Protocol deliberately mirrors only the surface that current
    consumers call (the rest of ``ProgressService`` is a mix of
    internal validators and ``@staticmethod`` frame builders used by
    the WebSocket router, which is migrated in a follow-up phase).
    """

    def stage_to_percent(self, stage: str, current: int, total: int) -> int:
        """Map a pipeline stage + sub-progress into a 0-100 overall percent."""
        ...

    def create_channel(self, display_client_id: str | None = None) -> _ProgressChannel:
        """Mint a new ``(channel_id, session_token)`` pair."""
        ...

    def validate_channel_id(self, channel_id: str) -> str:
        """Validate and return a channel id (raises on malformed)."""
        ...

    def validate_session_token(self, session_token: str) -> str:
        """Validate and return a session token (raises on malformed)."""
        ...

    def is_bound(
        self,
        *,
        channel_id: str,
        session_token: str,
        expected_channel_id: str,
        expected_session_token: str,
    ) -> bool:
        """Constant-time compare inbound tokens against expected tokens."""
        ...


@runtime_checkable
class TextArtifactStore(Protocol):
    """Service definition for a token-bound temporary JSON text-artifact store.

    The :class:`~omniscribe.api.services.artifacts.TextArtifactStore`
    is the canonical in-process implementation; a future
    SQLite- or Redis-backed store would satisfy the same Protocol.
    Three concrete stores live on the legacy ``state`` object
    (``text_artifacts`` / ``metadata_artifacts`` /
    ``export_artifacts``) and the Phase 5 wiring registers each
    under a distinct name so a consumer can request, for example,
    the metadata store explicitly.

    The Protocol surface is the minimum consumers need: ``get`` /
    ``pop`` / ``delete`` for access, ``__len__`` for size checks,
    ``cleanup_expired`` for the artifact sweeper.
    """

    @property
    def artifact_dir(self) -> Any:
        """The on-disk directory where the store writes its backing files."""
        ...

    async def get(self, artifact_id: str, token: str) -> str:
        """Resolve an artifact to its backing-file path."""
        ...

    def pop(self, artifact_id: str, token: str) -> str | None:
        """Remove a token-bound entry without deleting its backing file."""
        ...

    async def delete(self, artifact_id: str, token: str) -> bool:
        """Remove a token-bound entry and delete its backing file."""
        ...

    def cleanup_expired(self) -> list[str]:
        """Evict expired entries. Returns the list of removed paths."""
        ...

    def clear(self) -> list[str]:
        """Remove every entry. Returns the list of removed paths."""
        ...

    def __len__(self) -> int:
        """Number of non-expired entries in the store."""
        ...


__all__ = [
    "ConfigStore",
    "JobQueue",
    "ProgressChannel",
    "ProgressService",
    "SessionLog",
    "TextArtifactStore",
]
