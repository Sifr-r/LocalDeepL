"""Tests: AGPL notice uses a lock so concurrent first-use emits the notice at most once.

The GIL serializes the tiny read-check-set critical section in CPython, so the
8-thread ``test_agpl_notice_emitted_exactly_once_under_concurrency`` smoke test
cannot actually trigger a race (it always sees exactly 1 emission whether or
not the production code wraps the flag in a lock). It still guards the happy
path and the ``caplog`` plumbing.

The complementary ``test_emit_uses_lock_and_lock_is_mutex`` test patches
``_AGPL_NOTICE_LOCK`` with a recording wrapper and asserts the function
actually enters the lock on every call (and that the lock is held by at most
one caller at a time). This is the regression test for the production fix:
removing the ``with _AGPL_NOTICE_LOCK:`` block from
``_emit_pymupdf_agpl_notice`` would break it.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from omniscribe.core.pdf import rasterizer


def test_agpl_notice_emitted_exactly_once_under_concurrency(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Reset the module-level flag so the test is deterministic
    # regardless of which tests ran first.
    rasterizer._PYMUPDF_AGPL_NOTICE_EMITTED = False
    caplog.clear()

    N = 8
    barrier = threading.Barrier(N)

    def emit() -> None:
        barrier.wait()
        rasterizer._emit_pymupdf_agpl_notice()

    with caplog.at_level(logging.INFO, logger=rasterizer._LOGGER.name):
        with ThreadPoolExecutor(max_workers=N) as ex:
            futures = [ex.submit(emit) for _ in range(N)]
            for f in futures:
                f.result()

    matching = [
        r
        for r in caplog.records
        if "AGPL" in r.getMessage() or "agpl" in r.getMessage().lower()
    ]
    assert len(matching) == 1, (
        f"expected exactly 1 AGPL log line under {N}-thread concurrent first-use, "
        f"got {len(matching)}: {[r.getMessage() for r in matching]}"
    )


class _RecordingLock:
    """Context-manager wrapper around a real ``threading.Lock`` that records
    acquire / release events and tracks the maximum number of concurrent
    holders observed.

    Behaves like the wrapped lock from the caller's perspective: the
    ``with`` statement enters and exits it, and the real lock is held for
    the duration of the wrapper's critical section.
    """

    def __init__(self, real: threading.Lock) -> None:
        self._real = real
        self.acquired = 0
        self.inside_count = 0
        self.max_concurrent_inside = 0

    def __enter__(self) -> _RecordingLock:
        self._real.acquire()
        self.acquired += 1
        self.inside_count += 1
        if self.inside_count > self.max_concurrent_inside:
            self.max_concurrent_inside = self.inside_count
        return self

    def __exit__(self, *args: Any) -> None:
        self.inside_count -= 1
        self._real.release()


def test_emit_uses_lock_and_lock_is_mutex() -> None:
    """Regression test for the ``with _AGPL_NOTICE_LOCK:`` block.

    Asserts two things about ``_emit_pymupdf_agpl_notice``:

    1. It actually enters the lock on every call (``acquired == 2`` after
       two calls). Removing the ``with`` block from production code would
       drop this to 0 and fail the test.
    2. The lock is a mutex: at most one caller holds it at any moment
       (``max_concurrent_inside == 1``). ``threading.Lock`` provides this
       guarantee natively; the recording wrapper makes it observable.
    """
    rasterizer._PYMUPDF_AGPL_NOTICE_EMITTED = False

    real_lock = rasterizer._AGPL_NOTICE_LOCK
    recording = _RecordingLock(real_lock)
    rasterizer._AGPL_NOTICE_LOCK = recording
    try:
        rasterizer._emit_pymupdf_agpl_notice()
        rasterizer._emit_pymupdf_agpl_notice()
    finally:
        rasterizer._AGPL_NOTICE_LOCK = real_lock

    assert recording.acquired == 2, (
        f"expected the function to enter _AGPL_NOTICE_LOCK twice (once per "
        f"call), got acquired={recording.acquired}. The production code "
        f"is likely no longer wrapping the flag in `with _AGPL_NOTICE_LOCK:`."
    )
    assert recording.max_concurrent_inside == 1, (
        f"expected _AGPL_NOTICE_LOCK to be a mutex (max 1 concurrent "
        f"holder), got max_concurrent_inside={recording.max_concurrent_inside}"
    )
