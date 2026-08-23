"""Event domain bases."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, fields

import pytest

from omniscribe.harness.events import AgentEvent, CapabilityEvent, Event, SessionEvent


def test_event_is_frozen_dataclass_base() -> None:
    assert hasattr(Event, "__dataclass_fields__")

    @dataclass(frozen=True)
    class Ping(Event):
        n: int = 0

    ping = Ping(1)
    with pytest.raises(FrozenInstanceError):
        ping.n = 2  # type: ignore[misc]


def test_domains_subclass_event_and_are_distinct() -> None:
    for domain in (SessionEvent, AgentEvent, CapabilityEvent):
        assert issubclass(domain, Event)
    assert len({SessionEvent, AgentEvent, CapabilityEvent}) == 3


def test_frozen_events_compare_by_value() -> None:
    @dataclass(frozen=True)
    class Marker(SessionEvent):
        tag: str = ""

    assert Marker("a") == Marker("a")
    assert Marker("a") != Marker("b")
    assert hash(Marker("a")) == hash(Marker("a"))
    assert {f.name for f in fields(Marker("a"))} == {"tag"}
