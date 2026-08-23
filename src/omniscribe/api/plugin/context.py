"""PluginContext — a Cordis-inspired typed repository of services and events.

The :class:`PluginContext` is the "everything is a plugin" container. A
running OmniScribe server owns one :class:`PluginContext`; every capability
is registered as a service (Protocol + impl) or an event listener. Consumers
look up services by Protocol class instead of importing the concrete
implementation, which is what makes the seam replaceable.

Five things the context does
----------------------------

1. **Service registry** — :meth:`register` adds a (Protocol, name) -> impl
   entry; :meth:`get` looks one up; :meth:`has` checks; the returned
   disposer removes it. Multiple impls of the same Protocol can coexist
   under different names (e.g. ``JobQueue`` with ``"local"`` and ``"celery"``).

2. **Event listener registry** — :meth:`on` registers a listener under a
   named event with one of four :class:`EventMode` dispatch modes
   (``emit`` / ``waterfall`` / ``serial`` / ``parallel``).

3. **Event dispatch** — :meth:`emit`, :meth:`parallel`, :meth:`serial`,
   :meth:`waterfall` invoke the listeners for an event. Listeners that
   are not registered with the mode the dispatcher uses are skipped.

4. **Reversible effects** — :meth:`effect` registers a disposer that is
   called on :meth:`dispose`; :meth:`mount` does the same for a whole
   :class:`Plugin`.

5. **Teardown** — :meth:`dispose` unwinds every effect, listener, and
   service in reverse mount order. After dispose the context is final;
   any further operation raises :class:`ContextDisposedError`.

Thread safety
-------------

Every public method on this class is wrapped in a
``threading.RLock`` instance owned by the context. The lock is
acquired on entry and released on exit (re-entrant, so a listener
that calls :meth:`register` / :meth:`on` etc. from inside a dispatch
will not deadlock). Read-only methods are wrapped too so a
:meth:`has` / :meth:`service_names` snapshot is consistent across
concurrent mutations.

The intended pattern is still "mount during boot, dispatch during
request handling, dispose at shutdown" — the lock is for the rare
runtime-plugin-reload and the multi-worker-restart edge cases
where two threads briefly race on the registry.

**Why ``threading.RLock`` and not ``asyncio.Lock``:** every public
method on this class is sync. The :func:`_locked` decorator holds
the lock briefly without ``await``-ing. ``asyncio.Lock`` would
require making every method ``async``, which is gratuitous churn
for a class whose public methods are all sync today. **Revisit
this choice if a future method must ``await`` inside the critical
section** (e.g. a :meth:`register` that has to acquire a network
resource before completing).
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterable
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from omniscribe.api.plugin.errors import (
    ContextDisposedError,
    EventModeMismatchError,
    ServiceAlreadyRegisteredError,
    ServiceNotFoundError,
)
from omniscribe.api.plugin.events import EventMode, EventName

# A disposer is a zero-arg callable that unwinds a single effect.
Disposer = Callable[[], None]

_F = TypeVar("_F", bound=Callable[..., Any])


def _locked(method: _F) -> _F:
    """Decorator: serialize a :class:`PluginContext` method under the lock."""

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return cast(_F, wrapper)


@dataclass
class _ListenerEntry:
    """Internal record of a registered listener.

    The dataclass is used (not a tuple) so :meth:`list.remove` can match
    by identity, which is robust against duplicate callable objects.
    """

    mode: EventMode
    listener: Callable[..., Any]


# Type alias for the listener signature. The ``Any`` payloads reflect that
# Python lacks declaration merging — the type check happens at the call
# site (the listener's actual signature).
Listener = Callable[..., Any]


class PluginContext:
    """A typed repository of services and event listeners.

    Parameters
    ----------
    name:
        Human-readable name for diagnostics. Default ``"root"``. Nested
        contexts (created by a parent plugin) typically pass a dotted
        path like ``"root.web.ocr"``.
    """

    def __init__(self, name: str = "root") -> None:
        self._name = name
        # Re-entrant so a dispatch listener that calls back into a
        # mutation method does not deadlock.
        self._lock = threading.RLock()
        self._services: dict[tuple[type, str], Any] = {}
        self._listeners: dict[str, list[_ListenerEntry]] = {}
        self._effects: list[Disposer] = []
        self._disposed = False

    # -- Introspection ----------------------------------------------------

    @property
    def name(self) -> str:
        """Human-readable name for diagnostics."""
        return self._name

    @property
    @_locked
    def disposed(self) -> bool:
        """True after :meth:`dispose` has been called."""
        return self._disposed

    @_locked
    def __repr__(self) -> str:
        service_count = len(self._services)
        listener_count = sum(len(v) for v in self._listeners.values())
        return (
            f"PluginContext(name={self._name!r}, "
            f"services={service_count}, listeners={listener_count}, "
            f"disposed={self._disposed})"
        )

    # -- Service registry -------------------------------------------------

    @_locked
    def register(
        self,
        definition: type,
        impl: Any,
        *,
        name: str = "default",
        replace: bool = False,
    ) -> Disposer:
        """Register a service implementation.

        Parameters
        ----------
        definition:
            The :class:`Protocol` class that declares the service interface.
            Used as the registry key.
        impl:
            The implementation. Must structurally satisfy ``definition``;
            a duck-type check is performed via ``isinstance`` when
            ``definition`` is ``@runtime_checkable``.
        name:
            Slot name for multiple implementations of the same Protocol.
            Defaults to ``"default"``.
        replace:
            If True, an existing impl under the same key is silently
            replaced. If False (default), a duplicate raises
            :class:`ServiceAlreadyRegisteredError`.

        Returns
        -------
        A disposer that un-registers the service when called.
        """
        self._assert_not_disposed("register")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Service name must be a non-empty string, got {name!r}")
        # Best-effort structural check. The Protocol must be runtime_checkable
        # for isinstance() to do anything; if it isn't, the check passes
        # through and we rely on duck typing at the call site.
        if (
            hasattr(definition, "_is_runtime_protocol")
            and definition._is_runtime_protocol
            and not isinstance(impl, definition)
        ):
            raise TypeError(
                f"Implementation {type(impl).__name__!r} does not "
                f"satisfy the {definition.__name__!r} protocol."
            )
        key = (definition, name)
        if key in self._services and not replace:
            raise ServiceAlreadyRegisteredError(definition, name)
        self._services[key] = impl
        return self.effect(lambda: self._services.pop(key, None))

    @_locked
    def get(self, definition: type, *, name: str = "default") -> Any:
        """Fetch a registered service implementation.

        Raises :class:`ServiceNotFoundError` if no impl exists.
        """
        self._assert_not_disposed("get")
        key = (definition, name)
        try:
            return self._services[key]
        except KeyError:
            raise ServiceNotFoundError(definition, name) from None

    @_locked
    def has(self, definition: type, *, name: str = "default") -> bool:
        """True if an impl exists for the (Protocol, name) key."""
        return (definition, name) in self._services

    @_locked
    def unregister(self, definition: type, *, name: str = "default") -> bool:
        """Remove a service implementation. Returns True if it existed."""
        self._assert_not_disposed("unregister")
        return self._services.pop((definition, name), None) is not None

    @_locked
    def swap(
        self,
        definition: type,
        impl: Any,
        *,
        name: str = "default",
    ) -> Disposer:
        """Replace a service and return a disposer that restores the previous state.

        Unlike :meth:`register` (which raises on duplicate, or
        overwrites with a non-restoring disposer when ``replace=True``),
        :meth:`swap` snapshots whatever is currently registered for
        ``(definition, name)`` before installing ``impl`` and restores
        the snapshot on dispose.

        If nothing was previously registered, the disposer removes
        the swapped impl (same as :meth:`register`). The
        :class:`ServiceAlreadyRegisteredError` does NOT fire here —
        the whole point of ``swap`` is to overwrite cleanly.

        The structural isinstance check mirrors :meth:`register`: if
        the protocol is ``@runtime_checkable`` and the impl doesn't
        satisfy it, a :class:`TypeError` is raised before the swap.
        """
        self._assert_not_disposed("swap")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Service name must be a non-empty string, got {name!r}")
        if (
            hasattr(definition, "_is_runtime_protocol")
            and definition._is_runtime_protocol
            and not isinstance(impl, definition)
        ):
            raise TypeError(
                f"Implementation {type(impl).__name__!r} does not "
                f"satisfy the {definition.__name__!r} protocol."
            )
        key = (definition, name)
        previous = self._services.get(key)
        self._services[key] = impl

        def _restore() -> None:
            current = self._services.get(key)
            # Only restore if the current impl is the one we installed.
            # If the user later swapped or unregistered the patched impl,
            # we leave whatever they put there alone.
            if current is impl:
                if previous is None:
                    self._services.pop(key, None)
                else:
                    self._services[key] = previous

        return self.effect(_restore)

    @_locked
    def require(
        self,
        *definitions: type,
        name: str = "default",
    ) -> None:
        """Assert that every named definition is registered.

        Convenience for plugin boot: ``ctx.require(JobQueue, ProgressService)``
        raises :class:`ServiceNotFoundError` listing the first missing
        dependency if any are absent. Phase 0 does not block-wait; later
        phases may add an async ``require_async`` for the dynamic-mount case.
        """
        self._assert_not_disposed("require")
        for definition in definitions:
            if not self.has(definition, name=name):
                raise ServiceNotFoundError(definition, name)

    @_locked
    def service_names(self, definition: type) -> list[str]:
        """List every registered name for a given definition.

        Useful for diagnostics and for picking among multiple impls.
        """
        return [n for (d, n) in self._services if d is definition]

    # -- Event listener registry ------------------------------------------

    @_locked
    def on(
        self,
        event: str | EventName,
        listener: Listener,
        *,
        mode: str | EventMode = EventMode.EMIT,
        prepend: bool = False,
    ) -> Disposer:
        """Register an event listener and return its disposer.

        Parameters
        ----------
        event:
            Either a string event name or an :class:`EventName` constant.
        listener:
            The callable to invoke. Signature is mode-dependent; see the
            :meth:`emit` / :meth:`parallel` / :meth:`serial` / :meth:`waterfall`
            dispatchers for the expected shape.
        mode:
            One of :class:`EventMode`. Default ``emit`` (observe only).
        prepend:
            If True, the listener is registered *before* the existing
            listeners of the same event so it runs first. Default False
            (append).
        """
        self._assert_not_disposed("on")
        if not callable(listener):
            raise TypeError(f"Listener must be callable, got {type(listener).__name__}")
        event_mode = EventMode(mode) if not isinstance(mode, EventMode) else mode
        event_name = self._normalize_event_name(event)
        entry = _ListenerEntry(mode=event_mode, listener=listener)
        bucket = self._listeners.setdefault(event_name, [])
        if prepend:
            bucket.insert(0, entry)
        else:
            bucket.append(entry)
        return self.effect(lambda: self._remove_listener(event_name, entry))

    @_locked
    def off(self, event: str | EventName, listener: Listener) -> bool:
        """Remove a specific listener. Returns True if it was found."""
        self._assert_not_disposed("off")
        event_name = self._normalize_event_name(event)
        bucket = self._listeners.get(event_name, [])
        for entry in bucket:
            if entry.listener is listener:
                bucket.remove(entry)
                return True
        return False

    @_locked
    def _remove_listener(self, event_name: str, entry: _ListenerEntry) -> None:
        """Internal helper: remove a listener entry by identity. Used by the
        disposer returned by :meth:`on`."""
        bucket = self._listeners.get(event_name)
        if not bucket:
            return
        with suppress(ValueError):
            bucket.remove(entry)
        if not bucket:
            self._listeners.pop(event_name, None)

    @_locked
    def listeners(self, event: str | EventName) -> list[_ListenerEntry]:
        """Return a snapshot of registered listeners for an event (introspection)."""
        return list(self._listeners.get(self._normalize_event_name(event), ()))

    # -- Event dispatch ---------------------------------------------------

    @_locked
    def emit(self, event: str | EventName, **payload: Any) -> None:
        """Observe-only dispatch.

        All listeners registered with :attr:`EventMode.EMIT` run in
        registration order. Listeners with other modes are skipped.
        Return values (if any) are discarded.

        If a :class:`~omniscribe.api.plugin.SessionLog` is registered
        in this context, the event is also appended to the log as
        the very first step — so the session log is the canonical
        record of every emit. Use :meth:`emit_silent` to skip the
        log append (rare; mostly for internal log-draining
        notifications).

        Raises :class:`ContextDisposedError` if the context has been disposed.
        """
        self._assert_not_disposed("emit")
        self._maybe_log_event(event, payload)
        for entry in self._iter_listeners(event):
            if entry.mode is EventMode.EMIT:
                entry.listener(**payload)

    @_locked
    def parallel(self, event: str | EventName, **payload: Any) -> None:
        """Parallel dispatch.

        All listeners registered with :attr:`EventMode.PARALLEL` receive
        the same payload. Phase 0 runs them sequentially in registration
        order; a later phase will detect async listeners and schedule
        them with ``asyncio.gather``.

        Raises :class:`ContextDisposedError` if the context has been disposed.
        """
        self._assert_not_disposed("parallel")
        self._maybe_log_event(event, payload)
        for entry in self._iter_listeners(event):
            if entry.mode is EventMode.PARALLEL:
                entry.listener(**payload)

    @_locked
    def serial(
        self, event: str | EventName, initial: Any = None, **payload: Any
    ) -> Any:
        """Ordered dispatch.

        The first listener receives ``initial``; each subsequent listener
        receives the previous listener's return value. The chain's final
        return is the dispatch's return. Listeners not registered with
        :attr:`EventMode.SERIAL` are skipped.

        Raises :class:`ContextDisposedError` if the context has been disposed.
        """
        self._assert_not_disposed("serial")
        self._maybe_log_event(event, {"initial": initial, **payload})
        current = initial
        first = True
        for entry in self._iter_listeners(event):
            if entry.mode is not EventMode.SERIAL:
                continue
            if first:
                current = (
                    entry.listener(initial, **payload)
                    if payload
                    else entry.listener(initial)
                )
                first = False
            else:
                current = (
                    entry.listener(current, **payload)
                    if payload
                    else entry.listener(current)
                )
        return current

    @_locked
    def waterfall(
        self,
        event: str | EventName,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Around-middleware dispatch.

        The first listener receives the initial value as its first
        positional argument and a ``next`` keyword argument. Calling
        ``next(value)`` delegates to the next listener (optionally
        replacing the accumulated value). Returning without calling
        ``next`` short-circuits the chain and that value is the
        dispatch's return.

        All listeners in the chain must be registered with
        :attr:`EventMode.WATERFALL`; a non-waterfall listener in the
        chain raises :class:`EventModeMismatchError` when reached.

        If no listeners are registered, the first positional argument
        is returned (or ``None`` if no args were given).

        Raises :class:`ContextDisposedError` if the context has been disposed.
        """
        self._assert_not_disposed("waterfall")
        self._maybe_log_event(
            event,
            # ``waterfall`` carries its initial value positionally; the
            # log gets a flat payload with ``initial`` for traceability.
            {"initial": args[0] if args else None, **kwargs},
        )
        chain = list(self._iter_listeners(event))
        if not chain:
            return args[0] if len(args) == 1 else (args if args else None)

        initial = args[0] if args else None
        # Extra args/kwargs (besides initial and next) are forwarded to
        # every listener. This matches Cordis's around-middleware pattern.
        forwarded_kwargs = dict(kwargs)

        def build_next(idx: int) -> Callable[..., Any]:
            def next_(value: Any = _SENTINEL) -> Any:
                if idx >= len(chain):
                    return value if value is not _SENTINEL else initial
                entry = chain[idx]
                if entry.mode is not EventMode.WATERFALL:
                    raise EventModeMismatchError(
                        event=str(event), expected="waterfall", got=entry.mode.value
                    )
                # If the listener calls next() with no value, pass through the
                # current accumulated value.
                inner_next = build_next(idx + 1)
                forwarded = dict(forwarded_kwargs)
                forwarded["next"] = inner_next
                if value is _SENTINEL:
                    return entry.listener(initial, **forwarded)
                return entry.listener(value, **forwarded)

            return next_

        return build_next(0)()

    # -- Reversible effects -----------------------------------------------

    @_locked
    def effect(self, disposer: Disposer) -> Disposer:
        """Register a reversible effect and return its disposer.

        The effect is invoked during :meth:`dispose` (in LIFO order
        across all effects registered on this context, including
        effects added implicitly by :meth:`register` / :meth:`on`).
        """
        self._assert_not_disposed("effect")
        if not callable(disposer):
            raise TypeError(
                f"Effect disposer must be callable, got {type(disposer).__name__}"
            )
        fired = False

        def scoped() -> None:
            nonlocal fired
            if fired:
                return
            fired = True
            with suppress(Exception):
                disposer()

        self._effects.append(scoped)
        return scoped

    @_locked
    def mount(self, plugin: Any) -> Disposer:
        """Mount a :class:`Plugin` into this context.

        The plugin callable is invoked with ``self`` as its argument;
        the callable is expected to register services/listeners/effects
        via the context and return a top-level disposer that unwinds
        everything. The returned disposer is also registered with the
        context's effect list so it is called during :meth:`dispose`.
        """
        self._assert_not_disposed("mount")
        if not callable(plugin):
            raise TypeError(f"Plugin must be callable, got {type(plugin).__name__}")
        plugin_disposer = plugin(self)
        if not callable(plugin_disposer):
            raise TypeError(
                f"Plugin {plugin!r} must return a callable disposer, "
                f"got {type(plugin_disposer).__name__}"
            )
        return self.effect(plugin_disposer)

    # -- Teardown ---------------------------------------------------------

    @_locked
    def dispose(self) -> None:
        """Unwind every registered effect, listener, and service.

        Idempotent: a second call is a no-op. After dispose the context
        is final; any further operation raises
        :class:`ContextDisposedError`.
        """
        if self._disposed:
            return
        self._disposed = True
        # Unwind effects in LIFO order.
        while self._effects:
            effect_fn = self._effects.pop()
            with suppress(Exception):
                effect_fn()
        # Drop the registries so any accidental access after dispose is
        # caught by the disposed check rather than returning a stale ref.
        self._services.clear()
        self._listeners.clear()

    # -- Internal helpers -------------------------------------------------

    def _assert_not_disposed(self, operation: str) -> None:
        if self._disposed:
            raise ContextDisposedError(operation)

    def _iter_listeners(self, event: str | EventName) -> Iterable[_ListenerEntry]:
        return iter(self._listeners.get(self._normalize_event_name(event), ()))

    @staticmethod
    def _normalize_event_name(event: str | EventName) -> str:
        if isinstance(event, str):
            return event
        # NewType("EventName", str) — at runtime the value is a str.
        return str(event)

    @_locked
    def _maybe_log_event(self, event: str | EventName, payload: dict[str, Any]) -> None:
        """If a :class:`SessionLog` is registered, append this dispatch as a log event.

        Fan-out: when multiple :class:`SessionLog` providers are
        registered under different names (``"memory"``,
        ``"sqlite"``, etc.), every event is appended to every
        log. The canonical record is whatever the operator
        reads first; the fan-out is deliberate so a transient
        in-memory log does not lose events when a persistent
        one is added later.

        Lazy-imported so the import graph stays free of cycles
        (the context module is imported by ``session_log``'s
        dependencies).
        """
        # Cheap fast path: no services at all, no logs possible.
        if not self._services:
            return
        from omniscribe.api.plugin.seams import SessionLog

        # Find every (definition, name) key whose definition is
        # SessionLog. The cost is O(N registered services), but
        # in practice N is tiny (a handful of providers).
        log_keys = [key for key in self._services if key[0] is SessionLog]
        if not log_keys:
            return
        from omniscribe.api.plugin.session_log import LogEvent

        envelope = LogEvent(
            kind=self._normalize_event_name(event),
            # Deep-copy so a later mutation of the dispatcher's
            # local payload dict (including nested structures)
            # cannot affect the recorded event.
            payload=deepcopy(payload),
        )
        for definition, name in log_keys:
            self._services[(definition, name)].append(envelope)


# Sentinel used by waterfall() to distinguish "no value passed to next()"
# from "next() called with explicit None". Lives at module scope so the
# inner closure can reference it without capturing the outer frame.
_SENTINEL: Any = object()
