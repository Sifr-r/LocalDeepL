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

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from omniscribe.api.services.artifacts import TextArtifactStore  # noqa: F401
from omniscribe.api.services.config_store import ConfigStore
from omniscribe.api.services.jobs import JobHistory  # noqa: F401
from omniscribe.api.services.progress import ProgressService  # noqa: F401
from omniscribe.api.services.state_backend import (  # noqa: F401
    LocalStateBackend,
    build_state_backend,
)
from omniscribe.config import load_settings

if TYPE_CHECKING:
    # Type-only imports; never executed at runtime, so a missing
    # [lexicon] install doesn't break the server import chain.
    from omniscribe.core.lexicon import (
        GlossaryLibraryAdapter,
        LanceDBLexiconStore,
    )

_artifact_dir = (
    Path(os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())) / "omniscribe"
)

# Backend instance is the single source of truth; the legacy aliases
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
# ----------------------------------------------------------------------------
# Glossary store (Phase 5 of the LanceDB migration — cleanup)
# ----------------------------------------------------------------------------
# The canonical glossary store is the LanceDB-backed LexiconStore. The
# legacy ``GlossaryLibrary`` (JSON-on-disk) is wrapped by a
# :class:`GlossaryLibraryAdapter` so the existing API surface used by the
# ``glossary_imports`` router and the ``process_glossary_import_task`` Celery
# task keeps working — the swap is transparent to those call sites.
#
# The ``[lexicon]`` extra (lancedb + pyarrow + sentence-transformers) is
# OPTIONAL: a missing install logs a warning and falls back to a stub
# library that raises a clear "install [lexicon]" error at use time.
# This keeps the server bootable for users who don't use the glossary
# feature. The translation graph's ``retrieve_lexicon_context`` node
# independently degrades gracefully (empty ``rag_context``) when the
# store is missing.
_LOG = logging.getLogger(__name__)

_LEXICON_IMPORT_ERROR: str | None = None
_LEXICON_AVAILABLE: bool = False
_GlossaryLibraryAdapter: type | None = None
_LanceDBLexiconStore: type | None = None
# Embedding factory captured as Any because the imported function's
# signature is duck-typed (EmbeddingModel Protocol) and mypy would
# otherwise reject calling an `object`-typed name.
_embedding_factory: Any = None
try:
    from omniscribe.core.lexicon import (
        GlossaryLibraryAdapter as _GlossaryLibraryAdapter,
        LanceDBLexiconStore as _LanceDBLexiconStore,
    )
    from omniscribe.core.lexicon.embedding import (
        get_default_embedding_model as _embedding_factory,
    )
    _LEXICON_AVAILABLE = True
except ImportError as exc:
    _LEXICON_IMPORT_ERROR = str(exc)
    _LOG.warning(
        "lexicon extra not installed (%s); glossary library and translation RAG "
        "are unavailable. Install with: uv sync --extra lexicon",
        exc,
    )


class _UnavailableGlossaryLibrary:
    """Stub for ``state.glossary_library`` when the [lexicon] extra is missing.

    The server boots successfully but every glossary operation raises a
    clear ``RuntimeError`` with the install hint, instead of a generic
    ``AttributeError`` from ``None.save(...)`` or similar.
    """

    _HINT = (
        "The [lexicon] extra is not installed. Install with: "
        "uv sync --extra lexicon"
    )

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(
            f"glossary_library.{name}: {_UnavailableGlossaryLibrary._HINT}"
        )

    def __repr__(self) -> str:
        return f"<UnavailableGlossaryLibrary: {_UnavailableGlossaryLibrary._HINT}>"


def _build_lexicon_store() -> object | None:
    if not _LEXICON_AVAILABLE:
        return None
    assert _LanceDBLexiconStore is not None
    assert _embedding_factory is not None
    store: object = _LanceDBLexiconStore(
        path=_artifact_dir / "lexicon.lance",
        embedding_model=_embedding_factory(),
    )
    return store


def _build_glossary_library() -> object:
    if not _LEXICON_AVAILABLE:
        return _UnavailableGlossaryLibrary()
    store = _build_lexicon_store()
    assert store is not None
    assert _GlossaryLibraryAdapter is not None
    return _GlossaryLibraryAdapter(store)


# Module-level aliases. The server only ever reads these, so lazy attribute
# access via __getattr__ keeps the heavy construction off the import path
# while keeping the call-site syntax (``state.glossary_library``) unchanged.
glossary_library: object = _build_glossary_library()
lexicon_store: object | None = _build_lexicon_store()
