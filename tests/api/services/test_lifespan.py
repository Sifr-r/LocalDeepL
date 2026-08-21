"""Tests for the LifespanRunner / LifespanStep decomposition.

The runner is the wiring behind the FastAPI app's lifespan. Every
test here drives the runner directly (without FastAPI) so a regression
in setup ordering, teardown ordering, handle plumbing, or fail-open
semantics is caught before it can poison a real server boot.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from omniscribe.api.services.lifespan import LifespanRunner, LifespanStep

# -- Setup ordering ----------------------------------------------------------


async def test_setup_runs_steps_in_list_order() -> None:
    """Each step's setup is invoked once, in the order it appears in the
    runner's list. The runner does NOT re-order, dedupe, or sort."""
    calls: list[str] = []

    async def setup_a() -> None:
        calls.append("setup-a")

    async def setup_b() -> None:
        calls.append("setup-b")

    async def setup_c() -> None:
        calls.append("setup-c")

    async def teardown(_: object) -> None:
        pass

    runner = LifespanRunner(
        [
            LifespanStep("a", setup_a, teardown),
            LifespanStep("b", setup_b, teardown),
            LifespanStep("c", setup_c, teardown),
        ]
    )
    async with runner.run():
        assert calls == ["setup-a", "setup-b", "setup-c"]


# -- Teardown ordering -------------------------------------------------------


async def test_teardown_runs_steps_in_reverse_order() -> None:
    """LIFO teardown: last setup is first teardown. Matches the
    convention for resource cleanup (close-after-open in reverse)."""
    calls: list[str] = []

    async def setup(name: str) -> None:
        async def _setup() -> None:
            calls.append(f"setup-{name}")

        return _setup  # not actually called; only the outer one runs

    async def make_setup(name: str) -> Any:
        async def _setup() -> None:
            calls.append(f"setup-{name}")

        return _setup

    async def make_teardown(name: str) -> Any:
        async def _teardown(_: object) -> None:
            calls.append(f"teardown-{name}")

        return _teardown

    runner = LifespanRunner(
        [
            LifespanStep("a", await make_setup("a"), await make_teardown("a")),
            LifespanStep("b", await make_setup("b"), await make_teardown("b")),
            LifespanStep("c", await make_setup("c"), await make_teardown("c")),
        ]
    )
    async with runner.run():
        # Inside the body only setup has run.
        assert calls == ["setup-a", "setup-b", "setup-c"]
    # After exit, teardown has run in LIFO order.
    assert calls == [
        "setup-a",
        "setup-b",
        "setup-c",
        "teardown-c",
        "teardown-b",
        "teardown-a",
    ]


# -- Handle plumbing ---------------------------------------------------------


async def test_setup_return_value_is_passed_to_teardown() -> None:
    """Whatever the setup call returns becomes the teardown's only
    positional argument. This is the per-step "handle" — used by the
    artifact_cleanup step to plumb its asyncio.Task through."""
    received: list[object] = []

    async def setup() -> str:
        return "handle-x"

    async def teardown(handle: object) -> None:
        received.append(handle)

    runner = LifespanRunner([LifespanStep("x", setup, teardown)])
    async with runner.run():
        pass
    assert received == ["handle-x"]


async def test_setup_returning_none_still_passes_none_to_teardown() -> None:
    """The common case: setup returns ``None`` (the default). Teardown
    must accept ``None`` without complaint."""
    received: list[object] = []

    async def setup() -> None:
        return None

    async def teardown(handle: object) -> None:
        received.append(handle)

    runner = LifespanRunner([LifespanStep("n", setup, teardown)])
    async with runner.run():
        pass
    assert received == [None]


# -- Failure semantics -------------------------------------------------------


