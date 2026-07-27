"""Singleton application state shared across routers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from local_deepl.api.services.artifacts import TextArtifactStore
from local_deepl.api.services.jobs import JobHistory
from local_deepl.api.services.progress import ProgressService
from local_deepl.core.glossary_library import GlossaryLibrary

_artifact_dir = Path(
    os.getenv("LOCAL_DEEPL_ARTIFACT_DIR", tempfile.gettempdir())
) / "local-deepl"

text_artifacts = TextArtifactStore()
metadata_artifacts = TextArtifactStore()
export_artifacts = TextArtifactStore()
job_history = JobHistory()
progress_service = ProgressService()
glossary_library = GlossaryLibrary(artifact_dir=_artifact_dir)
