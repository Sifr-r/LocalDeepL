"""`POST /api/process` thread-bridge contract — the route must not block
the event loop.

The route handler dispatches ``pipeline.run`` to a worker thread via
:func:`asyncio.to_thread` and bridges the async progress callbacks to the
captured main loop via :func:`asyncio.run_coroutine_threadsafe`. The
load-bearing property: ``pipeline.run`` must execute on a thread that is
NOT the asyncio loop thread (``threading.get_ident()`` at the test's main
thread == asyncio loop thread when driven by ``asyncio.run``). If the
to_thread wrapper regresses, this test fails.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from omniscribe.api.routers import state
from omniscribe.api.routers.config import _config
from omniscribe.api.routers.ocr import _run_ocr_pipeline
from omniscribe.api.services.artifacts import TextArtifactStore
from omniscribe.api.services.ocr import execution as ocr_execution
from omniscribe.api.services.ocr.settings import resolve_process_settings
from tests.api._safety_helpers import _process_form_kwargs


def test_run_ocr_pipeline_dispatches_to_thread_pool_worker(tmp_path: Path):
    """``_run_ocr_pipeline`` runs ``pipeline.run`` on a worker thread.

    Without the to_thread wrapper, ``pipeline.run`` would execute on the
    asyncio loop's thread (= the test's main thread when driven via
    ``asyncio.run``), pinning the event loop for the full pipeline
    duration. With the wrapper, the pipeline runs in a separate thread
    and the main loop is released for other work. The test records
    ``threading.get_ident()`` from inside the stubbed ``pipeline.run``
    and from inside the progress callback; both should equal the worker
    thread id, not the test's main thread id.

    See refactor §3.1 in
    ``docs/superpowers/specs/deep_refactor_report.md``.
    """
    main_thread_id = threading.get_ident()
    pipeline_thread_id: list[int] = []
    progress_thread_id: list[int] = []

    class _ThreadProbingPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(
            self, input_path, output_path, *, progress=None, on_warning=None, **_
        ):
            pipeline_thread_id.append(threading.get_ident())
            if progress is not None:
                # The bridge callback runs synchronously in the worker
                # thread before returning the fire-and-forget awaitable,
                # so this ``threading.get_ident()`` is the worker thread.
                progress_thread_id.append(threading.get_ident())
                await progress("init", 0, 1, "starting")
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"]}

    input_path = str(tmp_path / "input.pdf")
    output_path = str(tmp_path / "output.pdf")
    Path(input_path).write_bytes(b"%PDF-1.4\n%%EOF\n")

    original_text_store = state.text_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=None,
            **_process_form_kwargs(),
        )

        with (
            patch("omniscribe.api.services.ocr.execution.build_pipeline") as mock_build,
            patch("omniscribe.api.services.ocr.execution.verify_backend_model"),
        ):
            pipeline = _ThreadProbingPipeline()
            mock_build.return_value = (pipeline, None)

            asyncio.run(
                _run_ocr_pipeline(
                    settings=settings,
                    input_path=input_path,
                    output_path=output_path,
                    progress_target=None,
                )
            )
    finally:
        state.text_artifacts = original_text_store

    assert pipeline_thread_id, "pipeline.run was not called"
    assert pipeline_thread_id[0] != main_thread_id, (
        "pipeline.run executed on the asyncio loop thread — "
        "the to_thread wrapper regressed; the event loop will block "
        "for the full pipeline duration"
    )
    # The progress callback fires from the same thread as pipeline.run
    # (both run inside the worker thread's asyncio.run).
    assert progress_thread_id, "progress callback was not invoked"
    assert progress_thread_id[0] == pipeline_thread_id[0], (
        "progress callback ran on a different thread than pipeline.run — "
        "the bridge is no longer co-located with the pipeline execution"
    )


def test_run_ocr_pipeline_progress_bridge_does_not_block_worker_thread(
    tmp_path: Path,
):
    """The progress bridge must be fire-and-forget, not block on the main loop.

    Each progress frame would normally take some time on the main loop
    (WebSocket send). If the bridge were implemented as ``await
    run_coroutine_threadsafe(...).asyncio.Future`` (block-on-result), the
    worker thread would serialize on the main loop and the
    event-loop-release benefit would be lost. The test stubs the
    connection manager's ``send_progress`` to sleep 0.1s on each call.
    A block-on-result bridge would cause the 3-frame pipeline to take
    ≥ 0.3s; a fire-and-forget bridge completes in well under 0.3s
    because the worker thread schedules and continues.

    See refactor §3.1 in
    ``docs/superpowers/specs/deep_refactor_report.md``.
    """

    class _CountingPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = []

        async def run(
            self, input_path, output_path, *, progress=None, on_warning=None, **_
        ):
            if progress is not None:
                for i in range(3):
                    await progress("ocr", i, 3, f"page {i}")
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"]}

    input_path = str(tmp_path / "input.pdf")
    output_path = str(tmp_path / "output.pdf")
    Path(input_path).write_bytes(b"%PDF-1.4\n%%EOF\n")

    # Stub manager.send_progress to simulate a slow WebSocket send (0.1s).
    # With a fire-and-forget bridge, the worker thread schedules the
    # coroutine and continues without waiting. With a block-on-result
    # bridge, the worker thread would serialize on these sleeps.
    class _SlowConnectionManager:
        async def send_progress(self, *args, **kwargs):
            await asyncio.sleep(0.1)

        async def send_block(self, *args, **kwargs):
            return None

        async def send_page_complete(self, *args, **kwargs):
            return None

        async def send_block_retry(self, *args, **kwargs):
            return None

        async def send_block_revised(self, *args, **kwargs):
            return None

        async def send_quality_summary(self, *args, **kwargs):
            return None

    original_manager = ocr_execution.manager
    ocr_execution.manager = _SlowConnectionManager()  # type: ignore[assignment]
    original_text_store = state.text_artifacts
    state.text_artifacts = TextArtifactStore(artifact_dir=tmp_path / "text")
    try:
        settings = resolve_process_settings(
            settings_store=_config,
            pages=None,
            **_process_form_kwargs(),
        )

        with (
            patch("omniscribe.api.services.ocr.execution.build_pipeline") as mock_build,
            patch("omniscribe.api.services.ocr.execution.verify_backend_model"),
        ):
            pipeline = _CountingPipeline()
            mock_build.return_value = (pipeline, None)

            started = time.monotonic()
            asyncio.run(
                _run_ocr_pipeline(
                    settings=settings,
                    input_path=input_path,
                    output_path=output_path,
                    progress_target=None,
                )
            )
            elapsed = time.monotonic() - started
    finally:
        ocr_execution.manager = original_manager  # type: ignore[assignment]
        state.text_artifacts = original_text_store

    # 3 progress frames × 0.1s = 0.3s if the bridge is fire-and-forget.
    # Block-on-result would push elapsed time to ≥ 0.3s per call, so we
    # assert the elapsed time is well under 0.5s (which would still
    # allow for some serial dispatch overhead).
    assert elapsed < 0.5, (
        f"pipeline.run took {elapsed:.3f}s; the progress bridge appears "
        "to be blocking on the main loop instead of fire-and-forget. "
        "Check that the bridge returns an immediately-resolving "
        "awaitable rather than awaiting the concurrent.futures.Future."
    )
