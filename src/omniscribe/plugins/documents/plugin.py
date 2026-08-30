"""Documents plugin — mounts extraction + export routes."""

from __future__ import annotations

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.documents.routes import build_documents_router


class DocumentsSchema(BaseModel):
    """No configurable fields."""


class DocumentsPlugin(Plugin):
    """Extraction + export routes over the token-bound ArtifactStore."""

    Schema = DocumentsSchema

    async def apply(self, ctx: Context) -> None:
        ctx.mount_router(build_documents_router(ctx))


plugin = DocumentsPlugin()
