"""Singleton application state shared across routers.

Process-lifetime boundary
-------------------------

Every name bound in this module (``backend``, ``text_artifacts``,
``metadata_artifacts``, ``export_artifacts``, ``job_history``,
``progress_service``, ``ocr_job_queue``, ``glossary_library``) lives in
the Python process that imports this module. There is no persistence
between restarts and no cross-process replication: any operator action
that terminates the uvicorn worker (or the parent ``start_app.vbs``
wrapper) loses job history, in-flight progress channels, queued OCR
jobs, and the on-disk glossary index unless they have already been
flushed to their respective artifact directories. This is the
"recovery boundary" — recovery only ever resumes from the last
artifact that was explicitly written to disk, never from in-memory
state.

The single source of truth is :class:`LocalStateBackend` (imported
from :mod:`omniscribe.api.services.state_backend`). The module-level
aliases (``state.text_artifacts`` etc.) are kept so existing call sites
continue to work; new code should prefer ``state.backend.text_artifacts``
so an alternative backend (Redis, file-backed) can be swapped in
without rewriting every consumer.

See the *Known Tech Debt* section of ``AGENTS.md`` for the
project-level acknowledgement: "Job/artifact state is in-memory only
(``api/routers/state.py`` singletons) — restarts lose history; no
horizontal scaling."
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from omniscribe.api.services.artifacts import TextArtifactStore  # noqa: F401
from omniscribe.api.services.jobs import JobHistory  # noqa: F401
from omniscribe.api.services.progress import ProgressService  # noqa: F401
from omniscribe.api.services.state_backend import (  # noqa: F401
    LocalStateBackend,
    build_state_backend,
)
from omniscribe.core.glossary_library import GlossaryLibrary

_artifact_dir = (
    Path(os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())) / "omniscribe"
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
