"""Concurrent test: AGPL notice emitted exactly once even under racing first-use."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

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
