"""Glossary plugin — mounts glossary routes over LexiconProvider + JobQueue."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.glossary.routes import build_glossary_router
from omniscribe.plugins.glossary.service import (
    GlossaryImportService,
    GlossaryImportServiceImpl,
)
from omniscribe.plugins.glossary.store import LexiconProvider
from omniscribe.plugins.jobs import GlossaryJobRunner, JobQueue
from omniscribe.plugins.runtime import RuntimeService


class GlossarySchema(BaseModel):
    """No configurable fields."""


class GlossaryPlugin(Plugin):
    """Client-frozen glossary surface: dual-shape imports + library."""

    Schema = GlossarySchema

    async def apply(self, ctx: Context) -> None:
        queue = ctx.inject(JobQueue)
        runtime = ctx.inject(RuntimeService)
        provider = LexiconProvider(
            store_path=runtime.settings.artifact_directory / "lexicon.lance"
        )
        service = GlossaryImportServiceImpl(store_provider=provider.get, queue=queue)
        ctx.service(GlossaryImportService, service)
        ctx.service(GlossaryJobRunner, service.run_import_job)
        ctx.mount_router(build_glossary_router(service))


plugin = GlossaryPlugin()
