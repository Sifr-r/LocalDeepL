"""Lifespan step decomposition for the FastAPI app.

Decomposes the FastAPI lifespan callback into a list of named,
independently testable (setup, teardown) pairs. The :class:`LifespanRunner`
runs setup in list order, teardown in reverse (LIFO), with fail-open
semantics: a teardown exception in one step must not stop the others
from running so a half-shut-down server doesn't leak resources.

Why a runner instead of inline try/finally
------------------------------------------

The inline ``@asynccontextmanager`` form makes each step's teardown
implicit and order-sensitive (every new contributor has to read the
whole block to know where to add their step). With a runner:

- Adding a step is one entry in a list, near the others, with its own
  name for the log line.
- Each step is independently testable: hand the runner a list of fake
  steps and assert the call order, the handle plumbing, and the
  fail-open teardown.
- The "teardown is LIFO" rule is encoded once in the runner instead of
  being the caller's responsibility to maintain.

The runner is intentionally minimal: it doesn't know about the plugin
context, the OCR queue, or any other OmniScribe-specific concern.
Those are wiring concerns; the runner is plumbing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# The value returned by ``setup`` is passed back to ``teardown`` so a
# step can plumb a handle between the two phases (e.g. an asyncio.Task
# that needs cancelling). ``Any`` because the type is step-specific.
SetupResult = Any

# Both callbacks are async so a step can be a thin wrapper over any
# async library call. Sync steps wrap their work in ``async def`` shims.
SetupFn = Callable[[], Awaitable[SetupResult]]
TeardownFn = Callable[[SetupResult], Awaitable[None]]


@dataclass(frozen=True)
class LifespanStep:
    """A single (setup, teardown) pair in the FastAPI app lifespan.

    Parameters
    ----------
    name:
        Human-readable label. Surfaced in the setup/teardown log lines
        and in the ``runner.steps()`` introspection helper.
    setup:
        Async callable invoked once when the lifespan opens. Whatever
        it returns is passed to :attr:`teardown` when the lifespan
        closes (the value is the per-step "handle").
    teardown:
        Async callable invoked once when the lifespan closes. Receives
        the setup's return value as its only positional argument.
        Must NOT raise unless something is genuinely broken — the
        runner logs and continues on teardown failure so a single
        broken cleanup doesn't leak the rest of the process state.
    """

    name: str
    setup: SetupFn
    teardown: TeardownFn


class LifespanRunner:
    """Run a sequence of :class:`LifespanStep` instances as one lifespan.

    Usage::

        runner = LifespanRunner([
            LifespanStep("lexicon", setup_lexicon, teardown_lexicon),
            LifespanStep("ocr_queue", start_queue, stop_queue),
            ...
        ])
        app = FastAPI(lifespan=runner.as_fastapi_lifespan())

    The runner also exposes :meth:`run` directly so tests can drive it
    without going through FastAPI's lifespan machinery.
    """

    def __init__(self, steps: Sequence[LifespanStep]) -> None:
        # Defensive copy so the caller's list can't be mutated after the
        # runner is constructed (would silently reorder setup/teardown).
        self._steps: list[LifespanStep] = list(steps)

    @property
    def step_names(self) -> list[str]:
        """The step names in setup order (introspection only)."""
        return [step.name for step in self._steps]

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Run every step's setup, yield, then teardown in reverse.

        Fail-open: if any setup raises, the runner tears down the steps
        that already started (in LIFO order) and re-raises the original
        exception. If any teardown raises, the runner logs and continues
        with the remaining teardowns so one broken cleanup can't leak
        process state.
        """
        handles: list[SetupResult] = []
        started: list[LifespanStep] = []
        try:
            for step in self._steps:
                logger.debug("lifespan setup: %s", step.name)
                handle = await step.setup()
                handles.append(handle)
                started.append(step)
            yield
        except BaseException:
            # Setup failed: unwind the started steps in LIFO order, then
            # re-raise. We use BaseException so KeyboardInterrupt /
            # SystemExit also unwind cleanly.
            await self._teardown_in_order(started, handles)
            raise
        # Normal exit: teardown everything in LIFO order.
        await self._teardown_in_order(self._steps, handles)

    async def _teardown_in_order(
        self,
        steps: Sequence[LifespanStep],
        handles: Sequence[SetupResult],
    ) -> None:
        """Call each step's teardown in reverse order; never let one
        failure block the rest."""
        # zip so a length mismatch between steps and handles (a
        # programming bug) doesn't cause an IndexError on teardown.
        # ``strict=False`` is the explicit default; a length mismatch
        # silently truncates to the shorter sequence.
        for step, handle in zip(reversed(steps), reversed(handles), strict=False):
            try:
                logger.debug("lifespan teardown: %s", step.name)
                await step.teardown(handle)
            except Exception:
                logger.exception(
                    "lifespan teardown failed for step %r; continuing with the rest",
                    step.name,
                )

    def as_fastapi_lifespan(
        self,
    ) -> Callable[[Any], AbstractAsyncContextManager[None]]:
        """Return a FastAPI-compatible lifespan callable.

        FastAPI calls the lifespan with the ``app`` instance as its only
        argument; we ignore it and just delegate to :meth:`run`.
        """
        runner = self

        @asynccontextmanager
        async def _fastapi_lifespan(_app: Any) -> AsyncIterator[None]:
            async with runner.run():
                yield

        return _fastapi_lifespan


__all__ = [
    "LifespanRunner",
    "LifespanStep",
    "SetupFn",
    "SetupResult",
    "TeardownFn",
]
