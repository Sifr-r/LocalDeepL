"""EffectScope — group reversible effects under a single disposer.

The :class:`EffectScope` wraps an :class:`ExitStack` so a plugin can register
multiple effects and dispose them all at once. The :class:`PluginContext` uses
one internal :class:`EffectScope` for its own bookkeeping; this public class
is available for plugins that want to group their own effects.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack

# A disposer is a zero-arg callable that unwinds a single effect.
Disposer = Callable[[], None]


class EffectScope:
    """Group multiple effects under one disposer.

    Effects are registered in mount order and disposed in reverse mount
    order (LIFO), which matches the convention for resource teardown.

    Example::

        scope = EffectScope()
        scope.effect(lambda: print("cleanup A"))
        scope.effect(lambda: print("cleanup B"))
        scope.dispose()
        # prints "cleanup B" then "cleanup A"
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._closed = False

    @property
    def closed(self) -> bool:
        """True after :meth:`dispose` has been called."""
        return self._closed

    def effect(self, disposer: Disposer) -> Disposer:
        """Register an effect and return a self-consuming disposer.

        The returned disposer is the *only* safe way to unwind the effect
        early. When called, it invokes ``disposer`` exactly once and
        removes the effect from the scope so a subsequent
        :meth:`dispose` call does not fire it a second time. This
        matches the Cordis convention: every effect is unwound at
        most once across the scope's lifetime.

        Calling :meth:`dispose` unwinds every effect in the
        reverse order they were registered.
        """
        if self._closed:
            raise RuntimeError("EffectScope is closed; cannot register new effects.")
        if not callable(disposer):
            raise TypeError(
                f"Effect disposer must be callable, got {type(disposer).__name__}"
            )

        # The per-effect disposer. A flag protects against double-fire if
        # the caller invokes the returned disposer and the scope also
        # disposes (e.g. on context teardown).
        fired = False

        def scoped() -> None:
            nonlocal fired
            if fired:
                return
            fired = True
            disposer()

        # ExitStack needs a callback to call on close. The callback must
        # not raise (ExitStack suppresses callbacks after the first
        # exception), so we wrap ``scoped`` in a try/except.
        self._stack.callback(scoped)
        return scoped

    def dispose(self) -> None:
        """Unwind every registered effect in LIFO order.

        Idempotent: subsequent calls are no-ops.
        """
        if self._closed:
            return
        self._stack.close()
        self._closed = True
