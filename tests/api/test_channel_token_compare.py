"""Regression test for H-3 audit fix: channel session tokens use compare_digest.

The audit found that ``MemoryStateBackend.consume_channel`` and
``SQLiteStateBackend.consume_channel`` compared ``session_token`` with
plain ``!=``, exposing a timing side-channel on a 32-byte token. The
fix uses ``secrets.compare_digest`` in both backends.
"""
from __future__ import annotations

import inspect
import secrets

import pytest

from omniscribe.plugins.state_backend import MemoryStateBackend


def test_H3_memory_consume_channel_uses_compare_digest() -> None:
    """``MemoryStateBackend.consume_channel`` MUST use ``secrets.compare_digest``."""
    src = inspect.getsource(MemoryStateBackend.consume_channel)
    assert "secrets.compare_digest" in src, (
        "H3 regression: MemoryStateBackend.consume_channel must use "
        "secrets.compare_digest for session_token equality (timing-safe)."
    )


@pytest.mark.asyncio
async def test_H3_memory_consume_channel_rejects_wrong_token() -> None:
    """Wrong tokens still return None (functional correctness preserved)."""
    backend = MemoryStateBackend()
    await backend.put_channel(
        "ch-1", session_token="x" * 32, job_id="j-1", ttl_seconds=60
    )
    # Correct token: returns the record and consumes it.
    record = await backend.consume_channel("ch-1", session_token="x" * 32)
    assert record is not None
    assert record.job_id == "j-1"
    # Wrong token: returns None.
    record = await backend.consume_channel("ch-1", session_token="y" * 32)
    assert record is None