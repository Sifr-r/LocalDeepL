"""SQLiteStateBackend: same surface on disk, WAL mode, persistence."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from omniscribe.plugins.state_backend import JobRecord, SQLiteStateBackend


@pytest.fixture
async def backend(tmp_path: Path) -> SQLiteStateBackend:
    impl = SQLiteStateBackend(
        db_path=tmp_path / "state.db", blob_dir=tmp_path / "blobs"
    )
    await impl.open()
    yield impl  # type: ignore[misc]
    await impl.aclose()


async def test_wal_mode_enabled(tmp_path: Path) -> None:
    impl = SQLiteStateBackend(db_path=tmp_path / "state.db", blob_dir=tmp_path)
    await impl.open()
    conn = sqlite3.connect(str(tmp_path / "state.db"))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    await impl.aclose()
    assert mode == "wal"


async def test_artifact_roundtrip_blob_on_disk(
    backend: SQLiteStateBackend, tmp_path: Path
) -> None:
    await backend.put_artifact(
        id="a1",
        token="tok",
        owner_job_id="job-1",
        content_type="application/pdf",
        blob=b"sqlite-bytes",
        ttl_seconds=3600,
    )
    result = await backend.get_artifact("a1", "tok")
    assert result is not None
    assert result.blob == b"sqlite-bytes"
    assert (tmp_path / "blobs" / "a1.bin").is_file()


async def test_artifact_wrong_token(backend: SQLiteStateBackend) -> None:
    await backend.put_artifact(
        id="a1",
        token="tok",
        owner_job_id="j",
        content_type="t",
        blob=b"x",
        ttl_seconds=1,
    )
    assert await backend.get_artifact("a1", "nope") is None


async def test_artifact_delete_removes_blob_file(
    backend: SQLiteStateBackend, tmp_path: Path
) -> None:
    await backend.put_artifact(
        id="a1",
        token="tok",
        owner_job_id="j",
        content_type="t",
        blob=b"x",
        ttl_seconds=1,
    )
    blob_file = tmp_path / "blobs" / "a1.bin"
    assert blob_file.is_file()
    await backend.delete_artifact("a1")
    assert await backend.get_artifact("a1", "tok") is None
    assert not blob_file.exists()


async def test_put_artifact_replaces_unlinks_previous_blob_file(
    backend: SQLiteStateBackend, tmp_path: Path
) -> None:
    """Pedantic 1.5 / test gap 5.2: ``INSERT OR REPLACE`` must unlink the
    prior ``.bin`` if the existing row points to a different path.

    Simulates the operator-cleanup / backup-restore / ad-hoc-SQL scenario
    where the row's ``blob_path`` is updated out-of-band to a file that
    is not the canonical ``<blob_dir>/<id>.bin``. A subsequent
    ``put_artifact`` for the same id must not leave the stale file
    behind.
    """
    # Seed an artifact and a sibling file the row will be repointed at.
    await backend.put_artifact(
        id="a1",
        token="tok",
        owner_job_id="j",
        content_type="t",
        blob=b"v1",
        ttl_seconds=3600,
    )
    canonical = tmp_path / "blobs" / "a1.bin"
    sibling_dir = tmp_path / "stale_blobs"
    sibling_dir.mkdir()
    sibling = sibling_dir / "a1.bin"
    sibling.write_bytes(b"v0-from-backup")
    # Ad-hoc SQL: repoint the row to the sibling file (no API path does
    # this; this models operator cleanup / backup restore / ad-hoc SQL).
    conn = sqlite3.connect(str(tmp_path / "state.db"))
    conn.execute(
        "UPDATE artifacts SET blob_path = ? WHERE id = ?",
        (str(sibling), "a1"),
    )
    conn.commit()
    conn.close()

    # The previous fix would have written ``v2`` to ``canonical``,
    # updated the row, and left ``sibling`` orphaned on disk.
    await backend.put_artifact(
        id="a1",
        token="tok2",
        owner_job_id="j",
        content_type="t",
        blob=b"v2",
        ttl_seconds=3600,
    )

    assert canonical.read_bytes() == b"v2"
    assert not sibling.exists(), "previous blob file leaked on INSERT OR REPLACE"
    record = await backend.get_artifact("a1", "tok2")
    assert record is not None and record.blob == b"v2"


async def test_artifact_prune(backend: SQLiteStateBackend) -> None:
    await backend.put_artifact(
        id="short",
        token="t",
        owner_job_id="j",
        content_type="c",
        blob=b"x",
        ttl_seconds=1,
    )
    await backend.put_artifact(
        id="long",
        token="t",
        owner_job_id="j",
        content_type="c",
        blob=b"y",
        ttl_seconds=1000,
    )
    removed = await backend.prune_expired_artifacts(now=time.time() + 5)
    assert removed == 1
    assert await backend.get_artifact("short", "t") is None
    assert await backend.get_artifact("long", "t") is not None


async def test_job_roundtrip_and_ordering(backend: SQLiteStateBackend) -> None:
    for index in range(3):
        await backend.upsert_job(
            JobRecord(
                job_id=f"job-{index}",
                status="queued",
                request_meta={"page": index},
                created_at=float(index),
                updated_at=float(index),
            )
        )
    record = await backend.get_job("job-1")
    assert record is not None
    assert record.request_meta == {"page": 1}
    listed = await backend.list_jobs(limit=2)
    assert [r.job_id for r in listed] == ["job-2", "job-1"]
    await backend.upsert_job(JobRecord(job_id="job-1", status="complete"))
    assert (await backend.get_job("job-1")).status == "complete"  # type: ignore[union-attr]
    await backend.delete_job("job-0")
    assert await backend.get_job("job-0") is None
    assert await backend.clear_jobs() == 2


async def test_channel_one_shot_consume(backend: SQLiteStateBackend) -> None:
    await backend.put_channel("ch1", "tok", "job-1", ttl_seconds=600)
    assert await backend.get_channel("ch1") is not None
    assert await backend.consume_channel("ch1", "tok") is not None
    assert await backend.consume_channel("ch1", "tok") is None
    assert await backend.consume_channel("ch1", "wrong") is None
    await backend.delete_channel("ch1")
    assert await backend.get_channel("ch1") is None
    await backend.put_channel("stale", "t", "j", ttl_seconds=1)
    assert await backend.prune_expired_channels(now=time.time() + 5) == 1


async def test_persistence_across_reopen(tmp_path: Path) -> None:
    first = SQLiteStateBackend(
        db_path=tmp_path / "state.db", blob_dir=tmp_path / "blobs"
    )
    await first.open()
    await first.put_artifact(
        id="kept",
        token="tok",
        owner_job_id="j",
        content_type="c",
        blob=b"keep",
        ttl_seconds=99,
    )
    await first.upsert_job(JobRecord(job_id="j1", status="complete"))
    await first.aclose()

    second = SQLiteStateBackend(
        db_path=tmp_path / "state.db", blob_dir=tmp_path / "blobs"
    )
    await second.open()
    result = await second.get_artifact("kept", "tok")
    assert result is not None and result.blob == b"keep"
    assert (await second.get_job("j1")) is not None
    await second.aclose()


async def test_operations_before_open_raise(tmp_path: Path) -> None:
    impl = SQLiteStateBackend(db_path=tmp_path / "x.db", blob_dir=tmp_path)
    with pytest.raises(RuntimeError):
        await impl.get_job("j")
