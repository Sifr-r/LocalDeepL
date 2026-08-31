"""Service Protocol marker for type-driven dependency injection.

Services are looked up by their ``typing.Protocol`` type. Concrete
implementations are plain classes; the marker exists purely so DI keys have
a common base.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Service(Protocol):
    """Marker Protocol — every DI key conceptually extends this."""

    ...
