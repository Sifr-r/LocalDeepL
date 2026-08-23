"""Effect tracking and scoped cleanup for the plugin harness.

``EffectRef`` is the registration handle returned by every ``Context``
registration; ``EffectScope`` collects cleanups and runs them in LIFO order.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

Cleanup = Callable[[], Awaitable[None] | None]

_effect_counter = itertools.count(1)


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

    @property
    def closed(self) -> bool:
        return self._closed

    def add(self, cleanup: Cleanup) -> None:
        """Register ``cleanup`` to run on close (LIFO)."""
        if self._closed:
            raise RuntimeError("effect scope is closed; cannot add cleanup")
        self._cleanups.append(cleanup)

    async def aclose(self) -> None:
        """Run every pending cleanup from last to first. Idempotent."""
        if self._closed:
            return
        self._closed = True
        while self._cleanups:
            cleanup = self._cleanups.pop()
            result = cleanup()
            if result is not None:
                await result


@asynccontextmanager
async def effect_scope() -> AsyncIterator[EffectScope]:
    """Async context manager that closes the scope on exit."""
    scope = EffectScope()
    try:
        yield scope
    finally:
        await scope.aclose()
