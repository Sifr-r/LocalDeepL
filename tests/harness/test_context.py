"""Context: services, events, effects, routers, and plugin lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from omniscribe.harness.context import Context
from omniscribe.harness.errors import ContextDisposedError, ServiceNotFoundError
from omniscribe.harness.events import Event, SessionEvent
from omniscribe.harness.plugin import Plugin


class SvcA(Protocol):
    def value(self) -> str: ...


class SvcB(Protocol):
    def value(self) -> str: ...


class _ImplA:
    def value(self) -> str:
        return "a"


class _ImplB:
    def value(self) -> str:
        return "b"


# -- services -----------------------------------------------------------------


async def test_service_inject_roundtrip() -> None:
    ctx = Context()
    impl = _ImplA()
    ctx.service(SvcA, impl)
    assert ctx.inject(SvcA) is impl
    assert ctx.has(SvcA)
    assert not ctx.has(SvcB)
    await ctx.dispose()


async def test_inject_unregistered_raises_with_protocol_name() -> None:
    ctx = Context()
    with pytest.raises(ServiceNotFoundError) as excinfo:
        ctx.inject(SvcA)
    assert excinfo.value.protocol_name == "SvcA"
    await ctx.dispose()


async def test_duplicate_service_registration_raises() -> None:
    ctx = Context()
    ctx.service(SvcA, _ImplA())
    with pytest.raises(ValueError):
        ctx.service(SvcA, _ImplA())
    await ctx.dispose()


async def test_service_after_dispose_raises() -> None:
    ctx = Context()
    await ctx.dispose()
    with pytest.raises(ContextDisposedError):
        ctx.service(SvcA, _ImplA())


# -- events -------------------------------------------------------------------


@dataclass(frozen=True)
class Ping(Event):
    n: int = 0


@dataclass(frozen=True)
class PingChild(Ping):
    pass


@dataclass(frozen=True)
class Logged(SessionEvent):
    tag: str = ""


async def test_on_emit_invokes_handler() -> None:
    ctx = Context()
    seen: list[Ping] = []
    ctx.on(Ping, lambda ev: seen.append(ev))
    await ctx.emit(Ping(3))
    assert seen == [Ping(3)]
    await ctx.dispose()


async def test_emit_matches_exact_type_only() -> None:
    ctx = Context()
    base_seen: list[Event] = []
    ctx.on(Ping, lambda ev: base_seen.append(ev))
    await ctx.emit(PingChild(1))
    assert base_seen == []
    await ctx.dispose()


async def test_two_handlers_run_concurrently() -> None:
    import asyncio

    ctx = Context()
    order: list[str] = []

    async def slow(_ev: Event) -> None:
        order.append("slow-start")
        await asyncio.sleep(0.02)
        order.append("slow-end")

    async def fast(_ev: Event) -> None:
        await asyncio.sleep(0.01)
        order.append("fast")

    ctx.on(Ping, slow)
    ctx.on(Ping, fast)
    await ctx.emit(Ping())
    # Concurrent dispatch lets `fast` finish before `slow` completes.
    assert order == ["slow-start", "fast", "slow-end"]
    await ctx.dispose()


async def test_raising_handler_does_not_break_others() -> None:
    ctx = Context()
    seen: list[bool] = []

    def bad(_ev: Event) -> None:
        raise RuntimeError("boom")

    ctx.on(Ping, bad)
    ctx.on(Ping, lambda _ev: seen.append(True))
    await ctx.emit(Ping())
    assert seen == [True]
    await ctx.dispose()


# -- effects + routers ----------------------------------------------------------


async def test_effect_cleanups_run_lifo_on_dispose() -> None:
    ctx = Context()
    order: list[str] = []
    ctx.effect(lambda: order.append("one"))
    ctx.effect(lambda: order.append("two"))
    await ctx.dispose()
    assert order == ["two", "one"]


async def test_mount_router_and_routes_order() -> None:
    ctx = Context()
    r1, r2 = object(), object()
    ctx.mount_router(r1)
    ctx.mount_router(r2)
    assert ctx.routes() == [r1, r2]
    await ctx.dispose()


async def test_registration_after_dispose_raises() -> None:
    ctx = Context()
    await ctx.dispose()
    with pytest.raises(ContextDisposedError):
        ctx.on(Ping, lambda _ev: None)
    with pytest.raises(ContextDisposedError):
        ctx.effect(lambda: None)
    with pytest.raises(ContextDisposedError):
        ctx.mount_router(object())


# -- plugin lifecycle -----------------------------------------------------------


class _PluginA(Plugin):
    id = "a"

    def __init__(self) -> None:
        self.applied_with: Context | None = None
        self.disposed = False
        self.owner_at_registration: str | None = None

    async def apply(self, ctx: Context) -> None:
        self.applied_with = ctx
        ref = ctx.service(SvcA, _ImplA())
        self.owner_at_registration = ref.plugin_id
        ctx.effect(lambda: None)

    async def dispose(self) -> None:
        self.disposed = True


class _PluginB(Plugin):
    id = "b"

    async def apply(self, ctx: Context) -> None:
        ctx.service(SvcB, _ImplB())


async def test_plugin_apply_sets_config_and_attributes() -> None:
    ctx = Context()
    plug = _PluginA()
    await ctx.plugin(plug, config={"k": 1})
    assert plug.config == {"k": 1}
    assert plug.applied_with is ctx
    assert plug.owner_at_registration == "a"
    assert ctx.inject(SvcA).value() == "a"
    await ctx.dispose()
    assert plug.disposed


async def test_unload_removes_only_that_plugins_registrations() -> None:
    ctx = Context()
    a, b = _PluginA(), _PluginB()
    await ctx.plugin(a)
    await ctx.plugin(b)
    await ctx.unload("a")
    assert not ctx.has(SvcA)
    assert ctx.has(SvcB)
    assert a.disposed
    await ctx.dispose()


async def test_unload_runs_effects_lifo() -> None:
    ctx = Context()
    order: list[str] = []

    class _OrderPlug(Plugin):
        id = "ordered"

        async def apply(self, inner_ctx: Context) -> None:
            inner_ctx.effect(lambda: order.append("first"))
            inner_ctx.effect(lambda: order.append("second"))

    await ctx.plugin(_OrderPlug())
    await ctx.unload("ordered")
    assert order == ["second", "first"]
    await ctx.dispose()


async def test_dispose_unloads_every_plugin_reverse_order() -> None:
    ctx = Context()
    events: list[str] = []

    class _TrackPlug(Plugin):
        def __init__(self, plug_id: str) -> None:
            self.id = plug_id

        async def dispose(self) -> None:
            events.append(self.id)

    await ctx.plugin(_TrackPlug("first"))
    await ctx.plugin(_TrackPlug("second"))
    await ctx.dispose()
    assert events == ["second", "first"]
    assert ctx.disposed


async def test_second_dispose_is_noop() -> None:
    ctx = Context()
    calls = 0

    class _CountPlug(Plugin):
        id = "counted"

        async def dispose(self) -> None:
            nonlocal calls
            calls += 1

    await ctx.plugin(_CountPlug())
    await ctx.dispose()
    await ctx.dispose()
    assert calls == 1


async def test_failed_apply_reverses_partial_registrations() -> None:
    ctx = Context()

    class _BadPlug(Plugin):
        id = "bad"

        async def apply(self, inner_ctx: Context) -> None:
            inner_ctx.service(SvcA, _ImplA())
            raise RuntimeError("explode")

    with pytest.raises(RuntimeError, match="explode"):
        await ctx.plugin(_BadPlug())
    assert not ctx.has(SvcA)
    await ctx.dispose()
