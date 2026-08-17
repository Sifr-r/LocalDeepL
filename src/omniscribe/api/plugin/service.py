"""Service definitions and plugin protocol.

A :class:`ServiceDefinition` is a :class:`Protocol` subclass that declares
the surface a service must implement. The Protocol class itself is the
registry key — :meth:`PluginContext.register` keys on ``(Protocol, name)``.

A :class:`Plugin` is a callable that mounts capabilities into a
:class:`PluginContext` and returns a disposer that unwinds every
registration it performed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from omniscribe.api.plugin.context import PluginContext


@runtime_checkable
class ServiceDefinition(Protocol):
    """Marker Protocol for a service interface.

    Subclass this with the methods/attributes the service exposes. The
    subclass itself becomes the registry key; implementations are checked
    structurally at registration time via ``isinstance(impl, ServiceDefinition)``.

    Example::

        class ConnectionManagerLike(Protocol):
            def send_progress(self, channel_id: str, percent: float) -> None: ...

        ctx.register(ConnectionManagerLike, my_manager, name="default")
        mgr = ctx.get(ConnectionManagerLike)
    """

    # Intentionally empty. Subclasses add the actual surface.
    pass


@runtime_checkable
class Plugin(Protocol):
    """A plugin is a callable that mounts capabilities into a :class:`PluginContext`.

    A plugin returns a disposer (a zero-arg callable) that unwinds every
    registration it performed — services, listeners, and effects. The
    :class:`PluginContext` calls the disposer when the plugin is unmounted
    or when the context itself is disposed.

    Example::

        def my_plugin(ctx: PluginContext) -> Callable[[], None]:
            unregister_service = ctx.register(MyService, my_impl, name="default")
            unregister_listener = ctx.on("app:ready", my_listener)
            def dispose() -> None:
                unregister_listener()
                unregister_service()
            return dispose
    """

    def __call__(self, ctx: PluginContext) -> Callable[[], None]: ...
