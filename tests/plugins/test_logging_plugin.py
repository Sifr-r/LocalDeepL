"""Logging plugin: side-effect configuration of structured logging."""

from __future__ import annotations

import pytest

from omniscribe.harness.context import Context
from omniscribe.plugins import logging as logging_plugin


async def test_logging_plugin_configures_structured_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_configure(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(logging_plugin, "configure_logging", _fake_configure)
    ctx = Context()
    await ctx.plugin(
        logging_plugin.LoggingPlugin(), config={"format": "json", "level": "DEBUG"}
    )
    assert calls == [{"level": "DEBUG", "fmt": "json"}]
    await ctx.dispose()


async def test_logging_plugin_defaults() -> None:
    plug = logging_plugin.LoggingPlugin()
    cfg = logging_plugin.LoggingSchema(**plug.config)
    assert cfg.format == "text"
    assert cfg.level == "INFO"


async def test_logging_plugin_registers_no_service() -> None:
    ctx = Context()
    await ctx.plugin(logging_plugin.LoggingPlugin(), config={})
    assert ctx.routes() == []
    await ctx.dispose()


async def test_bad_format_fails_schema() -> None:
    with pytest.raises(ValueError):
        logging_plugin.LoggingSchema(format="yaml")  # type: ignore[arg-type]
