"""OCR plugin: full route surface over a faked pipeline bridge."""

from __future__ import annotations

import asyncio
import importlib
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from omniscribe.harness.context import Context
from omniscribe.plugins import artifacts as art
from omniscribe.plugins import jobs, progress, runtime
from omniscribe.plugins import state_backend as sb
from omniscribe.plugins.ocr.plugin import OCRPlugin
from omniscribe.plugins.runtime import RuntimeService

# The package __init__ re-exports the ``plugin`` instance, which shadows the
# submodule attribute — import the module itself for monkeypatching.
ocr_plugin_mod = importlib.import_module("omniscribe.plugins.ocr.plugin")
# Sprint 6 split (audit catalog): the pipeline bridge call sites moved
# to ``service.py``. The fake has to be patched on the new module too,
# otherwise the test would hit the real VLM/Surya code path.
ocr_service_mod = importlib.import_module("omniscribe.plugins.ocr.service")

PDF_BYTES = b"%PDF-1.4 fake"


@pytest.fixture()
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replaces the bridge so no VLM / Surya is touched."""
    state: dict[str, Any] = {"fail": False, "wait": False, "gate": asyncio.Event()}

    def fake_build(settings: Any, request: Any, *, block_callbacks: Any = None):
        return object()

    async def fake_run(
        pipeline: Any,
        *,
        settings: Any,
        request: Any,
        input_path: str,
        output_path: str,
        on_progress: Any = None,
        on_warning: Any = None,
        cancel_check: Any = None,
    ) -> dict[int, list[str]]:
        if state["wait"]:
            await state["gate"].wait()
        if on_progress is not None:
            await on_progress(50, "ocr", "Processing page 1")
        if state["fail"]:
            raise RuntimeError("vlm exploded")
        Path(output_path).write_bytes(PDF_BYTES)
        return {0: ["hello world"]}

    monkeypatch.setattr(ocr_service_mod, "build_pipeline", fake_build)
    monkeypatch.setattr(ocr_service_mod, "run_pipeline", fake_run)
    return state


async def _boot(**ocr_config: Any) -> tuple[Context, FastAPI]:
    ctx = Context()
    await ctx.plugin(runtime.RuntimePlugin(), config={})
    await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
    await ctx.plugin(art.ArtifactsPlugin(), config={})
    await ctx.plugin(jobs.JobsPlugin(), config={})
    await ctx.plugin(progress.ProgressPlugin(), config={})
    await ctx.plugin(OCRPlugin(), config=ocr_config)
    app = FastAPI()
    for router in ctx.routes():
        app.include_router(router)
    return ctx, app


def _client(app: FastAPI) -> httpx.AsyncClient:
    """ASGI transport keeps the app on the test loop (same as the worker)."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _upload() -> dict[str, Any]:
    return {"files": {"file": ("a.pdf", b"%PDF-1.4 input", "application/pdf")}}


