"""Plugin base class contract."""

from __future__ import annotations

from omniscribe.harness.context import Context
from omniscribe.harness.plugin import Plugin


def test_plugin_defaults() -> None:
    plug = Plugin()
    assert plug.id == ""
    assert plug.config == {}
    assert Plugin.Schema is None


async def test_default_apply_and_dispose_are_awaitable_noops() -> None:
    plug = Plugin()
    ctx = Context()
    await plug.apply(ctx)
    await plug.dispose()
    await ctx.dispose()


async def test_subclass_apply_receives_context() -> None:
    seen: list[Context] = []

    class _Sub(Plugin):
        id = "sub"

        async def apply(self, ctx: Context) -> None:
            seen.append(ctx)

    ctx = Context()
    await ctx.plugin(_Sub())
    assert seen == [ctx]
    await ctx.dispose()
