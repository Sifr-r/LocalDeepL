"""MemoryStateBackend: full Protocol surface."""

from __future__ import annotations

import time

import pytest

from omniscribe.plugins.state_backend import JobRecord, MemoryStateBackend


@pytest.fixture
def backend() -> MemoryStateBackend:
    return MemoryStateBackend()


async def _put_artifact(
    backend: MemoryStateBackend, artifact_id: str = "a1", ttl: int = 3600
) -> None:
    await backend.put_artifact(
        id=artifact_id,
        token="tok",
        owner_job_id="job-1",
        content_type="application/pdf",
        blob=b"pdf-bytes",
        ttl_seconds=ttl,
    )


async def test_artifact_roundtrip(backend: MemoryStateBackend) -> None:
    await _put_artifact(backend)
    result = await backend.get_artifact("a1", "tok")
    assert result is not None
    assert result.blob == b"pdf-bytes"
    assert result.record.content_type == "application/pdf"
    assert result.record.owner_job_id == "job-1"


async def test_artifact_wrong_token_returns_none(backend: MemoryStateBackend) -> None:
    await _put_artifact(backend)
    assert await backend.get_artifact("a1", "bad") is None
    assert await backend.get_artifact("missing", "tok") is None


async def test_artifact_delete(backend: MemoryStateBackend) -> None:
    await _put_artifact(backend)
    await backend.delete_artifact("a1")
    assert await backend.get_artifact("a1", "tok") is None


async def test_artifact_prune_only_expired(backend: MemoryStateBackend) -> None:
    await _put_artifact(backend, artifact_id="short", ttl=1)
    await _put_artifact(backend, artifact_id="long", ttl=10_000)
    removed = await backend.prune_expired_artifacts(now=time.time() + 5)
    assert removed == 1
    assert await backend.get_artifact("short", "tok") is None
    assert await backend.get_artifact("long", "tok") is not None


async def test_artifact_blob_cap(
    backend: MemoryStateBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "omniscribe.plugins.state_backend_memory._MEMORY_BLOB_CAP_BYTES", 10
    )
    with pytest.raises(ValueError):
        await backend.put_artifact(
            id="huge",
            token="t",
            owner_job_id="j",
            content_type="application/octet-stream",
            blob=b"eleven-byte",
            ttl_seconds=10,
        )


async def test_job_upsert_get_list_clear_delete(backend: MemoryStateBackend) -> None:
    for index in range(3):
        await backend.upsert_job(
            JobRecord(
                job_id=f"job-{index}",
                status="queued",
                created_at=float(index),
                updated_at=float(index),
            )
        )
    record = await backend.get_job("job-1")
    assert record is not None and record.status == "queued"
    listed = await backend.list_jobs(limit=2)
    assert [r.job_id for r in listed] == ["job-2", "job-1"]  # newest first
    assert await backend.clear_jobs() == 3
    assert await backend.get_job("job-0") is None
    await backend.upsert_job(JobRecord(job_id="solo", status="running"))
    await backend.delete_job("solo")
    assert await backend.get_job("solo") is None


async def test_job_upsert_overwrites(backend: MemoryStateBackend) -> None:
    await backend.upsert_job(JobRecord(job_id="j", status="queued"))
    await backend.upsert_job(JobRecord(job_id="j", status="complete"))
    record = await backend.get_job("j")
    assert record is not None and record.status == "complete"


async def test_channel_put_get_consume_delete_prune(
    backend: MemoryStateBackend,
) -> None:
    await backend.put_channel("ch1", "session-tok", "job-1", ttl_seconds=600)
    record = await backend.get_channel("ch1")
    assert record is not None and record.session_token == "session-tok"
    # one-shot consume
    assert await backend.consume_channel("ch1", "session-tok") is not None
    assert await backend.consume_channel("ch1", "session-tok") is None
    # wrong token never consumes
    await backend.put_channel("ch2", "tok-2", "job-2", ttl_seconds=600)
    assert await backend.consume_channel("ch2", "wrong") is None
    assert await backend.get_channel("ch2") is not None
    await backend.delete_channel("ch2")
    assert await backend.get_channel("ch2") is None
    # prune
    await backend.put_channel("stale", "t", "j", ttl_seconds=1)
    removed = await backend.prune_expired_channels(now=time.time() + 5)
    assert removed >= 1
    assert await backend.get_channel("stale") is None


async def test_aclose_is_noop(backend: MemoryStateBackend) -> None:
    await backend.aclose()
