"""Service Protocol marker and runtime Protocol builder."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from omniscribe.harness.service import Service, service_protocol


@runtime_checkable
class Greeter(Service, Protocol):
    def greet(self) -> str: ...


class _DuckGreeter:
    def greet(self) -> str:
        return "hello"


def test_service_protocol_subclass_matches_duck_typed_instance() -> None:
    assert isinstance(_DuckGreeter(), Greeter)


def test_service_marker_is_runtime_checkable() -> None:
    assert isinstance(object(), Service)  # marker has no members


def test_service_protocol_builds_named_protocol() -> None:
    Counter = service_protocol("Counter", ("increment", "value"))
    assert Counter.__name__ == "Counter"

    class _DuckCounter:
        def increment(self) -> None: ...
        def value(self) -> int:
            return 0

    assert isinstance(_DuckCounter(), Counter)
    assert not isinstance(object(), Counter)
