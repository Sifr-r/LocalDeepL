"""Transcribe plugin — mounts transcription routes on the harness."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.runtime import RuntimeService
from omniscribe.plugins.transcribe.routes import build_transcribe_router
from omniscribe.plugins.transcribe.service import (
    TranscriptionService,
    TranscriptionServiceImpl,
)


class TranscribeSchema(BaseModel):
    """No configurable fields."""


class TranscribePlugin(Plugin):
    """Client-frozen transcription surface: sync + config + discovery."""

    Schema = TranscribeSchema

    async def apply(self, ctx: Context) -> None:
        store = ctx.inject(ArtifactStore)
        runtime = ctx.inject(RuntimeService)
        service = TranscriptionServiceImpl(runtime.settings, store)
        ctx.service(TranscriptionService, service)
        ctx.mount_router(build_transcribe_router(service))


plugin = TranscribePlugin()
