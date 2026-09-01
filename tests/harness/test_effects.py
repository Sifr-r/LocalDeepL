"""EffectRef and EffectScope semantics."""

from __future__ import annotations

import pytest

from omniscribe.harness.effects import EffectRef, EffectScope, effect_scope


def test_effect_ref_fields() -> None:
    ref = EffectRef(plugin_id="ocr", kind="service", key="OCRService")
    assert ref.plugin_id == "ocr"
    assert ref.kind == "service"
    assert ref.key == "OCRService"


def test_effect_ref_ids_are_unique() -> None:
    a = EffectRef(plugin_id="p", kind="effect", key=None)
    b = EffectRef(plugin_id="p", kind="effect", key=None)
    assert a._id != b._id


async def test_scope_runs_cleanups_lifo_and_awaits_async() -> None:
    order: list[str] = []
    scope = EffectScope()
    scope.add(lambda: order.append("first"))

    async def _async_cleanup() -> None:
        order.append("async-second")

    scope.add(_async_cleanup)
    scope.add(lambda: order.append("third"))
    await scope.aclose()
    assert order == ["third", "async-second", "first"]


async def test_scope_aclose_is_idempotent() -> None:
    calls = 0
    scope = EffectScope()
    scope.add(lambda: _inc())

    def _inc() -> None:
        nonlocal calls
        calls += 1

    await scope.aclose()
    await scope.aclose()
    assert calls == 1


async def test_scope_add_after_close_raises() -> None:
    scope = EffectScope()
    await scope.aclose()
    with pytest.raises(RuntimeError):
        scope.add(lambda: None)


async def test_effect_scope_helper_runs_cleanups_on_exit() -> None:
    ran = []
    async with effect_scope() as scope:
        scope.add(lambda: ran.append(True))
        assert not scope.closed
    assert ran == [True]
    assert scope.closed


# ---------------------------------------------------------------------------
# Pedantic 9.2 / 9.3 / 9.4: harness/effects.py hardening
# ---------------------------------------------------------------------------


async def test_scope_aclose_continues_after_failing_cleanup(caplog) -> None:
    """Pedantic 9.3: a cleanup that raises must not stop the
    remaining cleanups from running. Each cleanup is independent;
    a single failure is logged and the loop continues.
    """
    ran: list[str] = []
    scope = EffectScope()
    scope.add(lambda: ran.append("first"))
    scope.add(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    scope.add(lambda: ran.append("third"))

    with caplog.at_level("ERROR", logger="omniscribe.harness"):
        await scope.aclose()

    assert ran == ["third", "first"]


async def test_scope_aclose_continues_after_failing_async_cleanup(caplog) -> None:
    """Pedantic 9.3 (async path): the same isolation for a
    coroutine cleanup. A failing awaitable is caught and logged;
    the next cleanup still runs.
    """
    ran: list[str] = []
    scope = EffectScope()

    async def _bad() -> None:
        raise RuntimeError("async boom")

    async def _ok() -> None:
        ran.append("ok")

    scope.add(_bad)
    scope.add(_ok)
    with caplog.at_level("ERROR", logger="omniscribe.harness"):
        await scope.aclose()
    assert ran == ["ok"]


def test_scope_add_is_thread_safe() -> None:
    """Pedantic 9.4: ``EffectScope.add`` may be called from any
    thread that holds the scope (e.g. a plugin ``apply`` running
    in a worker thread). Concurrent ``add`` calls must not corrupt
    the LIFO list.
    """
    import threading

    scope = EffectScope()
    barrier = threading.Barrier(8)

    def worker(tag: str) -> None:
        barrier.wait()
        for i in range(50):
            scope.add(lambda i=i, tag=tag: (i, tag))  # type: ignore[arg-type, misc]

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 8 threads × 50 add calls each = 400 cleanups registered.
    assert len(scope._cleanups) == 400


async def test_context_effect_ids_are_local_to_context() -> None:
    """Pedantic 9.2: ids must be per-Context, not process-global.
    Two fresh ``Context`` instances each start their id sequence
    at 1 — the ``_id`` is an int so the values are equal, but
    each Context owns its own counter so the sequence is
    re-allocated, not shared.
    """
    from omniscribe.harness.context import Context

    a = Context()
    b = Context()

    a_ids = [a.effect(lambda: None)._id for _ in range(3)]
    b_ids = [b.effect(lambda: None)._id for _ in range(3)]

    # Each Context starts its counter at 1 and increments. A and B
    # allocate the same id values, but they are independent
    # allocations (the effect refs they point at are different
    # objects with different keys).
    assert a_ids == [1, 2, 3]
    assert b_ids == [1, 2, 3]

    # Disposing Context A must not touch Context B's effects
    # (proves the per-Context id space is independent).
    await a.dispose()
    assert len(b._effect_cleanups) == 3
