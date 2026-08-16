"""Cross-worker runtime-config store.

A small key/value abstraction layered on top of the StateBackend so the
``/api/config`` POST handler can persist updates in a way that all
uvicorn workers see. Each StateBackend implementation owns a
``config_store`` attribute (duck-typed, not part of the
:class:`omniscribe.api.services.state_backend.StateBackend` Protocol)
so the existing Protocol surface is preserved and the seven existing
attributes remain the only "required" ones.

Three implementations ship:

- :class:`InMemoryConfigStore` — per-process dict, **not** cross-worker
  visible. The default when ``OMNISCRIBE_STATE_BACKEND`` is unset.
- :class:`SQLiteConfigStore` — single-row table in the same SQLite file
  the :class:`~omniscribe.api.services.state_backend_sqlite.SQLiteStateBackend`
  uses. Cross-worker visible.
- :class:`RedisConfigStore` — single key in the same Redis instance
  the :class:`~omniscribe.api.services.state_backend_redis.RedisStateBackend`
  uses. Cross-worker visible.

The /api/config POST handler calls :meth:`is_cross_worker_visible`
before persisting: when the active store is the in-memory variant
the request is refused with a 503 + a clear remediation message so
operators do not see a silently-broken multi-worker deployment.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable


@runtime_checkable
class ConfigStore(Protocol):
    """Cross-worker-visible runtime config store.

    The :class:`~omniscribe.api.services.state_backend.StateBackend`
    Protocol does not list ``config_store``; every concrete backend
    still owns one as a duck-typed extra attribute so the Protocol
    surface stays at seven. This protocol is for the *value* of that
    attribute (``backend.config_store``) — it tells the
    :mod:`~omniscribe.api.routers.config` handlers how to talk to the
    active backend's storage layer.
    """

    def get_snapshot(self) -> dict[str, Any]: ...

    def update(self, values: dict[str, Any]) -> None: ...

    def is_cross_worker_visible(self) -> bool: ...


class InMemoryConfigStore:
    """Per-process config store. NOT cross-worker visible.

    The default when :class:`~omniscribe.api.services.state_backend.LocalStateBackend`
    is the active :class:`~omniscribe.api.services.state_backend.StateBackend`.
    The /api/config POST handler refuses updates with a 503 when this
    is the active store so operators get a clear error instead of a
    silently-broken multi-worker deployment (issue H1).

    The ``_cross_worker_visible`` attribute defaults to ``False`` and
    is intended to be flipped to ``True`` only by test fixtures that
    want to exercise the POST path without standing up a Redis or
    SQLite backend; production code should leave it alone.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})
        self._lock = threading.RLock()
        # Test-only override. Production callers (and the
        # ``/api/config`` handler) read this via
        # :meth:`is_cross_worker_visible` and act accordingly.
        self._cross_worker_visible: bool = False

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)

    def is_cross_worker_visible(self) -> bool:
        return self._cross_worker_visible


class SQLiteConfigStore:
    """SQLite-backed config store. Cross-worker visible.

    The schema is a single-row table keyed by ``id = 1``; updates are
    last-writer-wins because the Web UI's save flow is single-user
    (the Settings tab posts once per save and operators do not
    concurrently edit the same fields). The schema is created lazily
    in :meth:`__init__` so the first read on a fresh database
    succeeds without a separate migration step.

    Threading matches the rest of
    :mod:`~omniscribe.api.services.state_backend_sqlite`: each
    operation opens and closes its own ``sqlite3.Connection`` with
    WAL mode so concurrent readers do not block each other.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS omniscribe_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        payload TEXT NOT NULL
    );
    """
    _KEY = 1

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), isolation_level=None, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def get_snapshot(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM omniscribe_config WHERE id = ?",
                (self._KEY,),
            ).fetchone()
        if row is None:
            return {}
        try:
            return cast(dict[str, Any], json.loads(row[0]))
        except (TypeError, json.JSONDecodeError):
            return {}

    def update(self, values: dict[str, Any]) -> None:
        current = self.get_snapshot()
        current.update(values)
        payload = json.dumps(current)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO omniscribe_config (id, payload) VALUES (?, ?)",
                (self._KEY, payload),
            )

    def is_cross_worker_visible(self) -> bool:
        return True


class RedisConfigStore:
    """Redis-backed config store. Cross-worker visible.

    The whole config dict is serialised as JSON under a single key
    (``omniscribe:config``). The :class:`redis.Redis` client is
    created lazily in :meth:`__init__` so a missing optional
    dependency is surfaced at construction time, not at first write.
    """

    _KEY = "omniscribe:config"

    def __init__(self, redis_url: str) -> None:
        # Imported here so the optional ``redis`` package is only
        # required when an operator opts in to the Redis backend.
        from redis import Redis

        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def get_snapshot(self) -> dict[str, Any]:
        data = self._redis.get(self._KEY)
        if data is None:
            return {}
        try:
            return cast(dict[str, Any], json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return {}

    def update(self, values: dict[str, Any]) -> None:
        current = self.get_snapshot()
        current.update(values)
        self._redis.set(self._KEY, json.dumps(current))

    def is_cross_worker_visible(self) -> bool:
        return True


__all__ = [
    "ConfigStore",
    "InMemoryConfigStore",
    "RedisConfigStore",
    "SQLiteConfigStore",
]
