"""Artifacts plugin: token-gated storage over StateBackend + ArtifactCreated."""

from __future__ import annotations

import re

import pytest

from omniscribe.harness.context import Context
from omniscribe.harness.errors import ServiceNotFoundError
from omniscribe.harness.events import Event
from omniscribe.plugins import artifacts as art
from omniscribe.plugins import state_backend as sb
from omniscribe.plugins.artifacts import ArtifactCreated, ArtifactStore


async def _boot() -> Context:
    ctx = Context()
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    await ctx.plugin(art.ArtifactsPlugin(), config={})
    return ctx


async def test_put_returns_handle_with_expected_shapes() -> None:
    ctx = await _boot()
    store = ctx.inject(ArtifactStore)
    handle = await store.put(
        b"pdf-bytes", content_type="application/pdf", owner_job_id="job-1"
    )
    assert re.fullmatch(r"[0-9a-f]{32}", handle.id)  # uuid4().hex
    # secrets.token_urlsafe(32) → 43 urlsafe base64 chars
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", handle.token)
    await ctx.dispose()


async def test_get_roundtrip_and_token_gate() -> None:
    ctx = await _boot()
    store = ctx.inject(ArtifactStore)
    handle = await store.put(
        b"payload", content_type="text/plain", owner_job_id="job-1"
    )
    result = await store.get(handle.id, handle.token)
    assert result is not None
    assert result.blob == b"payload"
    assert result.record.content_type == "text/plain"
    assert result.record.owner_job_id == "job-1"
    assert await store.get(handle.id, "wrong-token") is None
    await ctx.dispose()


async def test_delete_removes_artifact() -> None:
    ctx = await _boot()
    store = ctx.inject(ArtifactStore)
    handle = await store.put(b"x", content_type="t/t", owner_job_id="j")
    await store.delete(handle.id)
    assert await store.get(handle.id, handle.token) is None
    await ctx.dispose()


async def test_put_emits_artifact_created() -> None:
    ctx = await _boot()
    seen: list[ArtifactCreated] = []

    def _on_created(event: Event) -> None:
        assert isinstance(event, ArtifactCreated)
        seen.append(event)

    ctx.on(ArtifactCreated, _on_created)
    store = ctx.inject(ArtifactStore)
    handle = await store.put(b"x", content_type="application/pdf", owner_job_id="job-9")
    assert len(seen) == 1
    assert seen[0].artifact_id == handle.id
    assert seen[0].owner_job_id == "job-9"
    assert seen[0].content_type == "application/pdf"
    await ctx.dispose()


async def test_missing_state_backend_fails_loud() -> None:
    ctx = Context()
    with pytest.raises(ServiceNotFoundError):
        await ctx.plugin(art.ArtifactsPlugin(), config={})
    await ctx.dispose()
