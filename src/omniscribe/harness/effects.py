"""Effect tracking and scoped cleanup for the plugin harness.

``EffectRef`` is the registration handle returned by every ``Context``
registration; ``EffectScope`` collects cleanups and runs them in LIFO order.
"""

from __future__ import annotations

import itertools
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

Cleanup = Callable[[], Awaitable[None] | None]

# Pedantic 9.2: the module-level counter was process-global and never
# reset, so two ``Context`` instances in the same process shared an id
# space. Production code (``Context.service``, ``Context.effect``,
# etc.) now passes its own per-context counter via the ``_id=`` kwarg;
# this module-level default is kept for the standalone
# ``EffectRef(...)`` test path that does not have a Context.
_effect_counter = itertools.count(1)

_LOGGER = logging.getLogger("omniscribe.harness")


@dataclass(frozen=True)
class EffectRef:
    """Handle describing one reversible registration."""

    plugin_id: str
    kind: str
    key: Any
    _id: int = field(default_factory=lambda: next(_effect_counter), repr=False)


class EffectScope:
    """Collects cleanups and runs them in reverse registration order."""

    def __init__(self) -> None:
        self._cleanups: list[Cleanup] = []
        self._closed = False
        # Pedantic 9.4: ``add`` is sync and may be called from any
        # thread that holds the scope (e.g. a plugin ``apply`` running
        # in a worker thread). Guard the list mutation so concurrent
        # ``add``s don't corrupt the LIFO ordering.
        self._lock = threading.Lock()

    @property
    def closed(self) -> bool:
        return self._closed

    def add(self, cleanup: Cleanup) -> None:
        """Register ``cleanup`` to run on close (LIFO)."""
        with self._lock:
            if self._closed:
                raise RuntimeError("effect scope is closed; cannot add cleanup")
            self._cleanups.append(cleanup)

    async def aclose(self) -> None:
        """Run every pending cleanup from last to first. Idempotent.

        Pedantic 9.3: a single failing cleanup no longer abandons the
        remaining ones. Each cleanup is wrapped in try/except; a
        failure is logged at ERROR with the traceback and the loop
        continues so every registered effect gets a chance to run.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = list(reversed(self._cleanups))
        for cleanup in pending:
            try:
                result = cleanup()
            except Exception:
                _LOGGER.exception(
                    "effect cleanup raised; continuing with remaining cleanups"
                )
                continue
            if result is not None:
                try:
                    await result
                except Exception:
                    _LOGGER.exception(
                        "async effect cleanup raised; "
                        "continuing with remaining cleanups"
                    )


@asynccontextmanager
async def effect_scope() -> AsyncIterator[EffectScope]:
    """Async context manager that closes the scope on exit."""
    scope = EffectScope()
    try:
        yield scope
    finally:
        await scope.aclose()
