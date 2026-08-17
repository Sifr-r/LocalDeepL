"""Event dispatch tests: emit / parallel / serial / waterfall + registration."""

from __future__ import annotations

import pytest

from omniscribe.api.plugin import PluginContext
from omniscribe.api.plugin.context import _SENTINEL
from omniscribe.api.plugin.errors import EventModeMismatchError

# -- emit mode --------------------------------------------------------------


def test_emit_invokes_listeners_in_registration_order() -> None:
    ctx = PluginContext("test")
    calls: list[str] = []
    ctx.on("ping", lambda: calls.append("a"))
    ctx.on("ping", lambda: calls.append("b"))
    ctx.on("ping", lambda: calls.append("c"))
    ctx.emit("ping")
    assert calls == ["a", "b", "c"]


def test_emit_passes_kwargs_to_listeners() -> None:
    ctx = PluginContext("test")
    captured: list[dict] = []
    ctx.on("event", lambda **kw: captured.append(kw))
    ctx.emit("event", foo=1, bar="two")
    assert captured == [{"foo": 1, "bar": "two"}]


def test_emit_skips_listeners_in_other_modes() -> None:
    ctx = PluginContext("test")
    fired: list[str] = []
    ctx.on("event", lambda: fired.append("emit"), mode="emit")
    ctx.on("event", lambda: fired.append("parallel"), mode="parallel")
    ctx.on("event", lambda: fired.append("serial"), mode="serial")
    ctx.on(
        "event", lambda x, next=None: fired.append(f"waterfall:{x}"), mode="waterfall"
    )
    ctx.emit("event")
    assert fired == ["emit"]


def test_prepend_puts_listener_first() -> None:
    ctx = PluginContext("test")
    order: list[str] = []
    ctx.on("ping", lambda: order.append("a"))
    ctx.on("ping", lambda: order.append("b"))
    ctx.on("ping", lambda: order.append("prepended"), prepend=True)
    ctx.emit("ping")
    assert order == ["prepended", "a", "b"]


def test_no_listeners_is_a_noop() -> None:
    ctx = PluginContext("test")
    ctx.emit("nothing")  # must not raise


def test_on_rejects_non_callable() -> None:
    ctx = PluginContext("test")
    with pytest.raises(TypeError):
        ctx.on("event", "not a function")  # type: ignore[arg-type]


def test_off_removes_specific_listener_and_returns_bool() -> None:
    ctx = PluginContext("test")
    fired: list[str] = []
    a = lambda: fired.append("a")  # noqa: E731
    b = lambda: fired.append("b")  # noqa: E731
    ctx.on("event", a)
    ctx.on("event", b)
    assert ctx.off("event", a) is True
    assert ctx.off("event", a) is False  # already gone
    ctx.emit("event")
    assert fired == ["b"]


# -- parallel mode ----------------------------------------------------------


def test_parallel_invokes_listeners_in_registration_order() -> None:
    ctx = PluginContext("test")
    order: list[str] = []
    ctx.on("event", lambda: order.append("a"), mode="parallel")
    ctx.on("event", lambda: order.append("b"), mode="parallel")
    ctx.parallel("event")
    assert order == ["a", "b"]


def test_parallel_skips_listeners_in_other_modes() -> None:
    ctx = PluginContext("test")
    fired: list[str] = []
    ctx.on("event", lambda: fired.append("emit"), mode="emit")
    ctx.on("event", lambda: fired.append("parallel"), mode="parallel")
    ctx.parallel("event")
    assert fired == ["parallel"]


# -- serial mode ------------------------------------------------------------


def test_serial_passes_initial_then_chains_return_values() -> None:
    ctx = PluginContext("test")
    ctx.on("build", lambda x: x + 1, mode="serial")
    ctx.on("build", lambda x: x * 10, mode="serial")
    ctx.on("build", lambda x: f"final={x}", mode="serial")
    assert ctx.serial("build", initial=1) == "final=20"


def test_serial_with_no_serial_listeners_returns_initial() -> None:
    ctx = PluginContext("test")
    assert ctx.serial("build", initial=42) == 42


