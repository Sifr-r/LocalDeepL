"""Event dispatch modes for the plugin context.

Cordis models events as typed names with one of four dispatch modes:

- ``emit`` — observe only; listeners run in registration order; no return value.
- ``waterfall`` — around-middleware; each listener receives a current value and
  a ``next`` callable; calling ``next()`` delegates (optionally with a replaced
  value); returning without ``next()`` short-circuits the chain.
- ``serial`` — ordered; each listener receives the previous listener's return
  value; the chain's final return is the dispatch's return.
- ``parallel`` — concurrent; all listeners run with the same payload; no
  return value. Phase 0 executes these sequentially; async concurrency is
  scheduled for a later phase.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NewType


class EventMode(StrEnum):
    """Dispatch mode for an event listener.

    A :class:`StrEnum` so values serialize cleanly to JSON when an
    event is recorded in a session log.
    """

    EMIT = "emit"
    """Observe-only dispatch. Listeners run in registration order. No return value."""

    WATERFALL = "waterfall"
    """Around-middleware dispatch. Each listener must call ``next()`` to delegate."""

    SERIAL = "serial"
    """Ordered dispatch. Each listener returns a value passed to the next."""

    PARALLEL = "parallel"
    """Concurrent dispatch. All listeners receive the same payload. No return."""


# An EventName is just a string at the type level. The :class:`Event` class
# in :mod:`omniscribe.api.plugin.context` accepts either a string or an
# ``EventName`` so callers can use either a literal or a typed constant.
EventName = NewType("EventName", str)
"""Type alias for an event name. Plain ``str`` at runtime; the type alias
makes intent explicit in function signatures."""
