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

from typing import Protocol, runtime_checkable

from omniscribe.api.plugin.session_log import SessionLog as _SessionLog
from omniscribe.api.services.ocr_jobs import (
    OCRJobRecord,
    OCRJobRunner,
)

# Re-export so consumers can `from omniscribe.api.plugin.seams import SessionLog`.
SessionLog = _SessionLog


@runtime_checkable
class JobQueue(Protocol):
    """Service definition for a background OCR job queue.

    The :class:`~omniscribe.api.services.ocr_jobs.OCRJobQueue` is the
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


__all__ = ["JobQueue", "SessionLog"]
