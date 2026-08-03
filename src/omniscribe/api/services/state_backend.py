"""Pluggable per-server state holder.

The :class:`StateBackend` Protocol defines the surface that every router
and service consumes (artifacts, jobs, progress math, glossary library).
:class:`LocalStateBackend` is the in-memory implementation that has been
the de-facto state since v0; future work can plug in a Redis-backed or
file-backed implementation without rewriting every call site.

To swap in a new backend:

1. Implement a class that exposes the same seven attributes.
2. Have :mod:`omniscribe.api.routers.state` construct that class instead
   of :class:`LocalStateBackend`.

The module-level aliases ``state.text_artifacts`` etc. are kept so that
existing call sites continue to work; new code should prefer
``state.backend.text_artifacts``.

Process-lifetime boundary
-------------------------

A :class:`LocalStateBackend` instance owns the canonical references for
its seven attributes:

- ``text_artifacts`` (:class:`TextArtifactStore`)
- ``metadata_artifacts`` (:class:`TextArtifactStore`)
- ``export_artifacts`` (:class:`TextArtifactStore`)
- ``job_history`` (:class:`JobHistory`)
- ``progress_service`` (:class:`ProgressService`)
- ``glossary_library`` (:class:`GlossaryLibrary`)
- ``ocr_job_queue`` (:class:`OCRJobQueue`)

All seven live in the Python process that runs :func:`LocalStateBackend.from_env`
(via :mod:`omniscribe.api.routers.state`). ``from_env`` constructs every
attribute fresh on import: no disk snapshot is read, no external service
is contacted. Terminating the uvicorn worker (or the parent
``start_app.vbs`` wrapper) discards the instance and therefore every
in-memory job history record, in-flight progress channel, queued OCR
job, and glossary index not yet flushed to its artifact directory. The
"recovery boundary" lives one level up from this module: the only state
that survives a restart is whatever its child components explicitly
wrote to disk (artifact files, glossary on-disk index).

See the *Known Tech Debt* section of ``AGENTS.md`` for the project-level
acknowledgement: "Job/artifact state is in-memory only (``api/routers/state.py``
singletons) — restarts lose history; no horizontal scaling."
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.api.services.jobs import JobHistory
from omniscribe.api.services.ocr_jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService
from omniscribe.core.glossary_library import GlossaryLibrary


@runtime_checkable
class StateBackend(Protocol):
    """Pluggable per-server state holder (artifacts, jobs, progress, glossary).

    ``runtime_checkable`` so tests can assert duck-typing of alternative
    implementations (Redis, file-backed, etc.) without subclassing.
    """

    text_artifacts: TextArtifactStore
    metadata_artifacts: TextArtifactStore
    export_artifacts: TextArtifactStore
    job_history: JobHistory
    progress_service: ProgressService
    glossary_library: GlossaryLibrary
    ocr_job_queue: OCRJobQueue


@dataclass(slots=True)
class LocalStateBackend:
    """In-memory StateBackend. All state is lost on restart.

    ``slots=True`` keeps the instances lightweight but we deliberately
    avoid ``frozen=True`` — the :class:`StateBackend` Protocol declares
    its seven attributes as plain (settable) instance variables, and mypy
    rejects assigning a frozen dataclass where a Protocol variable is
    expected. The instance is still effectively immutable from the
    router layer because callers go through ``state.backend.X``.
    """

    text_artifacts: TextArtifactStore
    metadata_artifacts: TextArtifactStore
    export_artifacts: TextArtifactStore
    job_history: JobHistory
    progress_service: ProgressService
    glossary_library: GlossaryLibrary
    ocr_job_queue: OCRJobQueue

    @classmethod
    def from_env(cls) -> LocalStateBackend:
        artifact_dir = (
            Path(os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir()))
            / "omniscribe"
        )
        # REVIEW: `artifact_dir` is applied to the glossary only; the three
        # artifact stores fall back to the system temp directory. Keep all
        # persisted artifact surfaces on one configured retention boundary.
        return cls(
            text_artifacts=TextArtifactStore(),
            metadata_artifacts=TextArtifactStore(),
            export_artifacts=TextArtifactStore(),
            job_history=JobHistory(),
            progress_service=ProgressService(),
            glossary_library=GlossaryLibrary(artifact_dir=artifact_dir),
            ocr_job_queue=OCRJobQueue(),
        )


__all__ = ["LocalStateBackend", "StateBackend"]
