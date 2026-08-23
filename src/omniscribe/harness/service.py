"""Service Protocol marker for type-driven dependency injection.

Services are looked up by their ``typing.Protocol`` type. Concrete
implementations are plain classes; the marker exists purely so DI keys have
a common base and so ad-hoc Protocols can be built at runtime.
"""

from __future__ import annotations

import types
from typing import Any, Protocol, cast, runtime_checkable


@runtime_checkable
class Service(Protocol):
    """Marker Protocol — every DI key conceptually extends this."""

    ...


def service_protocol(name: str, methods: tuple[str, ...]) -> type:
    """Build a runtime-checkable Protocol class with stub ``methods``.

    The returned class can be used as a DI key and supports ``isinstance``
    checks against duck-typed implementations.
    """

    def _exec_body(namespace: dict[str, Any]) -> None:
        namespace["__annotations__"] = {}
        namespace["__doc__"] = f"Runtime-built service Protocol {name!r}."
        for method in methods:

            def _stub(self: Any, *args: Any, **kwargs: Any) -> Any:
                raise NotImplementedError

            _stub.__name__ = method
            namespace[method] = _stub

    bases = cast("tuple[type, ...]", (Protocol,))
    protocol_cls = types.new_class(name, bases, exec_body=_exec_body)
    return runtime_checkable(protocol_cls)
