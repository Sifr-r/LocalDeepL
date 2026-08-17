"""Pluggable per-server state holder.

The :class:`StateBackend` Protocol defines the surface that every router
and service consumes (artifacts, jobs, progress math, glossary library).
:class:`LocalStateBackend` is the in-memory implementation that has been
the de-facto state since v0; future work can plug in a Redis-backed or
file-backed implementation without rewriting every call site.

Config persistence
------------------

Each backend also owns a ``config_store`` attribute (duck-typed, not
listed on the Protocol) so the :mod:`~omniscribe.api.routers.config`
POST handler can persist runtime-config updates in a way that all
uvicorn workers see. The :class:`LocalStateBackend` uses the
in-memory variant (per-process); :class:`RedisStateBackend` and
:class:`SQLiteStateBackend` use the cross-worker-visible variants. The
Protocol's seven-attribute surface is preserved — ``config_store`` is
an extra, not a replacement.

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
from pathlib import Path
from typing import Protocol, runtime_checkable

from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.api.services.config_store import InMemoryConfigStore
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


class LocalStateBackend:
    """In-memory StateBackend. All state is lost on restart.

    The class is intentionally not a ``@dataclass`` — the seven
    attributes are typed non-Optional so the :class:`StateBackend`
    Protocol surface is preserved for callers. The ``artifact_dir``
    parameter is the *primitive* constructor input: pass any directory
    and the seven internal stores are auto-wired against it. To inject a
    pre-built store (e.g. a Redis-backed :class:`TextArtifactStore` for
    tests), pass that store positionally to the corresponding field and
    ``artifact_dir`` is ignored for that slot. ``from_env`` is the
    canonical entry point for runtime startup.
    """

    text_artifacts: TextArtifactStore
    metadata_artifacts: TextArtifactStore
    export_artifacts: TextArtifactStore
    job_history: JobHistory
    progress_service: ProgressService
    glossary_library: GlossaryLibrary
    ocr_job_queue: OCRJobQueue
    # Duck-typed config-store attribute (see module docstring).
    # Not part of the :class:`StateBackend` Protocol.
    config_store: InMemoryConfigStore

    def __init__(
        self,
        artifact_dir: Path | str | os.PathLike[str] | None = None,
        *,
        text_artifacts: TextArtifactStore | None = None,
        metadata_artifacts: TextArtifactStore | None = None,
        export_artifacts: TextArtifactStore | None = None,
        job_history: JobHistory | None = None,
        progress_service: ProgressService | None = None,
        glossary_library: GlossaryLibrary | None = None,
        ocr_job_queue: OCRJobQueue | None = None,
        config_store: InMemoryConfigStore | None = None,
    ) -> None:
        if artifact_dir is not None:
            resolved = Path(artifact_dir).expanduser().resolve()
        else:
            resolved = Path(
                os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())
            ).resolve()
        self.text_artifacts = text_artifacts or TextArtifactStore(
            artifact_dir=resolved, kind="text"
        )
        self.metadata_artifacts = metadata_artifacts or TextArtifactStore(
            artifact_dir=resolved, kind="metadata"
        )
        self.export_artifacts = export_artifacts or TextArtifactStore(
            artifact_dir=resolved, kind="export"
        )
        self.job_history = job_history or JobHistory()
        self.progress_service = progress_service or ProgressService()
        self.glossary_library = glossary_library or GlossaryLibrary(
            artifact_dir=resolved
        )
        self.ocr_job_queue = ocr_job_queue or OCRJobQueue()
        self.config_store = config_store or InMemoryConfigStore()

    @classmethod
    def from_env(cls) -> LocalStateBackend:
        artifact_dir = (
            Path(os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir()))
            / "omniscribe"
        )
        # The ``from_env`` factory applies the ``omniscribe`` subdirectory
        # suffix so callers can reuse the same ``OMNISCRIBE_ARTIFACT_DIR``
        # across multiple deployments without colliding on disk.
        return cls(artifact_dir=artifact_dir)


def build_state_backend(settings: object) -> StateBackend:
    """Construct a :class:`StateBackend` from a settings-like object.

    The ``settings`` argument only needs up to four attributes:

    - ``state_backend`` — ``"memory"``, ``"redis"``, or ``"sqlite"``
    - ``redis_url`` — used when ``state_backend == "redis"``
    - ``artifact_directory`` — :class:`Path` threaded to every store
    - ``state_db_path`` — :class:`str | Path` used when
      ``state_backend == "sqlite"`` (default: ``<artifact_dir>/omniscribe-state.db``)

    The factory is the single boundary where backend selection fails loud:
    an unknown value raises :class:`RuntimeError` (not :class:`ValueError`)
    so the failure mode is unmistakable at startup.
    """
    backend_name = getattr(settings, "state_backend", None)
    if backend_name == "memory":
        artifact_dir = getattr(settings, "artifact_directory", None)
        return LocalStateBackend(artifact_dir=artifact_dir)
    if backend_name == "redis":
        redis_url = getattr(settings, "redis_url", None)
        try:
            import redis  # noqa: F401  -- probe for the optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "OMNISCRIBE_STATE_BACKEND=redis requires the optional "
                "`redis` package. Install it with `uv add redis` "
                "(or `pip install redis`)."
            ) from exc
        from omniscribe.api.services.state_backend_redis import RedisStateBackend

        artifact_dir = getattr(settings, "artifact_directory", None)
        redis_kwargs: dict[str, object] = {}
        if redis_url is not None:
            redis_kwargs["redis_url"] = redis_url
        if artifact_dir is not None:
            redis_kwargs["artifact_dir"] = artifact_dir
        return RedisStateBackend(**redis_kwargs)  # type: ignore[arg-type,return-value]
    if backend_name == "sqlite":
        from omniscribe.api.services.state_backend_sqlite import SQLiteStateBackend

        artifact_dir = getattr(settings, "artifact_directory", None)
        db_path = getattr(settings, "state_db_path", None)
        sqlite_kwargs: dict[str, object] = {}
        if db_path is not None:
            sqlite_kwargs["db_path"] = db_path
        if artifact_dir is not None:
            sqlite_kwargs["artifact_dir"] = artifact_dir
        return SQLiteStateBackend(**sqlite_kwargs)  # type: ignore[arg-type,return-value]
    raise RuntimeError(
        f"Unknown OMNISCRIBE_STATE_BACKEND={backend_name!r}. "
        "Expected 'memory', 'redis', or 'sqlite'."
    )


__all__ = ["LocalStateBackend", "StateBackend", "build_state_backend"]
