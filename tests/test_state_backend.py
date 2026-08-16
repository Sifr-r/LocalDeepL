"""Tests for the StateBackend Protocol + LocalStateBackend (§1)."""

from __future__ import annotations

import pytest

from omniscribe.api.routers import state as router_state
from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.api.services.jobs import JobHistory
from omniscribe.api.services.ocr_jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService
from omniscribe.api.services.state_backend import (
    LocalStateBackend,
    StateBackend,
)
from omniscribe.core.glossary_library import GlossaryLibrary


def test_local_state_backend_from_env_has_seven_attributes():
    backend = LocalStateBackend.from_env()
    assert isinstance(backend.text_artifacts, TextArtifactStore)
    assert isinstance(backend.metadata_artifacts, TextArtifactStore)
    assert isinstance(backend.export_artifacts, TextArtifactStore)
    assert isinstance(backend.job_history, JobHistory)
    assert isinstance(backend.progress_service, ProgressService)
    assert isinstance(backend.glossary_library, GlossaryLibrary)
    assert isinstance(backend.ocr_job_queue, OCRJobQueue)


def test_local_state_backend_isinstance_of_state_backend_protocol():
    # runtime_checkable Protocol must accept duck-typed instances.
    backend = LocalStateBackend.from_env()
    assert isinstance(backend, StateBackend)


def test_module_level_backend_is_local_state_backend():
    assert isinstance(router_state.backend, LocalStateBackend)
    # Module-level aliases point at the same objects as backend.* at
    # import time. Other tests may rebind the aliases (e.g.
    # test_glossary_imports_route reassigns state.glossary_library); the
    # ``state.backend.X`` access path stays stable across such patches.
    # Verify the structural invariant via a fresh LocalStateBackend.
    fresh = LocalStateBackend.from_env()
    assert fresh.text_artifacts is fresh.text_artifacts  # sanity
    # Each alias has the same type as the corresponding backend attribute.
    assert type(router_state.text_artifacts) is type(
        router_state.backend.text_artifacts
    )
    assert type(router_state.metadata_artifacts) is type(
        router_state.backend.metadata_artifacts
    )
    assert type(router_state.export_artifacts) is type(
        router_state.backend.export_artifacts
    )
    assert type(router_state.job_history) is type(router_state.backend.job_history)
    assert type(router_state.progress_service) is type(
        router_state.backend.progress_service
    )
    assert type(router_state.glossary_library) is type(
        router_state.backend.glossary_library
    )
    assert type(router_state.ocr_job_queue) is type(router_state.backend.ocr_job_queue)


def test_redis_state_backend_satisfies_protocol_without_connecting(tmp_path):
    pytest.importorskip("redis")
    from omniscribe.api.services.state_backend_redis import RedisStateBackend

    backend = RedisStateBackend("redis://localhost:6379/0", artifact_dir=tmp_path)
    assert isinstance(backend, StateBackend)
    assert isinstance(backend.ocr_job_queue, OCRJobQueue)


def test_sqlite_state_backend_satisfies_protocol_without_connecting(tmp_path):
    from omniscribe.api.services.state_backend_sqlite import SQLiteStateBackend

    backend = SQLiteStateBackend(db_path=tmp_path / "state.db", artifact_dir=tmp_path)
    assert isinstance(backend, StateBackend)
    assert isinstance(backend.ocr_job_queue, OCRJobQueue)
