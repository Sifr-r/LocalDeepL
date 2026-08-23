"""StateBackendPlugin: backend selection and registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from omniscribe.config import RuntimeSettings
from omniscribe.harness.context import Context
from omniscribe.plugins import state_backend as sb
from omniscribe.plugins.state_backend import (
    MemoryStateBackend,
    SQLiteStateBackend,
    StateBackend,
)


async def test_memory_backend_registered() -> None:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    assert isinstance(ctx.inject(StateBackend), MemoryStateBackend)
    await ctx.dispose()


async def test_default_backend_is_memory() -> None:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={})
    assert isinstance(ctx.inject(StateBackend), MemoryStateBackend)
    await ctx.dispose()


async def test_sqlite_backend_registered(tmp_path: Path) -> None:
    ctx = Context()
    await ctx.plugin(
        sb.StateBackendPlugin(),
        config={"backend": "sqlite", "sqlite_path": str(tmp_path / "state.db")},
    )
    backend = ctx.inject(StateBackend)
    assert isinstance(backend, SQLiteStateBackend)
    assert (tmp_path / "state.db").exists()
    await ctx.dispose()
    # dispose closed the connection via the registered effect
    with pytest.raises(RuntimeError):
        await backend.get_job("j")


async def test_redis_backend_rejected_with_clear_message() -> None:
    ctx = Context()
    with pytest.raises(ValueError, match=r"memory.*sqlite|redis"):
        await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "redis"})
    await ctx.dispose()


async def test_empty_sqlite_path_defaults_to_artifact_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sb,
        "load_settings",
        lambda: RuntimeSettings(artifact_base_dir=tmp_path),
    )
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "sqlite"})
    assert (tmp_path / "omniscribe-state.db").exists()
    await ctx.dispose()
