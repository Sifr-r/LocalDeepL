"""The shared harness container: services, typed events, reversible effects.

One ``Context`` exists per app process. Every registration returns an
``EffectRef`` attributed to the plugin id currently being applied (resolved
through a ``contextvars.ContextVar`` set by :meth:`Context.plugin`), so
``unload`` can reverse exactly that plugin's registrations in LIFO order.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from omniscribe.harness.effects import Cleanup, EffectRef, EffectScope, effect_scope
from omniscribe.harness.errors import ContextDisposedError, ServiceNotFoundError
from omniscribe.harness.events import Event

_LOGGER = logging.getLogger("omniscribe.harness")

EventHandler = Callable[[Event], Awaitable[None] | None]

_current_plugin_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "omniscribe_harness_plugin_id", default=None
)

ROOT_PLUGIN_ID = "<root>"


class Context:
    """Shared mutable container wiring services, events, effects, and routers."""

    def __init__(self) -> None:
        self._services: dict[type, Any] = {}
        self._listeners: dict[type, list[EventHandler]] = {}
        self._effect_cleanups: dict[int, Cleanup] = {}
        self._routers: list[Any] = []
        self._plugin_order: list[str] = []
        self._plugin_instances: dict[str, Any] = {}
        self._plugin_effects: dict[str, list[EffectRef]] = {}
        self._root_effects: list[EffectRef] = []
        self._disposed = False

    # -- internals ----------------------------------------------------------

    @property
    def disposed(self) -> bool:
        return self._disposed

    def _check_not_disposed(self, operation: str) -> None:
        if self._disposed:
            raise ContextDisposedError(operation)

    def _track(self, ref: EffectRef) -> EffectRef:
        bucket = self._plugin_effects.get(ref.plugin_id)
        if bucket is not None:
            bucket.append(ref)
        else:
            self._root_effects.append(ref)
        return ref

    def _current_plugin(self) -> str:
        return _current_plugin_id.get() or ROOT_PLUGIN_ID

    # -- services -----------------------------------------------------------

    def service(self, protocol: type, instance: Any) -> EffectRef:
        """Register ``instance`` under ``protocol``; duplicate keys fail loud."""
        self._check_not_disposed("register service")
        if protocol in self._services:
            raise ValueError(
                f"service already registered for protocol {protocol.__name__!r}"
            )
        self._services[protocol] = instance
        ref = EffectRef(plugin_id=self._current_plugin(), kind="service", key=protocol)
        return self._track(ref)

    def inject(self, protocol: type) -> Any:
        """Return the instance registered for ``protocol`` or raise."""
        if protocol not in self._services:
            raise ServiceNotFoundError(protocol.__name__)
        return cast(Any, self._services[protocol])

    def has(self, protocol: type) -> bool:
        return protocol in self._services

    # -- events -------------------------------------------------------------

    def on(self, event_type: type[Event], handler: EventHandler) -> EffectRef:
        """Subscribe ``handler`` to the exact ``event_type``."""
        self._check_not_disposed("subscribe event handler")
        self._listeners.setdefault(event_type, []).append(handler)
        ref = EffectRef(
            plugin_id=self._current_plugin(),
            kind="listener",
            key=(event_type, handler),
        )
        return self._track(ref)

    async def emit(self, event: Event) -> None:
        """Dispatch ``event`` to exact-type listeners concurrently.

        A raising listener is logged but never breaks the other handlers.
        """
        handlers = list(self._listeners.get(type(event), ()))
        if not handlers:
            return

        async def _run(handler: EventHandler) -> None:
            result = handler(event)
            if result is not None:
                await result

        results = await asyncio.gather(
            *(_run(handler) for handler in handlers), return_exceptions=True
        )
        for handler, result in zip(handlers, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.exception(
                    "event handler %r failed for %s",
                    handler,
                    type(event).__name__,
                    exc_info=result,
                )

    # -- effects ------------------------------------------------------------

    def effect(self, cleanup: Cleanup) -> EffectRef:
        """Register a cleanup that runs (in LIFO) when the owner unloads."""
        self._check_not_disposed("register effect")
        ref = EffectRef(plugin_id=self._current_plugin(), kind="effect", key=cleanup)
        self._effect_cleanups[ref._id] = cleanup
        return self._track(ref)

    @asynccontextmanager
    async def effect_scope(self) -> AsyncIterator[EffectScope]:
        """Scoped cleanup lifetime; cleanups run on block exit."""
        async with effect_scope() as scope:
            yield scope

    # -- routers ------------------------------------------------------------

    def mount_router(self, router: Any) -> EffectRef:
        """Queue ``router`` for inclusion by the server after harness load."""
        self._check_not_disposed("mount router")
        self._routers.append(router)
        ref = EffectRef(plugin_id=self._current_plugin(), kind="router", key=router)
        return self._track(ref)

    def routes(self) -> list[Any]:
        """Snapshot of mounted routers in mount order."""
        return list(self._routers)

    # -- lifecycle ----------------------------------------------------------

    async def plugin(
        self, plugin: Any, *, config: dict[str, Any] | None = None
    ) -> None:
        """Apply ``plugin`` with ``config``, attributing its registrations."""
        self._check_not_disposed("mount plugin")
        plugin_id = plugin.id or type(plugin).__name__
        plugin.id = plugin_id
        plugin.config = dict(config or {})
        if plugin_id in self._plugin_instances:
            raise ValueError(f"plugin {plugin_id!r} is already mounted")
        self._plugin_instances[plugin_id] = plugin
        self._plugin_order.append(plugin_id)
        self._plugin_effects[plugin_id] = []
        token = _current_plugin_id.set(plugin_id)
        try:
            await plugin.apply(self)
        except Exception:
            # A failed apply leaves no half-mounted plugin behind.
            self._plugin_order.remove(plugin_id)
            self._plugin_instances.pop(plugin_id, None)
            refs = self._plugin_effects.pop(plugin_id, [])
            for ref in reversed(refs):
                await self._reverse(ref)
            raise
        finally:
            _current_plugin_id.reset(token)

    async def unload(self, plugin_id: str) -> None:
        """Reverse every registration the plugin made, in LIFO order."""
        refs = self._plugin_effects.pop(plugin_id, [])
        for ref in reversed(refs):
            await self._reverse(ref)
        if plugin_id in self._plugin_order:
            self._plugin_order.remove(plugin_id)
        instance = self._plugin_instances.pop(plugin_id, None)
        if instance is not None:
            await instance.dispose()

    async def dispose(self) -> None:
        """Unload every plugin in reverse mount order, then clear the rest."""
        if self._disposed:
            return
        for plugin_id in reversed(list(self._plugin_order)):
            await self.unload(plugin_id)
        for ref in reversed(self._root_effects):
            await self._reverse(ref)
        self._services.clear()
        self._listeners.clear()
        self._routers.clear()
        self._disposed = True

    async def _reverse(self, ref: EffectRef) -> None:
        if ref.kind == "service":
            self._services.pop(ref.key, None)
        elif ref.kind == "listener":
            event_type, handler = ref.key
            handlers = self._listeners.get(event_type)
            if handlers and handler in handlers:
                handlers.remove(handler)
                if not handlers:
                    del self._listeners[event_type]
        elif ref.kind == "effect":
            cleanup = self._effect_cleanups.pop(ref._id, None)
            if cleanup is not None:
                result = cleanup()
                if result is not None:
                    await result
        elif ref.kind == "router" and ref.key in self._routers:
            self._routers.remove(ref.key)
