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
