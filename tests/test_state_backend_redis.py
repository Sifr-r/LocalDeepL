"""Coverage push for ``RedisStateBackend`` (audit P3-11).

Runs against ``fakeredis`` (shared :class:`fakeredis.FakeServer` so the
three artifact stores + job history behave like separate workers talking
to one Redis), exercising the token-binding, prefix isolation, TTL, and
job-history trimming behavior that construction-only tests never reach.
"""

from __future__ import annotations

from pathlib import Path

import fakeredis
import pytest

from omniscribe.api.services import state_backend_redis as redis_backend_mod
from omniscribe.api.services.artifacts import (
    ArtifactAccessDeniedError,
    ArtifactNotFoundError,
)
from omniscribe.api.services.jobs import JobStatus
from omniscribe.api.services.state_backend import StateBackend
from omniscribe.api.services.state_backend_redis import (
    RedisJobHistory,
    RedisStateBackend,
    RedisTextArtifactStore,
)

_ARTIFACT_ID = "a" * 32
_OTHER_ARTIFACT_ID = "b" * 32
_TOKEN = "t" * 43
_OTHER_TOKEN = "u" * 43


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    """Route every ``Redis.from_url`` in the backend module to one fake server."""
    server = fakeredis.FakeServer()

    class _FakeRedisFactory:
        @staticmethod
        def from_url(url: str, decode_responses: bool = False):
            return fakeredis.FakeRedis(server=server, decode_responses=decode_responses)

    monkeypatch.setattr(redis_backend_mod, "Redis", _FakeRedisFactory)
    return server


@pytest.fixture()
def store(fake_redis, tmp_path: Path) -> RedisTextArtifactStore:
    return RedisTextArtifactStore(
        "redis://fake:6379/0", "omniscribe:artifacts:text", artifact_dir=tmp_path
    )