async def test_setup_failure_unwinds_started_steps_and_reraises() -> None:
    """If the third setup raises, the runner tears down the two steps
    that already started (in LIFO order) and re-raises the original
    exception. Un-started steps are NOT touched."""
    teardowns_called: list[str] = []
    setup_b_called = False

    async def setup_a() -> None:
        pass

    async def teardown_a(_: object) -> None:
        teardowns_called.append("a")

    async def setup_b() -> None:
        nonlocal setup_b_called
        setup_b_called = True

    async def teardown_b(_: object) -> None:
        teardowns_called.append("b")

    async def setup_c() -> None:
        raise RuntimeError("boom")

    async def teardown_c(_: object) -> None:
        teardowns_called.append("c")

    async def setup_d() -> None:
        pass  # never reached

    async def teardown_d(_: object) -> None:
        teardowns_called.append("d")

    runner = LifespanRunner(
        [
            LifespanStep("a", setup_a, teardown_a),
            LifespanStep("b", setup_b, teardown_b),
            LifespanStep("c", setup_c, teardown_c),
            LifespanStep("d", setup_d, teardown_d),
        ]
    )
    with pytest.raises(RuntimeError, match="boom"):
        async with runner.run():
            pass
    # a, b started; teardown runs LIFO so b then a; c, d never started.
    assert setup_b_called is True
    assert teardowns_called == ["b", "a"]


async def test_teardown_failure_is_logged_and_other_teardowns_continue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One broken teardown must NOT stop the other teardowns from
    running — a half-shut-down server leaks resources, so the runner
    logs and continues."""
    teardowns_called: list[str] = []

    async def setup_a() -> None:
        pass

    async def teardown_a(_: object) -> None:
        teardowns_called.append("a")

    async def setup_b() -> None:
        pass

    async def teardown_b(_: object) -> None:
        teardowns_called.append("b")
        raise ValueError("cleanup b exploded")

    async def setup_c() -> None:
        pass

    async def teardown_c(_: object) -> None:
        teardowns_called.append("c")

    runner = LifespanRunner(
        [
            LifespanStep("a", setup_a, teardown_a),
            LifespanStep("b", setup_b, teardown_b),
            LifespanStep("c", setup_c, teardown_c),
        ]
    )
    with caplog.at_level(logging.ERROR, logger="omniscribe.api.services.lifespan"):
        async with runner.run():
            pass
    # All three teardowns ran — the broken middle one didn't stop the rest.
    # LIFO teardown order: c (last registered) first, then b, then a.
    assert teardowns_called == ["c", "b", "a"]
    # The exception is logged with the step name.
    assert any(
        "b" in rec.message and "continuing" in rec.message for rec in caplog.records
    )


# -- Introspection -----------------------------------------------------------


def test_step_names_returns_setup_order() -> None:
    """``step_names`` exposes the step list in setup order for
    diagnostics; teardown is intentionally NOT surfaced here (the
    inversion is the runner's job, not the caller's)."""

    async def setup() -> None:
        pass

    async def teardown(_: object) -> None:
        pass

    runner = LifespanRunner(
        [
            LifespanStep("alpha", setup, teardown),
            LifespanStep("beta", setup, teardown),
        ]
    )
    assert runner.step_names == ["alpha", "beta"]


def test_runner_copies_input_step_list() -> None:
    """Mutating the caller's list after construction must NOT reorder
    the runner's internal list (silent reorder would scramble teardown)."""

    async def setup() -> None:
        pass

    async def teardown(_: object) -> None:
        pass

    original = [LifespanStep("first", setup, teardown)]
    runner = LifespanRunner(original)
    original.append(LifespanStep("second", setup, teardown))
    assert runner.step_names == ["first"]


# -- FastAPI integration -----------------------------------------------------


async def test_as_fastapi_lifespan_drives_a_real_fastapi_app() -> None:
    """End-to-end: a runner exposed via :meth:`as_fastapi_lifespan`
    fires the same setup/teardown sequence the inline ``@asynccontextmanager``
    form would, but through FastAPI's lifespan plumbing."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    log: list[str] = []

    async def setup() -> None:
        log.append("setup")

    async def teardown(_: object) -> None:
        log.append("teardown")

    runner = LifespanRunner([LifespanStep("only", setup, teardown)])
    app = FastAPI(lifespan=runner.as_fastapi_lifespan())

    @app.get("/probe")
    def probe() -> dict[str, str]:
        return {"ok": "yes"}

    # Entering the context opens the lifespan.
    with TestClient(app) as client:
        # Inside the lifespan: setup ran, teardown did not.
        assert log == ["setup"]
        response = client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"ok": "yes"}
    # Leaving the context closed the lifespan: teardown ran.
    assert log == ["setup", "teardown"]
