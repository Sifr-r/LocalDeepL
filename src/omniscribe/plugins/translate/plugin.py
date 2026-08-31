"""Translate plugin — mounts the translation routes over the JobQueue."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.artifacts import ArtifactStore
from omniscribe.plugins.jobs import JobQueue, TranslationJobRunner
from omniscribe.plugins.runtime import RuntimeService
from omniscribe.plugins.translate.routes import build_translate_router
from omniscribe.plugins.translate.service import (
    TranslationService,
    TranslationServiceImpl,
)


class TranslateSchema(BaseModel):
    """No configurable fields."""


class TranslatePlugin(Plugin):
    """Client-frozen translation surface: sync, async (JobQueue), NLLB."""

    Schema = TranslateSchema

    async def apply(self, ctx: Context) -> None:
        queue = ctx.inject(JobQueue)
        store = ctx.inject(ArtifactStore)
        runtime = ctx.inject(RuntimeService)
        service = TranslationServiceImpl(runtime.settings, queue, store)
        ctx.service(TranslationService, service)
        ctx.service(TranslationJobRunner, service.run_translate_job)
        ctx.mount_router(build_translate_router(service))


plugin = TranslatePlugin()
