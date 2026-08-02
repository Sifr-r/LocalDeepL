"""Singleton application state shared across routers.

The single source of truth is :class:`LocalStateBackend` (imported
from :mod:`local_deepl.api.services.state_backend`). The module-level
aliases (``state.text_artifacts`` etc.) are kept so existing call sites
continue to work; new code should prefer ``state.backend.text_artifacts``
so an alternative backend (Redis, file-backed) can be swapped in
without rewriting every consumer.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from local_deepl.api.services.artifacts import TextArtifactStore  # noqa: F401
from local_deepl.api.services.jobs import JobHistory  # noqa: F401
from local_deepl.api.services.progress import ProgressService  # noqa: F401
from local_deepl.api.services.state_backend import LocalStateBackend
from local_deepl.core.glossary_library import GlossaryLibrary

_artifact_dir = (
    Path(os.getenv("LOCAL_DEEPL_ARTIFACT_DIR", tempfile.gettempdir())) / "local-deepl"
)

# Backend instance is the single source of truth; the legacy aliases
# below resolve through it so a runtime swap keeps both access paths
# in sync.
backend = LocalStateBackend.from_env()

text_artifacts = backend.text_artifacts
metadata_artifacts = backend.metadata_artifacts
export_artifacts = backend.export_artifacts
job_history = backend.job_history
progress_service = backend.progress_service
ocr_job_queue = backend.ocr_job_queue
# GlossaryLibrary carries a non-default artifact_dir; keep the original
# instance so the on-disk glossary index is preserved across swaps.
glossary_library = GlossaryLibrary(artifact_dir=_artifact_dir)
