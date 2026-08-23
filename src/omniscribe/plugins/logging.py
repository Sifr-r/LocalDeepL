"""Logging plugin — configures structured logging from its row config.

Side-effect plugin: registers no service. The loader validates ``format`` and
``level`` against the Schema before ``apply`` runs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin
from omniscribe.utils.structured_logging import configure_logging


class LoggingSchema(BaseModel):
    format: Literal["text", "json"] = "text"
    level: str = "INFO"


class LoggingPlugin(Plugin):
    Schema = LoggingSchema

    async def apply(self, ctx: Context) -> None:
        cfg = LoggingSchema(**self.config)
        configure_logging(level=cfg.level, fmt=cfg.format)


plugin = LoggingPlugin()
