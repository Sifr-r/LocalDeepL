import asyncio
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from redis import Redis

from omniscribe.api.services.artifacts import (
    DEFAULT_ARTIFACT_TTL_SECONDS,
    DEFAULT_MAX_ARTIFACT_ENTRIES,
    ArtifactAccessDeniedError,
    ArtifactNotFoundError,
    TextArtifactHandle,
    TextArtifactStore,
    _delete_file,
    _validate_artifact_id,
    _validate_token,
)
from omniscribe.api.services.config_store import RedisConfigStore
from omniscribe.api.services.jobs import (
    JobHistory,
    JobRecord,
    JobStatus,
    _clean_duration,
    _clean_failed_pages,
    _clean_optional_text,
    _clean_required_text,
    _clean_status,
    _current_timestamp,
)
from omniscribe.api.services.ocr.jobs import OCRJobQueue
from omniscribe.api.services.progress import ProgressService
from omniscribe.core.lexicon import (
    LanceDBLexiconStore,
    LexiconStore,
    get_default_embedding_model,
)


class RedisTextArtifactStore(TextArtifactStore):
    """Redis-backed storage for Text Artifact metadata."""

    EXPIRATIONS_KEY = "omniscribe:artifacts:expirations"

    def __init__(
        self,
        redis_url: str,
        prefix: str,
        *,
        ttl_seconds: float = DEFAULT_ARTIFACT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ARTIFACT_ENTRIES,
        clock: Callable[[], float] = time.time,
        artifact_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        super().__init__(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
            clock=clock,
            artifact_dir=artifact_dir,
        )
        self.prefix = prefix
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def _key(self, artifact_id: str) -> str:
        return f"{self.prefix}:{artifact_id}"

    def put(
        self,
        *,
        artifact_id: str,
        token: str,
        path: str | os.PathLike[str],
    ) -> TextArtifactHandle:
        self.cleanup_expired()
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        artifact_path = self._resolve_artifact_path(path)
        now = self._clock()
        expires_at = now + self._ttl_seconds

        key = self._key(artifact_id)

        # We store token and path. Expiry is managed by Redis TTL and tracked in ZSET.
        payload = {
            "token": token,
            "path": str(artifact_path),
        }
        self._redis.set(key, json.dumps(payload), ex=int(self._ttl_seconds))

        member = json.dumps({"key": key, "path": str(artifact_path)})
        self._redis.zadd(self.EXPIRATIONS_KEY, {member: expires_at})

        return TextArtifactHandle(
            artifact_id=artifact_id,
            token=token,
            path=str(artifact_path),
            expires_at=expires_at,
        )

    async def get(self, artifact_id: str, token: str) -> str:
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        key = self._key(artifact_id)
        data = await asyncio.to_thread(self._redis.get, key)
        if not data:
            raise ArtifactNotFoundError("Artifact was not found.")

        entry: dict[str, Any] = json.loads(data)
        import secrets

        if not secrets.compare_digest(entry["token"], token):
            raise ArtifactAccessDeniedError("Artifact token does not match.")

        return cast(str, entry["path"])

    def pop(self, artifact_id: str, token: str) -> str | None:
        _validate_artifact_id(artifact_id)
        _validate_token(token)
        self.cleanup_expired()
        key = self._key(artifact_id)
        data = self._redis.get(key)
        if not data:
            return None

        entry: dict[str, Any] = json.loads(data)
        import secrets

        if not secrets.compare_digest(entry["token"], token):
            raise ArtifactAccessDeniedError("Artifact token does not match.")

        self._redis.delete(key)
        path = str(entry["path"])
        member = json.dumps({"key": key, "path": path})
        self._redis.zrem(self.EXPIRATIONS_KEY, member)
        return cast(str | None, path)

    async def delete(self, artifact_id: str, token: str) -> bool:
        path = self.pop(artifact_id, token)
        if not path:
            return False
        await asyncio.to_thread(_delete_file, Path(path))
        return True

    def clear(self) -> list[str]:
        # SCAN and delete all keys with this prefix
        keys = []
        paths = []
        for key in self._redis.scan_iter(f"{self.prefix}:*"):
            data = self._redis.get(key)
            if data:
                entry = json.loads(data)
                p = str(entry["path"])
                paths.append(p)
                _delete_file(Path(p))
                member = json.dumps({"key": key, "path": p})
                self._redis.zrem(self.EXPIRATIONS_KEY, member)
            keys.append(key)
        if keys:
            self._redis.delete(*keys)
        return paths

    def cleanup_expired(self) -> list[str]:
        now = self._clock()
        expired_members = self._redis.zrangebyscore(self.EXPIRATIONS_KEY, "-inf", now)
        removed_paths: list[str] = []
        if not expired_members:
            return removed_paths

        for item in expired_members:
            try:
                info = json.loads(cast(str, item))
                key = info.get("key")
                path_str = info.get("path")
                if key:
                    self._redis.delete(key)
                if path_str:
                    _delete_file(Path(path_str))
                    removed_paths.append(str(path_str))
            except Exception:
                pass

        self._redis.zremrangebyscore(self.EXPIRATIONS_KEY, "-inf", now)
        return removed_paths

    def __len__(self) -> int:
        self.cleanup_expired()
        return sum(1 for _ in self._redis.scan_iter(f"{self.prefix}:*"))


class RedisJobHistory(JobHistory):
    """Redis-backed storage for Job History."""

    def __init__(
        self,
        redis_url: str,
        *,
        max_jobs: int = 1000,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(max_jobs=max_jobs, now=now)
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self.key = "omniscribe:jobs"

    def record(
        self,
        *,
        job_id: str,
        filename: str,
        model: str,
        pipeline_mode: str,
        pages: str | None,
        duration_s: float,
        status: JobStatus,
        failed_pages: Sequence[int] = (),
        text_artifact_id: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            id=_clean_required_text(job_id, "job_id"),
            filename=_clean_required_text(filename, "filename"),
            model=_clean_required_text(model, "model"),
            pipeline_mode=_clean_required_text(pipeline_mode, "pipeline_mode"),
            pages=_clean_optional_text(pages, "pages"),
            duration_s=_clean_duration(duration_s),
            timestamp=_current_timestamp(self._now),
            status=_clean_status(status),
            failed_pages=_clean_failed_pages(failed_pages),
            text_artifact_id=(
                _clean_optional_text(text_artifact_id, "text_artifact_id")
                if text_artifact_id is not None
                else None
            ),
        )
        payload = json.dumps(record.to_dict())
        self._redis.lpush(self.key, payload)
        self._redis.ltrim(self.key, 0, self.max_jobs - 1)
        return record

    def list(self) -> list[dict[str, Any]]:
        raw_list: list[Any] = self._redis.lrange(self.key, 0, -1)
        typed: list[dict[str, Any]] = []
        for item in raw_list:
            typed.append(cast(dict[str, Any], json.loads(item)))
        return typed

    def clear(self) -> None:
        self._redis.delete(self.key)


class RedisStateBackend:
    """Redis-backed StateBackend implementation."""

    lexicon_store: LexiconStore
    config_store: RedisConfigStore

    def __init__(
        self,
        redis_url: str,
        artifact_dir: str | os.PathLike[str] | None = None,
        lexicon_store: LexiconStore | None = None,
    ) -> None:
        import tempfile
        from pathlib import Path

        resolved_dir = (
            artifact_dir
            if artifact_dir is not None
            else os.getenv("OMNISCRIBE_ARTIFACT_DIR", tempfile.gettempdir())
        )
        self.artifact_dir = Path(resolved_dir) / "omniscribe"
        self.text_artifacts = RedisTextArtifactStore(
            redis_url, "omniscribe:artifacts:text", artifact_dir=self.artifact_dir
        )
        self.metadata_artifacts = RedisTextArtifactStore(
            redis_url, "omniscribe:artifacts:meta", artifact_dir=self.artifact_dir
        )
        self.export_artifacts = RedisTextArtifactStore(
            redis_url, "omniscribe:artifacts:export", artifact_dir=self.artifact_dir
        )
        self.job_history = RedisJobHistory(redis_url)
        self.progress_service = ProgressService(redis_url=redis_url)
        self.lexicon_store = lexicon_store or LanceDBLexiconStore(
            path=self.artifact_dir / "lexicon.lance",
            embedding_model=get_default_embedding_model(),
        )
        self.ocr_job_queue = OCRJobQueue()
        # Duck-typed config-store attribute (see
        # ``api/services/state/base.py`` module docstring). Not part of
        # the :class:`StateBackend` Protocol.
        self.config_store = RedisConfigStore(redis_url)