def test_serial_skips_non_serial_listeners() -> None:
    ctx = PluginContext("test")
    ctx.on("event", lambda x: x + 100, mode="emit")
    ctx.on("event", lambda x: x + 1, mode="serial")
    ctx.on("event", lambda x: x + 1000, mode="parallel")
    assert ctx.serial("event", initial=0) == 1


# -- waterfall mode ---------------------------------------------------------


def test_waterfall_no_listeners_returns_initial() -> None:
    ctx = PluginContext("test")
    assert ctx.waterfall("event", "init") == "init"
    assert ctx.waterfall("event") is None  # no initial


def test_waterfall_single_listener_passes_initial_and_passes_a_noop_next() -> None:
    """The last listener in a chain gets a ``next`` callable that is a no-op
    (returns the current value), so a listener that ignores ``next`` still
    produces the right result."""
    ctx = PluginContext("test")
    seen: list[tuple[str, object]] = []

    def listener(value, next=None):
        seen.append((value, next))
        return value + "!"

    ctx.on("event", listener, mode="waterfall")
    assert ctx.waterfall("event", "hello") == "hello!"
    # ``next`` is a no-op callable (always available, just delegates to the
    # empty tail); the listener did not call it.
    assert len(seen) == 1
    assert seen[0][0] == "hello"
    assert callable(seen[0][1])


def test_waterfall_chain_calls_next_to_delegate() -> None:
    ctx = PluginContext("test")

    def first(value, next=None):
        return next(value + 1)

    def second(value, next=None):
        return next(value * 10)

    def third(value, next=None):
        return next(f"final={value}")

    ctx.on("chain", first, mode="waterfall")
    ctx.on("chain", second, mode="waterfall")
    ctx.on("chain", third, mode="waterfall")
    assert ctx.waterfall("chain", 1) == "final=20"


def test_waterfall_listener_can_short_circuit_by_returning_directly() -> None:
    ctx = PluginContext("test")

    def policy(value, next=None):
        if value < 0:
            return "blocked"
        return next(value)

    def logger(value, next=None):
        return next(value + 1)

    ctx.on("auth", policy, mode="waterfall")
    ctx.on("auth", logger, mode="waterfall")
    assert ctx.waterfall("auth", 5) == 6  # passes through both
    assert ctx.waterfall("auth", -1) == "blocked"  # short-circuited


def test_waterfall_replaces_value_when_next_called_with_explicit_value() -> None:
    ctx = PluginContext("test")

    def rewriter(value, next=None):
        return next(f"replaced({value})")

    def receiver(value, next=None):
        return f"got:{value}"

    ctx.on("flow", rewriter, mode="waterfall")
    ctx.on("flow", receiver, mode="waterfall")
    assert ctx.waterfall("flow", "orig") == "got:replaced(orig)"


def test_waterfall_raises_when_chain_contains_non_waterfall_listener() -> None:
    ctx = PluginContext("test")
    ctx.on("event", lambda value, next=None: next(value), mode="waterfall")
    ctx.on("event", lambda: None, mode="emit")
    with pytest.raises(EventModeMismatchError) as excinfo:
        ctx.waterfall("event", 1)
    assert excinfo.value.expected == "waterfall"
    assert excinfo.value.got == "emit"


def test_waterfall_forwards_extra_kwargs_to_every_listener() -> None:
    ctx = PluginContext("test")
    captured: list[dict] = []

    def first(value, next=None, **kw):
        captured.append(("first", kw))
        return next(value)

    def second(value, next=None, **kw):
        captured.append(("second", kw))
        return value

    ctx.on("event", first, mode="waterfall")
    ctx.on("event", second, mode="waterfall")
    ctx.waterfall("event", "init", actor="user", scope="audit")
    assert captured == [
        ("first", {"actor": "user", "scope": "audit"}),
        ("second", {"actor": "user", "scope": "audit"}),
    ]


def test_waterfall_sentinel_is_module_level_singleton() -> None:
    """Sentinel must be a unique object so None can be a real value."""
    assert _SENTINEL is _SENTINEL
    assert _SENTINEL is not None
