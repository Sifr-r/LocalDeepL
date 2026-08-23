"""Singleton application state shared across routers.

Process-lifetime boundary
-------------------------

Every name bound in this module (``backend``, ``text_artifacts``,
``metadata_artifacts``, ``export_artifacts``, ``job_history``,
``progress_service``, ``ocr_job_queue``, ``lexicon_store``) lives in
the Python process that imports this module. There is no persistence
between restarts and no cross-process replication: any operator action
that terminates the uvicorn worker (or the parent ``start_app.vbs``
wrapper) loses job history, in-flight progress channels, and queued OCR
jobs unless they have already been flushed to their respective artifact
directories. This is the "recovery boundary" — recovery only ever
resumes from the last artifact that was explicitly written to disk,
never from in-memory state.

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
from typing import TYPE_CHECKING

from omniscribe.api.services.artifacts import TextArtifactStore  # noqa: F401
from omniscribe.api.services.config_store import ConfigStore
from omniscribe.api.services.jobs import JobHistory  # noqa: F401
from omniscribe.api.services.ocr_jobs import OCRJobQueue  # noqa: F401
from omniscribe.api.services.progress import ProgressService  # noqa: F401
from omniscribe.api.services.state_backend import (  # noqa: F401
    LocalStateBackend,
    build_state_backend,
)
from omniscribe.config import load_settings
from omniscribe.core.lexicon import LexiconStore

if TYPE_CHECKING:
    pass

_artifact_dir = (
    Path(os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())) / "omniscribe"
)

# Backend instance is the single source of truth; the module-level aliases
# below resolve through it so a runtime swap keeps both access paths
# in sync. The factory honours ``OMNISCRIBE_STATE_BACKEND`` — default
# ``"memory"`` keeps the historical :class:`LocalStateBackend`, while
# ``"sqlite"`` and ``"redis"`` route to the persistent backends. The
# factory is fail-fast on unknown values, so an operator typo crashes
# at import time rather than silently running with the wrong backend.
backend = build_state_backend(load_settings())

text_artifacts = backend.text_artifacts
metadata_artifacts = backend.metadata_artifacts
export_artifacts = backend.export_artifacts
job_history = backend.job_history
progress_service = backend.progress_service
ocr_job_queue = backend.ocr_job_queue
# Duck-typed config_store on every StateBackend implementation; expose
# the same instance here so call sites that already use ``state.X``
# can do ``state.config_store`` without reaching through ``backend``.
config_store: ConfigStore = backend.config_store  # type: ignore[attr-defined]
lexicon_store: LexiconStore = backend.lexicon_store

__all__ = [
    "backend",
    "config_store",
    "export_artifacts",
    "job_history",
    "lexicon_store",
    "metadata_artifacts",
    "ocr_job_queue",
    "progress_service",
    "text_artifacts",
]
