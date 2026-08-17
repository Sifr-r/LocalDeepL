"""Service registry behavior: register / get / has / unregister / require."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from omniscribe.api.plugin import (
    PluginContext,
    ServiceAlreadyRegisteredError,
    ServiceDefinition,
    ServiceNotFoundError,
)

# -- Test fixtures: a couple of protocols + implementations ------------------


@runtime_checkable
class Greeter(Protocol):
    def greet(self, name: str) -> str: ...


class FriendlyGreeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


class FormalGreeter:
    def greet(self, name: str) -> str:
        return f"Good day, {name}."


@runtime_checkable
class Counter(Protocol):
    def increment(self) -> int: ...


class AtomicCounter:
    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> int:
        self.value += 1
        return self.value


# -- Tests ------------------------------------------------------------------


def test_register_and_get_a_service() -> None:
    ctx = PluginContext("test")
    impl = FriendlyGreeter()
    ctx.register(Greeter, impl)
    assert ctx.get(Greeter) is impl


def test_has_returns_true_after_register_false_before() -> None:
    ctx = PluginContext("test")
    assert ctx.has(Greeter) is False
    ctx.register(Greeter, FriendlyGreeter())
    assert ctx.has(Greeter) is True


def test_get_unknown_service_raises_with_diagnostics() -> None:
    ctx = PluginContext("test")
    with pytest.raises(ServiceNotFoundError) as excinfo:
        ctx.get(Greeter)
    assert excinfo.value.definition is Greeter
    assert excinfo.value.name == "default"
    assert "Greeter" in str(excinfo.value)


def test_register_duplicate_raises() -> None:
    ctx = PluginContext("test")
    ctx.register(Greeter, FriendlyGreeter())
    with pytest.raises(ServiceAlreadyRegisteredError) as excinfo:
        ctx.register(Greeter, FormalGreeter())
    assert excinfo.value.definition is Greeter
    assert excinfo.value.name == "default"


def test_register_with_replace_overrides_silently() -> None:
    ctx = PluginContext("test")
    original = FriendlyGreeter()
    replacement = FormalGreeter()
    ctx.register(Greeter, original)
    ctx.register(Greeter, replacement, replace=True)
    assert ctx.get(Greeter) is replacement


def test_multiple_named_implementations_of_the_same_protocol() -> None:
    ctx = PluginContext("test")
    local = FriendlyGreeter()
    cloud = FormalGreeter()
    ctx.register(Greeter, local, name="local")
    ctx.register(Greeter, cloud, name="cloud")
    assert ctx.get(Greeter, name="local") is local
    assert ctx.get(Greeter, name="cloud") is cloud
    assert ctx.service_names(Greeter) == ["local", "cloud"]


def test_registered_disposer_unregisters() -> None:
    ctx = PluginContext("test")
    impl = FriendlyGreeter()
    dispose = ctx.register(Greeter, impl)
    assert ctx.has(Greeter) is True
    dispose()
    assert ctx.has(Greeter) is False
    with pytest.raises(ServiceNotFoundError):
        ctx.get(Greeter)


def test_register_rejects_non_structural_implementation() -> None:
    """A runtime_checkable Protocol enforces structural typing at register time."""

    class NotAGreeter:
        def not_greet(self) -> None:
            pass

    ctx = PluginContext("test")
    with pytest.raises(TypeError) as excinfo:
        ctx.register(Greeter, NotAGreeter())  # type: ignore[arg-type]
    assert "Greeter" in str(excinfo.value)


def test_unregister_returns_true_when_present_false_otherwise() -> None:
    ctx = PluginContext("test")
    assert ctx.unregister(Greeter) is False
    ctx.register(Greeter, FriendlyGreeter())
    assert ctx.unregister(Greeter) is True
    assert ctx.unregister(Greeter) is False


def test_require_passes_when_all_present_raises_when_missing() -> None:
    ctx = PluginContext("test")
    ctx.register(Greeter, FriendlyGreeter())
    ctx.register(Counter, AtomicCounter())
    # All present — no exception.
    ctx.require(Greeter, Counter)
    # Missing — raises for the first missing one.
    with pytest.raises(ServiceNotFoundError):
        ctx.require(Greeter, ServiceDefinition)


def test_register_with_empty_name_raises() -> None:
    ctx = PluginContext("test")
    with pytest.raises(ValueError):
        ctx.register(Greeter, FriendlyGreeter(), name="")  # type: ignore[arg-type]


def test_context_repr_includes_counts() -> None:
    ctx = PluginContext("demo")
    assert "demo" in repr(ctx)
    assert "services=0" in repr(ctx)
    ctx.register(Greeter, FriendlyGreeter())
    assert "services=1" in repr(ctx)