def _write_artifact_file(tmp_path: Path, name: str = "artifact.json") -> Path:
    path = tmp_path / name
    path.write_text("{}", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# RedisTextArtifactStore
# ---------------------------------------------------------------------------


def test_put_get_roundtrip_is_token_bound(
    store: RedisTextArtifactStore, tmp_path: Path
):
    path = _write_artifact_file(tmp_path)
    handle = store.put(artifact_id=_ARTIFACT_ID, token=_TOKEN, path=path)

    assert handle.artifact_id == _ARTIFACT_ID
    assert Path(_run(store.get(_ARTIFACT_ID, _TOKEN))) == path.resolve()


def test_get_rejects_wrong_token(store: RedisTextArtifactStore, tmp_path: Path):
    store.put(
        artifact_id=_ARTIFACT_ID, token=_TOKEN, path=_write_artifact_file(tmp_path)
    )

    with pytest.raises(ArtifactAccessDeniedError):
        _run(store.get(_ARTIFACT_ID, _OTHER_TOKEN))


def test_get_unknown_artifact_raises_not_found(store: RedisTextArtifactStore):
    with pytest.raises(ArtifactNotFoundError):
        _run(store.get(_OTHER_ARTIFACT_ID, _TOKEN))


def test_put_stores_redis_ttl(store: RedisTextArtifactStore, tmp_path: Path):
    """Retention rides on Redis TTL (the documented max_entries trade-off)."""
    store.put(
        artifact_id=_ARTIFACT_ID, token=_TOKEN, path=_write_artifact_file(tmp_path)
    )

    ttl = store._redis.ttl(store._key(_ARTIFACT_ID))
    assert 0 < ttl <= int(store._ttl_seconds)


def test_pop_removes_entry_but_keeps_file(
    store: RedisTextArtifactStore, tmp_path: Path
):
    path = _write_artifact_file(tmp_path)
    store.put(artifact_id=_ARTIFACT_ID, token=_TOKEN, path=path)

    popped = store.pop(_ARTIFACT_ID, _TOKEN)
    assert popped is not None
    assert Path(popped) == path.resolve()
    # Gone from Redis, file untouched.
    assert store.pop(_ARTIFACT_ID, _TOKEN) is None
    assert path.exists()


def test_pop_rejects_wrong_token(store: RedisTextArtifactStore, tmp_path: Path):
    store.put(
        artifact_id=_ARTIFACT_ID, token=_TOKEN, path=_write_artifact_file(tmp_path)
    )

    with pytest.raises(ArtifactAccessDeniedError):
        store.pop(_ARTIFACT_ID, _OTHER_TOKEN)


def test_delete_removes_entry_and_file(store: RedisTextArtifactStore, tmp_path: Path):
    path = _write_artifact_file(tmp_path)
    store.put(artifact_id=_ARTIFACT_ID, token=_TOKEN, path=path)

    assert _run(store.delete(_ARTIFACT_ID, _TOKEN)) is True
    assert not path.exists()
    assert _run(store.delete(_ARTIFACT_ID, _TOKEN)) is False


def test_clear_scopes_to_own_prefix(fake_redis, tmp_path: Path):
    text = RedisTextArtifactStore(
        "redis://fake:6379/0", "omniscribe:artifacts:text", artifact_dir=tmp_path
    )
    export = RedisTextArtifactStore(
        "redis://fake:6379/0", "omniscribe:artifacts:export", artifact_dir=tmp_path
    )
    text_file = _write_artifact_file(tmp_path, "text.json")
    export_file = _write_artifact_file(tmp_path, "export.json")
    text.put(artifact_id=_ARTIFACT_ID, token=_TOKEN, path=text_file)
    export.put(artifact_id=_OTHER_ARTIFACT_ID, token=_OTHER_TOKEN, path=export_file)

    removed = text.clear()

    assert removed == [str(text_file.resolve())]
    assert not text_file.exists()
    # The export store's artifact survives untouched.
    assert export_file.exists()
    assert Path(_run(export.get(_OTHER_ARTIFACT_ID, _OTHER_TOKEN))) == (
        export_file.resolve()
    )


# ---------------------------------------------------------------------------
# RedisJobHistory
# ---------------------------------------------------------------------------


def _record(
    history: RedisJobHistory, job_id: str, status: JobStatus = "complete"
) -> None:
    history.record(
        job_id=job_id,
        filename="doc.pdf",
        model="test-model",
        pipeline_mode="hybrid",
        pages=None,
        duration_s=1.5,
        status=status,
    )


def test_job_history_record_and_list_roundtrip(fake_redis):
    history = RedisJobHistory("redis://fake:6379/0")
    _record(history, "job-1")

    rows = history.list()
    assert len(rows) == 1
    assert rows[0]["id"] == "job-1"
    assert rows[0]["status"] == "complete"
    assert rows[0]["duration_s"] == 1.5


def test_job_history_lists_newest_first(fake_redis):
    history = RedisJobHistory("redis://fake:6379/0")
    _record(history, "job-1")
    _record(history, "job-2")

    assert [row["id"] for row in history.list()] == ["job-2", "job-1"]


def test_job_history_trims_to_max_jobs(fake_redis):
    history = RedisJobHistory("redis://fake:6379/0", max_jobs=3)
    for index in range(5):
        _record(history, f"job-{index}")

    rows = history.list()
    assert len(rows) == 3
    assert [row["id"] for row in rows] == ["job-4", "job-3", "job-2"]


def test_job_history_clear(fake_redis):
    history = RedisJobHistory("redis://fake:6379/0")
    _record(history, "job-1")

    history.clear()
    assert history.list() == []


# ---------------------------------------------------------------------------
# RedisStateBackend assembly
# ---------------------------------------------------------------------------


def test_backend_stores_are_prefix_isolated(fake_redis, tmp_path: Path):
    backend = RedisStateBackend("redis://fake:6379/0", artifact_dir=tmp_path)
    assert isinstance(backend, StateBackend)

    path = backend.artifact_dir / "shared.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")

    handle = backend.text_artifacts.put(
        artifact_id=_ARTIFACT_ID, token=_TOKEN, path=path
    )
    # Same id + a correct-looking token must not resolve through a
    # sibling store's prefix.
    with pytest.raises(ArtifactNotFoundError):
        _run(backend.export_artifacts.get(handle.artifact_id, handle.token))
    with pytest.raises(ArtifactNotFoundError):
        _run(backend.metadata_artifacts.get(handle.artifact_id, handle.token))


def test_backend_shares_one_artifact_dir(fake_redis, tmp_path: Path):
    backend = RedisStateBackend("redis://fake:6379/0", artifact_dir=tmp_path)

    assert backend.text_artifacts.artifact_dir == backend.artifact_dir
    assert backend.metadata_artifacts.artifact_dir == backend.artifact_dir
    assert backend.export_artifacts.artifact_dir == backend.artifact_dir


def _run(coro):
    import asyncio

    return asyncio.run(coro)
