"""Pluggable per-server state holder.

The :class:`StateBackend` Protocol defines the surface that every router
and service consumes (artifacts, jobs, progress math, glossary library).
:class:`LocalStateBackend` is the in-memory implementation that has been
the de-facto state since v0; future work can plug in a Redis-backed or
file-backed implementation without rewriting every call site.

To swap in a new backend:

1. Implement a class that exposes the same seven attributes.
2. Have :mod:`local_deepl.api.routers.state` construct that class instead
   of :class:`LocalStateBackend`.

The module-level aliases ``state.text_artifacts`` etc. are kept so that
existing call sites continue to work; new code should prefer
``state.backend.text_artifacts``.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from local_deepl.api.services.artifacts import TextArtifactStore
from local_deepl.api.services.jobs import JobHistory
from local_deepl.api.services.ocr_jobs import OCRJobQueue
from local_deepl.api.services.progress import ProgressService
from local_deepl.core.glossary_library import GlossaryLibrary


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
            Path(os.getenv("LOCAL_DEEPL_ARTIFACT_DIR", tempfile.gettempdir()))
            / "local-deepl"
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