async def _wait_status(
    client: httpx.AsyncClient, job_id: str, status: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = await client.get(f"/api/process/status/{job_id}")
        body = response.json()
        if body.get("status") == status:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {status!r}; last={body}")


async def _artifact_token_from_events(
    client: httpx.AsyncClient, job_id: str, *, timeout: float = 5.0
) -> str:
    """Read the ``job_completed`` SSE event and return its ``artifact_token``.

    2026-08-29 audit C-3 / H-3: the async result token is delivered
    out-of-band via the ``job_completed`` SSE event (not the status
    response). This helper replays the event stream for tests that
    need the token to download the result.
    """
    import json

    deadline = time.time() + timeout
    async with client.stream("GET", f"/api/process/{job_id}/events") as stream:
        assert stream.status_code == 200
        # Single aiter_lines() pass — httpx raises ``StreamConsumed`` on
        # the second iteration. Track the current SSE event name as we
        # walk the stream.
        current_event: str | None = None
        async for raw in stream.aiter_lines():
            if time.time() > deadline:
                raise AssertionError(
                    f"job {job_id} never emitted job_completed within {timeout}s"
                )
            if raw is None or raw == "" or raw.startswith(":"):
                current_event = None
                continue
            if raw.startswith("event:"):
                current_event = raw.removeprefix("event:").strip()
            elif raw.startswith("data:") and current_event == "job_completed":
                body = json.loads(raw.removeprefix("data:").strip())
                token = body.get("artifact_token")
                if token:
                    return str(token)
                raise AssertionError(
                    f"job_completed for {job_id} had no artifact_token"
                )
    raise AssertionError(f"job {job_id} never emitted job_completed")


# -- sync /api/process -----------------------------------------------------------


async def test_process_sync_returns_pdf_with_artifact_headers(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            response = await client.post("/api/process", **_upload())
        assert response.status_code == 200
        assert response.content == PDF_BYTES
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.headers["x-text-artifact-id"]
        assert response.headers["x-text-artifact-token"]
    finally:
        await ctx.dispose()


async def test_process_sync_rejects_missing_file(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            response = await client.post("/api/process", data={"model": "x"})
        assert response.status_code == 400
    finally:
        await ctx.dispose()


async def test_process_sync_oversized_upload_is_413(fake_pipeline) -> None:
    ctx, app = await _boot(max_upload_mb=1)
    try:
        async with _client(app) as client:
            big = {
                "files": {
                    "file": ("big.pdf", b"x" * (1024 * 1024 + 1), "application/pdf")
                }
            }
            response = await client.post("/api/process", **big)
        assert response.status_code == 413
    finally:
        await ctx.dispose()


# -- async lifecycle -----------------------------------------------------------


async def test_async_submit_status_result_and_job_list(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            submit = await client.post(
                "/api/process/async", data={"pipeline_mode": "hybrid"}, **_upload()
            )
            assert submit.status_code == 202
            body = submit.json()
            assert body["status"] == "pending"
            job_id = body["job_id"]
            assert body["status_url"] == f"/api/process/status/{job_id}"

            done = await _wait_status(client, job_id, "complete")
            assert done["filename"] == "a.pdf"
            assert done["text_artifact_id"]
            # 2026-08-29 audit C-3 / H-3: status no longer leaks the
            # artifact token; the async client receives it from the
            # ``job_completed`` SSE event payload.
            assert "text_artifact_token" not in done
            assert "text_artifact_url" not in done

            token = await _artifact_token_from_events(client, job_id)
            assert token

            result = await client.get(
                f"/api/jobs/{job_id}/result",
                params={"token": token},
            )
            assert result.status_code == 200
            assert result.content == PDF_BYTES

            wrong = await client.get(
                f"/api/jobs/{job_id}/result", params={"token": "nope"}
            )
            assert wrong.status_code == 403

            listing = await client.get("/api/jobs")
            assert listing.status_code == 200
            items = listing.json()
            assert len(items) == 1
            assert items[0]["id"] == job_id
            assert items[0]["filename"] == "a.pdf"
            assert items[0]["status"] == "complete"
            assert items[0]["timestamp"]

            cleared = await client.delete("/api/jobs")
            assert cleared.status_code == 200
            assert cleared.json()["cleared"] == 1
            assert (await client.get("/api/jobs")).json() == []
    finally:
        await ctx.dispose()


async def test_async_failure_maps_to_error_status_and_409_result(
    fake_pipeline,
) -> None:
    fake_pipeline["fail"] = True
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            submit = await client.post("/api/process/async", **_upload())
            job_id = submit.json()["job_id"]
            failed = await _wait_status(client, job_id, "error")
            assert failed["error"] == "vlm exploded"

            result = await client.get(
                f"/api/jobs/{job_id}/result", params={"token": "anything"}
            )
            assert result.status_code == 409
    finally:
        await ctx.dispose()


async def test_status_unknown_job_is_404(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            assert (await client.get("/api/process/status/nope")).status_code == 404
            assert (await client.get("/api/jobs/nope/result")).status_code == 404
            assert (await client.post("/api/jobs/nope/cancel")).status_code == 404
    finally:
        await ctx.dispose()


async def test_cancel_queued_job(fake_pipeline) -> None:
    fake_pipeline["wait"] = True
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            first = await client.post("/api/process/async", **_upload())
            first_id = first.json()["job_id"]
            # wait for the single worker to claim job one
            await _wait_status(client, first_id, "processing")

            second = await client.post("/api/process/async", **_upload())
            second_id = second.json()["job_id"]
            assert (await _wait_status(client, second_id, "pending"))[
                "status"
            ] == "pending"

            cancel = await client.post(f"/api/jobs/{second_id}/cancel")
            assert cancel.status_code == 200
            assert cancel.json() == {"cancelled": True}
            cancelled = await _wait_status(client, second_id, "error")
            assert cancelled["error"] == "Job cancelled."

            # terminal cancel is a no-op
            again = await client.post(f"/api/jobs/{second_id}/cancel")
            assert again.json() == {"cancelled": False}

            fake_pipeline["gate"].set()
            await _wait_status(client, first_id, "complete")
    finally:
        await ctx.dispose()


# -- SSE -----------------------------------------------------------------------


async def test_events_stream_replays_job_lifecycle(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            submit = await client.post("/api/process/async", **_upload())
            job_id = submit.json()["job_id"]
            await _wait_status(client, job_id, "complete")

            async with client.stream("GET", f"/api/process/{job_id}/events") as stream:
                assert stream.status_code == 200
                text = "".join([chunk async for chunk in stream.aiter_text()])
            assert "event: job_queued" in text
            assert "event: job_started" in text
            assert "event: job_completed" in text

            unknown = await client.get("/api/process/nope/events")
            assert unknown.status_code == 404
    finally:
        await ctx.dispose()


# -- config store ----------------------------------------------------------------


async def test_config_round_trip_with_settings_write_through(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            got = await client.get("/api/config")
            assert got.status_code == 200
            seeded = got.json()
            assert seeded["pipeline_mode"] == "hybrid"
            assert seeded["dense_mode"] == "auto"
            assert seeded["document_processors"] == []

            updated = await client.post(
                "/api/config",
                json={"model": "new-model", "dpi": 300, "unknown_key": 1},
            )
            assert updated.status_code == 200
            body = updated.json()
            assert body["model"] == "new-model"
            assert body["dpi"] == 300
            assert "unknown_key" not in body

            runtime_service = ctx.inject(RuntimeService)
            assert runtime_service.settings.llm_model == "new-model"

            alias = await client.get("/api/config/ocr")
            assert alias.json()["model"] == "new-model"
            put = await client.put("/api/config/ocr", json={"dense_mode": "always"})
            assert put.status_code == 200
            assert put.json()["dense_mode"] == "always"
    finally:
        await ctx.dispose()


async def test_update_config_rejects_ssrf_blocked_api_base(fake_pipeline) -> None:
    ctx, app = await _boot()
    try:
        async with _client(app) as client:
            res = await client.post(
                "/api/config",
                json={"api_base": "http://169.254.169.254/v1"},
            )
            assert res.status_code == 400
            assert "SSRF blocked" in res.json().get("detail", "")
    finally:
        await ctx.dispose()


async def test_event_buffers_and_done_jobs_are_bounded_and_pruned(
    fake_pipeline,
) -> None:
    from omniscribe.plugins.jobs import JobCompleted, JobQueued
    from omniscribe.plugins.ocr.service import OCRServiceImpl

    ctx, _app = await _boot()
    try:
        service = ctx.inject(ocr_plugin_mod.OCRService)
        assert isinstance(service, OCRServiceImpl)
        service._max_buffered_jobs = 10

        for i in range(25):
            job_id = f"job_{i}"
            await service.record_event(JobQueued(job_id=job_id))
            await service.record_event(
                JobCompleted(job_id=job_id, artifact_id="a", artifact_token="t")
            )

        assert len(service._event_buffers) <= 10
        assert len(service._done_jobs) <= 10
        # Oldest jobs were pruned
        assert "job_0" not in service._event_buffers
        assert service.is_done("job_0") is False
        # Newest jobs are present
        assert "job_24" in service._event_buffers
        assert service.is_done("job_24") is True

        # Explicit prune
        pruned_count = service.prune(max_buffered_jobs=5)
        assert pruned_count == 5
        assert len(service._event_buffers) == 5
    finally:
        await ctx.dispose()
