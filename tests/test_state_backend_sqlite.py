"""Tests for the SQLite-backed :class:`StateBackend` (Phase D3).

The acceptance criteria for this backend are:

1. **Persistence across restart** — a put / record survives a
   process restart (i.e. constructing a fresh instance against
   the same ``db_path``).
2. **Protocol surface** — :class:`SQLiteStateBackend` is
   duck-typed by :class:`StateBackend` (runtime_checkable).
3. **No surprises vs the in-memory backend** — TTL, max_entries,
   max_jobs, pop, delete, and clear all behave like the
   :class:`LocalStateBackend` tests in
   :mod:`tests.test_artifact_store` and
   :mod:`tests.test_jobs`.
4. **Factory wiring** — :func:`build_state_backend` returns a
   :class:`SQLiteStateBackend` when ``OMNISCRIBE_STATE_BACKEND=sqlite``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omniscribe.api.services.artifacts import ArtifactNotFoundError
from omniscribe.api.services.jobs import JobHistory
from omniscribe.api.services.state_backend import (
    LocalStateBackend,
    StateBackend,
    build_state_backend,
)
from omniscribe.api.services.state_backend_sqlite import (
    SQLiteJobHistory,
    SQLiteStateBackend,
    SQLiteTextArtifactStore,
)


class ManualClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _open_backend(db_path: Path, artifact_dir: Path) -> SQLiteStateBackend:
    return SQLiteStateBackend(db_path=db_path, artifact_dir=artifact_dir)


# ---------------------------------------------------------------------------
# Protocol + factory wiring
# ---------------------------------------------------------------------------


def test_sqlite_state_backend_satisfies_protocol(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path)
    assert isinstance(backend, StateBackend)
    # The seven attributes named by the Protocol are present and typed.
    assert isinstance(backend.text_artifacts, SQLiteTextArtifactStore)
    assert isinstance(backend.metadata_artifacts, SQLiteTextArtifactStore)
    assert isinstance(backend.export_artifacts, SQLiteTextArtifactStore)
    assert isinstance(backend.job_history, SQLiteJobHistory)
    assert backend.db_path == (tmp_path / "state.db").resolve()


def test_default_db_path_uses_artifact_dir(tmp_path: Path) -> None:
    backend = SQLiteStateBackend(artifact_dir=tmp_path)
    assert backend.db_path == (tmp_path / "omniscribe-state.db").resolve()


def test_build_state_backend_returns_sqlite_for_setting(tmp_path: Any) -> None:
    """``build_state_backend`` recognises ``state_backend == "sqlite"``."""

    class _Settings:
        state_backend = "sqlite"
        artifact_directory = tmp_path
        state_db_path = str(tmp_path / "state.db")

    backend = build_state_backend(_Settings())  # type: ignore[arg-type]
    assert isinstance(backend, SQLiteStateBackend)


def test_build_state_backend_uses_default_db_path_when_unset(tmp_path: Any) -> None:
    class _Settings:
        state_backend = "sqlite"
        artifact_directory = tmp_path
        state_db_path = None

    backend = build_state_backend(_Settings())  # type: ignore[arg-type]
    assert isinstance(backend, SQLiteStateBackend)
    assert backend.db_path == (tmp_path / "omniscribe-state.db").resolve()


def test_local_state_backend_still_works_for_default(tmp_path: Any) -> None:
    """The SQLite backend is opt-in; the default factory path is unchanged."""

    class _Settings:
        state_backend = "memory"
        artifact_directory = tmp_path
        state_db_path = None

    backend = build_state_backend(_Settings())  # type: ignore[arg-type]
    assert isinstance(backend, LocalStateBackend)


# ---------------------------------------------------------------------------
# TextArtifactStore round-trip + TTL + overflow
# ---------------------------------------------------------------------------


async def test_artifact_round_trip_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    files_dir = tmp_path / "files"

    first = _open_backend(db_path, files_dir)
    handle = await first.text_artifacts.create({0: ["first page"], 1: ["second"]})
    assert Path(handle.path).exists()

    # Brand-new instance against the same DB file: the row must
    # still be retrievable.
    second = _open_backend(db_path, files_dir)
    assert (
        await second.text_artifacts.get(handle.artifact_id, handle.token) == handle.path
    )


async def test_artifact_expiry_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    files_dir = tmp_path / "files"
    clock = ManualClock(0.0)

    first = SQLiteTextArtifactStore(
        db_path=db_path,
        table="omniscribe_artifact_text",
        ttl_seconds=5,
        clock=clock,
        artifact_dir=files_dir,
    )
    handle = await first.create({0: ["expires"]})
    clock.advance(6)

    # Reopen with a fresh instance; the same DB file should now
    # treat the row as expired.
    clock2 = ManualClock(6.0)
    second = SQLiteTextArtifactStore(
        db_path=db_path,
        table="omniscribe_artifact_text",
        ttl_seconds=5,
        clock=clock2,
        artifact_dir=files_dir,
    )
    with pytest.raises(ArtifactNotFoundError):
        await second.get(handle.artifact_id, handle.token)


async def test_artifact_max_entries_evicts_oldest_across_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state.db"
    files_dir = tmp_path / "files"

    first = SQLiteTextArtifactStore(
        db_path=db_path,
        table="omniscribe_artifact_text",
        max_entries=1,
        artifact_dir=files_dir,
    )
    older = await first.create({0: ["older"]})
    newer = await first.create({0: ["newer"]})

    # Reopen; the cap survives the restart.
    second = SQLiteTextArtifactStore(
        db_path=db_path,
        table="omniscribe_artifact_text",
        max_entries=1,
        artifact_dir=files_dir,
    )
    with pytest.raises(ArtifactNotFoundError):
        await second.get(older.artifact_id, older.token)
    assert await second.get(newer.artifact_id, newer.token) == newer.path


async def test_artifact_clear_removes_rows_and_files(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    a = await backend.text_artifacts.create({0: ["a"]})
    b = await backend.text_artifacts.create({0: ["b"]})

    removed = backend.text_artifacts.clear()
    assert sorted(removed) == sorted([a.path, b.path])
    assert not Path(a.path).exists()
    assert not Path(b.path).exists()
    assert len(backend.text_artifacts) == 0


def test_artifact_pop_is_token_bound(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    (tmp_path / "files").mkdir(parents=True, exist_ok=True)
    handle = backend.text_artifacts.put(
        artifact_id=backend.text_artifacts.issue_id(),
        token=backend.text_artifacts.issue_token(),
        path=tmp_path / "files" / "x.json",
    )
    Path(handle.path).write_text("{}", encoding="utf-8")

    assert backend.text_artifacts.pop(handle.artifact_id, handle.token) == handle.path
    # File stays on disk (pop, not delete).
    assert Path(handle.path).exists()
    assert backend.text_artifacts.pop(handle.artifact_id, handle.token) is None


async def test_artifact_delete_removes_backing_file(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    handle = await backend.text_artifacts.create({0: ["x"]})
    assert Path(handle.path).exists()

    assert await backend.text_artifacts.delete(handle.artifact_id, handle.token) is True
    assert not Path(handle.path).exists()
    assert (
        await backend.text_artifacts.delete(handle.artifact_id, handle.token) is False
    )


def test_separate_tables_for_each_artifact_store(tmp_path: Path) -> None:
    """text / metadata / export stores are independent SQLite tables."""
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    (tmp_path / "files").mkdir(parents=True, exist_ok=True)

    text_handle = backend.text_artifacts.put(
        artifact_id=backend.text_artifacts.issue_id(),
        token=backend.text_artifacts.issue_token(),
        path=tmp_path / "files" / "t.json",
    )
    meta_handle = backend.metadata_artifacts.put(
        artifact_id=backend.metadata_artifacts.issue_id(),
        token=backend.metadata_artifacts.issue_token(),
        path=tmp_path / "files" / "m.json",
    )
    Path(text_handle.path).write_text("{}", encoding="utf-8")
    Path(meta_handle.path).write_text("{}", encoding="utf-8")

    assert len(backend.text_artifacts) == 1
    assert len(backend.metadata_artifacts) == 1
    assert len(backend.export_artifacts) == 0
    # IDs are independent — the same UUID can exist in different tables.
    assert text_handle.artifact_id != meta_handle.artifact_id


# ---------------------------------------------------------------------------
# JobHistory round-trip + cap
# ---------------------------------------------------------------------------


def test_job_history_round_trip_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    files_dir = tmp_path / "files"

    first = _open_backend(db_path, files_dir)
    first.job_history.record(
        job_id="job-1",
        filename="doc.pdf",
        model="allenai/olmocr-2-7b",
        pipeline_mode="hybrid",
        pages="1-3",
        duration_s=4.2,
        status="complete",
    )
    first.job_history.record(
        job_id="job-2",
        filename="other.pdf",
        model="allenai/olmocr-2-7b",
        pipeline_mode="grounded",
        pages=None,
        duration_s=1.0,
        status="error",
        failed_pages=[0, 2],
    )

    second = _open_backend(db_path, files_dir)
    history = second.job_history.list()
    assert isinstance(second.job_history, JobHistory)
    # Newest-first; both jobs survive the restart.
    assert [entry["id"] for entry in history] == ["job-2", "job-1"]
    assert history[1]["filename"] == "doc.pdf"
    assert history[0]["failed_pages"] == [0, 2]


def test_job_history_max_jobs_caps_via_sql(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    backend.job_history = SQLiteJobHistory(backend.db_path, max_jobs=3)

    for index in range(5):
        backend.job_history.record(
            job_id=f"job-{index}",
            filename=f"doc-{index}.pdf",
            model="allenai/olmocr-2-7b",
            pipeline_mode="hybrid",
            pages=None,
            duration_s=0.1,
            status="complete",
        )

    history = backend.job_history.list()
    # Newest 3 survive; older two are deleted.
    assert [entry["id"] for entry in history] == ["job-4", "job-3", "job-2"]


def test_job_history_clear_empties_table(tmp_path: Path) -> None:
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    backend.job_history.record(
        job_id="job-1",
        filename="doc.pdf",
        model="allenai/olmocr-2-7b",
        pipeline_mode="hybrid",
        pages=None,
        duration_s=0.1,
        status="complete",
    )
    backend.job_history.clear()
    assert backend.job_history.list() == []


def test_job_history_validates_inputs(tmp_path: Path) -> None:
    """SQLite backend does not weaken the validation from JobHistory."""
    backend = _open_backend(tmp_path / "state.db", tmp_path / "files")
    with pytest.raises(ValueError):
        backend.job_history.record(
            job_id="",
            filename="doc.pdf",
            model="allenai/olmocr-2-7b",
            pipeline_mode="hybrid",
            pages=None,
            duration_s=0.1,
            status="complete",
        )
    with pytest.raises(ValueError):
        backend.job_history.record(
            job_id="job-1",
            filename="doc.pdf",
            model="allenai/olmocr-2-7b",
            pipeline_mode="hybrid",
            pages=None,
            duration_s=0.1,
            status="bogus",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Schema isolation across backend instances
# ---------------------------------------------------------------------------


def test_two_backends_against_the_same_db_share_state(tmp_path: Path) -> None:
    """Two SQLiteStateBackend instances pointed at the same file see
    each other's writes — this is the cross-process scaling story
    (multiple uvicorn workers can share the same artifact metadata
    + job history)."""
    db_path = tmp_path / "state.db"
    files_dir = tmp_path / "files"
    a = _open_backend(db_path, files_dir)
    b = _open_backend(db_path, files_dir)

    a.job_history.record(
        job_id="job-a",
        filename="a.pdf",
        model="allenai/olmocr-2-7b",
        pipeline_mode="hybrid",
        pages=None,
        duration_s=1.0,
        status="complete",
    )
    assert b.job_history.list()[0]["id"] == "job-a"


def test_two_backends_against_different_dbs_are_isolated(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    a = _open_backend(tmp_path / "a.db", files_dir)
    b = _open_backend(tmp_path / "b.db", files_dir)

    a.job_history.record(
        job_id="job-a",
        filename="a.pdf",
        model="allenai/olmocr-2-7b",
        pipeline_mode="hybrid",
        pages=None,
        duration_s=1.0,
        status="complete",
    )
    assert b.job_history.list() == []


# -- Audit-secondary D4-04: SQLite lock contention under concurrent writers --


def test_concurrent_writers_do_not_block_under_wal(tmp_path: Path) -> None:
    """N threads writing 50 artifacts each complete in bounded time.

    Audit-secondary D4-04: the previous test suite never spawned
    two concurrent writers, so the production ``WAL + timeout=30``
    setting had no test that proved it works. A regression to
    the default 5 s timeout (or removing ``WAL``) would not be
    caught.

    This test spawns 4 threads × 50 puts (200 total writes) and
    asserts all complete within a generous bound. The bound
    is loose (5 s) so a slow CI runner does not flake; the
    real signal is "no thread hung on a lock".
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    db_path = tmp_path / "omniscribe-state.db"
    backend = SQLiteStateBackend(db_path=db_path)

    def writer(thread_idx: int) -> int:
        # Re-open a fresh connection per call so each thread gets
        # its own SQLite connection (sqlite3 connections are not
        # safe to share across threads). The StateBackend opens
        # a connection per call internally, so the test mirrors
        # production.
        for i in range(50):
            aid = f"{thread_idx:02x}{i:030x}"
            backend.text_artifacts.put(
                artifact_id=aid,
                token="t" * 32,
                path=tmp_path / f"text_{aid}.json",
            )
        return 50

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(writer, idx) for idx in range(4)]
        results = [f.result(timeout=10) for f in as_completed(futures)]
    elapsed = time.monotonic() - t0

    assert results == [50, 50, 50, 50], "every thread must report 50 writes"
    # Loose bound so a slow CI does not flake; the real signal
    # is that no thread hung on a database lock. The previous
    # (no-WAL) implementation would either time out or
    # serialize the writes; either way the bound is hit.
    assert elapsed < 5.0, f"200 concurrent writes took {elapsed:.2f}s — lock contention"

    # All 200 artifacts are queryable through the same backend.
    assert len(backend.text_artifacts) == 200, (
        f"expected 200 artifacts after concurrent writes, got {len(backend.text_artifacts)}"
    )
