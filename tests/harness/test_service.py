"""Service Protocol marker (runtime-checkable)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from omniscribe.harness.service import Service


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
