"""Exception types for the plugin context.

Every error raised by the :class:`~omniscribe.api.plugin.context.PluginContext`
is a subclass of :class:`PluginError` so callers can catch the whole family
with a single ``except`` clause.
"""

from __future__ import annotations


class PluginError(Exception):
    """Base class for every error raised by the plugin context."""


class ServiceAlreadyRegisteredError(PluginError):
    """Raised by :meth:`PluginContext.register` when the same service key
    (Protocol + name) is registered twice without ``replace=True``.

    Carries the original error message from the underlying implementation
    plus the conflicting key for diagnostics.
    """

    def __init__(self, definition: type, name: str) -> None:
        self.definition = definition
        self.name = name
        super().__init__(
            f"Service {definition.__name__!r} with name={name!r} is already "
            f"registered. Pass replace=True to override."
        )


class ServiceNotFoundError(PluginError):
    """Raised by :meth:`PluginContext.get` when no implementation exists
    for the requested (Protocol, name) key.
    """

    def __init__(self, definition: type, name: str) -> None:
        self.definition = definition
        self.name = name
        super().__init__(
            f"No service implementation found for {definition.__name__!r} "
            f"with name={name!r}. Did you forget to register it?"
        )


class ContextDisposedError(PluginError):
    """Raised when an operation is attempted on a disposed :class:`PluginContext`.

    Once :meth:`PluginContext.dispose` is called the context is final: all
    registrations, listeners, and effects have been unwound. Any further
    interaction is a programming error.
    """

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"Cannot perform {operation!r} on a disposed PluginContext.")


class EventModeMismatchError(PluginError):
    """Raised by a waterfall dispatch when a listener for the event is
    registered with a non-waterfall mode, or when a non-waterfall listener
    appears in a waterfall chain.
    """

    def __init__(self, event: str, expected: str, got: str) -> None:
        self.event = event
        self.expected = expected
        self.got = got
        super().__init__(
            f"Listener mode mismatch for event {event!r}: expected "
            f"{expected!r}, got {got!r}."
        )
