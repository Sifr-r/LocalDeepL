"""Service registry behavior: register / get / has / unregister / require."""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

import pytest

from omniscribe.api.plugin import (
    ContextDisposedError,
    EventName,
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


# -- F27: thread safety ------------------------------------------------------


def test_concurrent_registration_with_unique_keys_is_safe() -> None:
    """Many threads register services under distinct (Protocol, name)
    pairs concurrently. The lock serialises the registrations so every
    entry lands in the registry; ``service_names`` returns the full set."""
    ctx = PluginContext("f27-unique")
    n_threads = 32
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def worker(idx: int) -> None:
        try:
            # All threads wait until everyone is ready, so the race is real.
            barrier.wait(timeout=5.0)
            ctx.register(Counter, AtomicCounter(), name=f"counter-{idx}")
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(i,), name=f"f27-{i}")
        for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    names = ctx.service_names(Counter)
    assert len(names) == n_threads
    assert set(names) == {f"counter-{i}" for i in range(n_threads)}
    # Every registered impl is retrievable (no torn writes).
    for i in range(n_threads):
        assert isinstance(ctx.get(Counter, name=f"counter-{i}"), AtomicCounter)


def test_concurrent_registration_with_the_same_key_serialises_errors() -> None:
    """Two threads race to register under the same (Protocol, name).
    Exactly one wins; the other gets :class:`ServiceAlreadyRegisteredError`
    — no torn writes, no double-registration, no silent overwrite."""
    ctx = PluginContext("f27-race")
    barrier = threading.Barrier(2)
    successes: list[int] = []
    failures: list[BaseException] = []

    def worker(idx: int, impl: object) -> None:
        try:
            barrier.wait(timeout=5.0)
            ctx.register(Counter, impl, name="shared")
            successes.append(idx)
        except BaseException as exc:
            failures.append(exc)

    a, b = AtomicCounter(), AtomicCounter()
    t1 = threading.Thread(target=worker, args=(1, a), name="race-a")
    t2 = threading.Thread(target=worker, args=(2, b), name="race-b")
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # Exactly one winner, exactly one loser.
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ServiceAlreadyRegisteredError)
    # The winner is whichever impl the registry now holds.
    assert ctx.get(Counter, name="shared") is (a if successes[0] == 1 else b)


def test_concurrent_dispatch_and_mutation_does_not_corrupt_registry() -> None:
    """While one thread emits an event repeatedly, another thread
    registers a listener under the same event. The lock ensures the
    dispatch snapshot is consistent (no :class:`RuntimeError` from
    mutating-during-iteration)."""
    ctx = PluginContext("f27-emit")
    received: list[str] = []
    stop = threading.Event()
    errors: list[BaseException] = []
    event_name: EventName = "race.event"  # type: ignore[assignment]

    def emitter() -> None:
        try:
            while not stop.is_set():
                ctx.emit(event_name, n=1)
        except BaseException as exc:
            errors.append(exc)

    def registrar() -> None:
        try:
            for _i in range(50):
                ctx.on(event_name, lambda *, n=1: received.append("x"), prepend=False)
        except BaseException as exc:
            errors.append(exc)

    t_emit = threading.Thread(target=emitter, name="emit")
    t_reg = threading.Thread(target=registrar, name="reg")
    t_emit.start()
    t_reg.start()
    t_reg.join()
    stop.set()
    t_emit.join()
    assert errors == [], f"Unexpected errors during concurrent emit/register: {errors}"


# -- Effects, mounting, and lifecycle ----------------------------------------


def test_context_effect_is_invoked_on_dispose() -> None:
    ctx = PluginContext("test")
    fired: list[str] = []
    ctx.effect(lambda: fired.append("ctx_effect"))
    ctx.dispose()
    assert fired == ["ctx_effect"]


def test_context_effect_returned_disposer_can_be_called_early() -> None:
    ctx = PluginContext("test")
    fired: list[str] = []
    disposer = ctx.effect(lambda: fired.append("only"))
    disposer()
    assert fired == ["only"]
    ctx.dispose()
    assert fired == ["only"]


def test_context_effect_disposes_in_lifo_order() -> None:
    ctx = PluginContext("test")
    order: list[str] = []
    ctx.effect(lambda: order.append("a"))
    ctx.effect(lambda: order.append("b"))
    ctx.effect(lambda: order.append("c"))
    ctx.dispose()
    assert order == ["c", "b", "a"]


def test_mount_invokes_plugin_and_disposes() -> None:
    ctx = PluginContext("test")
    seen_ctx: list[PluginContext] = []
    fired: list[str] = []

    def my_plugin(c: PluginContext):
        seen_ctx.append(c)
        c.register(Greeter, FriendlyGreeter())
        return lambda: fired.append("plugin_cleanup")

    unmount = ctx.mount(my_plugin)
    assert seen_ctx == [ctx]
    assert ctx.has(Greeter) is True
    unmount()
    assert fired == ["plugin_cleanup"]


def test_mount_rejects_non_callable_and_invalid_disposer() -> None:
    ctx = PluginContext("test")
    with pytest.raises(TypeError):
        ctx.mount("not a plugin")  # type: ignore[arg-type]

    def bad_plugin(c: PluginContext):
        return "not a disposer"  # type: ignore[return-value]

    with pytest.raises(TypeError):
        ctx.mount(bad_plugin)


def test_dispose_makes_operations_raise_and_is_idempotent() -> None:
    ctx = PluginContext("test")
    ctx.register(Greeter, FriendlyGreeter())
    assert ctx.disposed is False
    ctx.dispose()
    assert ctx.disposed is True

    # Idempotent
    ctx.dispose()
    assert ctx.disposed is True

    with pytest.raises(ContextDisposedError):
        ctx.register(Greeter, FormalGreeter())
    with pytest.raises(ContextDisposedError):
        ctx.get(Greeter)
    with pytest.raises(ContextDisposedError):
        ctx.emit("event")
    with pytest.raises(ContextDisposedError):
        ctx.on("event", lambda: None)
    with pytest.raises(ContextDisposedError):
        ctx.effect(lambda: None)
    with pytest.raises(ContextDisposedError):
        ctx.mount(lambda c: lambda: None)


def test_swap_replaces_and_restores_previous() -> None:
    ctx = PluginContext("test")
    orig = FriendlyGreeter()
    swapped = FormalGreeter()
    ctx.register(Greeter, orig)
    assert ctx.get(Greeter) is orig

    restore = ctx.swap(Greeter, swapped)
    assert ctx.get(Greeter) is swapped

    restore()
    assert ctx.get(Greeter) is orig
