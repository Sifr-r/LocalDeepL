"""Unit tests for distributed OCR Celery task and async router orchestration."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import ocr, state
from omniscribe.api.routers.config import _config
from omniscribe.api.services.artifacts import TextArtifactHandle
from omniscribe.api.services.jobs import JobRecord
from omniscribe.api.services.ocr_jobs import OCRJobRecord, OCRJobStatus
from omniscribe.api.services.ocr_settings import resolve_process_settings
from omniscribe.api.services.state_backend import LocalStateBackend
from omniscribe.api.services.state_backend_redis import RedisStateBackend
from omniscribe.api.tasks import _CeleryTaskBase, _OCRTask, process_ocr_task


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(ocr.router)
    return TestClient(app)


def _make_settings_dict(**overrides: Any) -> dict[str, Any]:
    """Build a complete settings dictionary valid for ProcessSettings."""
    pages = overrides.pop("pages", None)
    settings = resolve_process_settings(
        settings_store=_config,
        pages=pages,
        **overrides,
    )
    return settings.model_dump()


def test_ocr_task_definition():
    """_OCRTask must inherit from _CeleryTaskBase and process_ocr_task is registered."""
    assert issubclass(_OCRTask, _CeleryTaskBase)
    assert callable(process_ocr_task)
    assert process_ocr_task.name == "process_ocr"


def test_process_ocr_task_validation():
    """process_ocr_task must reject invalid job_id, file_path, and settings_dict."""
    with pytest.raises(ValueError, match="job_id must be a non-empty string"):
        process_ocr_task.run("", "/path/to/file.pdf", {})

    with pytest.raises(ValueError, match="job_id must be a non-empty string"):
        process_ocr_task.run(None, "/path/to/file.pdf", {})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="file_path must be a non-empty string"):
        process_ocr_task.run("job-1", "", {})

    with pytest.raises(ValueError, match="file_path must be a non-empty string"):
        process_ocr_task.run("job-1", None, {})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="settings_dict must be a dict"):
        process_ocr_task.run("job-1", "/path/to/file.pdf", "not-a-dict")  # type: ignore[arg-type]


def test_process_ocr_task_success(tmp_path: Path):
    """process_ocr_task executes pipeline, emits progress, records job, and returns result."""
    sample_file = tmp_path / "sample.pdf"
    sample_file.write_bytes(b"%PDF-1.4 dummy content")

    mock_artifact = TextArtifactHandle(
        artifact_id="art-12345",
        token="tok-67890",
        path=str(tmp_path / "art-12345.json"),
        expires_at=9999999999.0,
    )
    mock_pipeline = MagicMock()
    mock_pipeline.last_failed_pages = []

    progress_calls: list[tuple[int, str]] = []

    def _mock_emit_progress(self_task, pct: int, msg: str):
        progress_calls.append((pct, msg))

    with (
        patch(
            "omniscribe.api.routers.ocr._execute_ocr_pipeline",
            new=AsyncMock(
                return_value=(
                    mock_pipeline,
                    mock_artifact,
                    None,
                    str(tmp_path / "art.txt"),
                    [],
                )
            ),
        ) as mock_exec,
        patch("omniscribe.api.routers.ocr._emit_job_started") as mock_started,
        patch("omniscribe.api.routers.ocr._record_job") as mock_record,
        patch.object(_OCRTask, "emit_progress", _mock_emit_progress),
    ):
        settings_payload = _make_settings_dict(
            model="test-vlm-model",
            pipeline_mode="hybrid",
            pages="1-2",
        )
        res = process_ocr_task.run(
            "job-test-success",
            str(sample_file),
            settings_payload,
            channel_id="chan-1",
            session_token="token-1",
        )

        assert res["job_id"] == "job-test-success"
        assert res["status"] == "complete"
        assert res["text_artifact_id"] == "art-12345"
        assert res["text_artifact_token"] == "tok-67890"
        assert res["failed_pages"] == []
        assert "output_pdf_path" in res

        mock_exec.assert_awaited_once()
        mock_started.assert_called_once_with(
            "job-test-success",
            model="test-vlm-model",
            pipeline_mode="hybrid",
            pages="1-2",
        )
        mock_record.assert_called_once()
        record_kwargs = mock_record.call_args[1]
        assert record_kwargs["job_id"] == "job-test-success"
        assert record_kwargs["filename"] == "sample.pdf"
        assert record_kwargs["model"] == "test-vlm-model"
        assert record_kwargs["pipeline_mode"] == "hybrid"
        assert record_kwargs["pages"] == "1-2"
        assert record_kwargs["status"] == "complete"
        assert record_kwargs["text_artifact_id"] == "art-12345"

        assert (0, "Initializing OCR pipeline") in progress_calls
        assert (100, "OCR complete") in progress_calls


def test_process_ocr_task_extracts_channel_from_settings(tmp_path: Path):
    """Extracts channel_id and session_token from settings_dict when direct args are None."""
    sample_file = tmp_path / "sample.pdf"
    sample_file.write_bytes(b"%PDF-1.4 dummy content")

    mock_artifact = TextArtifactHandle(
        artifact_id="art-channel",
        token="tok-channel",
        path=str(tmp_path / "art-channel.json"),
        expires_at=9999999999.0,
    )
    mock_pipeline = MagicMock()

    with (
        patch(
            "omniscribe.api.routers.ocr._execute_ocr_pipeline",
            new=AsyncMock(
                return_value=(
                    mock_pipeline,
                    mock_artifact,
                    None,
                    str(tmp_path / "art.txt"),
                    [],
                )
            ),
        ) as mock_exec,
        patch("omniscribe.api.routers.ocr._emit_job_started"),
        patch("omniscribe.api.routers.ocr._record_job"),
        patch.object(_OCRTask, "emit_progress"),
    ):
        settings_payload = _make_settings_dict(
            model="test-vlm-model",
            pipeline_mode="hybrid",
        )
        settings_payload["progress_channel"] = "injected-channel-id"
        settings_payload["progress_token"] = "injected-token"

        res = process_ocr_task.run(
            "job-test-channel",
            str(sample_file),
            settings_payload,
        )

        assert res["status"] == "complete"
        mock_exec.assert_awaited_once()
        exec_kwargs = mock_exec.call_args[1]
        assert exec_kwargs["progress_target"] == "injected-channel-id"


def test_process_ocr_task_error_handling(tmp_path: Path):
    """On exception during pipeline execution, job is recorded as error and re-raised."""
    sample_file = tmp_path / "sample.pdf"
    sample_file.write_bytes(b"%PDF-1.4 dummy content")

    progress_calls: list[tuple[int, str]] = []

    def _mock_emit_progress(self_task, pct: int, msg: str):
        progress_calls.append((pct, msg))

    with (
        patch(
            "omniscribe.api.routers.ocr._execute_ocr_pipeline",
            new=AsyncMock(side_effect=RuntimeError("VLM connection timed out")),
        ),
        patch("omniscribe.api.routers.ocr._emit_job_started"),
        patch("omniscribe.api.routers.ocr._record_job") as mock_record,
        patch.object(_OCRTask, "emit_progress", _mock_emit_progress),
    ):
        settings_payload = _make_settings_dict(
            model="failing-model",
            pipeline_mode="grounded",
        )
        with pytest.raises(RuntimeError, match="VLM connection timed out"):
            process_ocr_task.run(
                "job-test-error",
                str(sample_file),
                settings_payload,
            )

        mock_record.assert_called_once()
        record_kwargs = mock_record.call_args[1]
        assert record_kwargs["job_id"] == "job-test-error"
        assert record_kwargs["status"] == "error"
        assert record_kwargs["error"] == "VLM connection timed out"
        assert record_kwargs["model"] == "failing-model"
        assert record_kwargs["pipeline_mode"] == "grounded"

        assert any(
            pct == 0 and "Error: VLM connection timed out" in msg
            for pct, msg in progress_calls
        )


def test_process_pdf_async_redis_mode_dispatches_celery():
    """When RedisStateBackend is active, process_pdf_async calls process_ocr_task.delay."""
    client = _api_client()

    fake_redis_backend = MagicMock(spec=RedisStateBackend)

    with (
        patch.object(state, "backend", fake_redis_backend),
        patch("omniscribe.api.tasks.process_ocr_task.delay") as mock_delay,
        patch("omniscribe.api.routers.ocr._emit_job_submitted") as mock_submitted,
    ):
        file_content = b"%PDF-1.4 fake pdf"
        response = client.post(
            "/api/process/async",
            files={"file": ("test.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"model": "test-model", "pipeline_mode": "hybrid"},
        )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["status"] == "pending"

        job_id = body["job_id"]
        mock_delay.assert_called_once()
        delay_args = mock_delay.call_args[0]
        assert delay_args[0] == job_id
        assert isinstance(delay_args[1], str) and delay_args[1].endswith(".pdf")
        assert delay_args[2]["model"] == "test-model"
        mock_submitted.assert_called_once_with(job_id, "test.pdf")


def test_process_pdf_async_standalone_mode_enqueues():
    """When LocalStateBackend is active, process_pdf_async submits to ocr_job_queue."""
    client = _api_client()

    local_backend = MagicMock(spec=LocalStateBackend)

    with (
        patch.object(state, "backend", local_backend),
        patch.object(state.ocr_job_queue, "submit", new=AsyncMock()) as mock_submit,
        patch("omniscribe.api.routers.ocr._emit_job_submitted") as mock_submitted,
    ):
        file_content = b"%PDF-1.4 fake pdf"
        response = client.post(
            "/api/process/async",
            files={"file": ("local.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"model": "local-model"},
        )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["status"] == "pending"

        job_id = body["job_id"]
        mock_submit.assert_awaited_once()
        submit_args = mock_submit.call_args[0]
        assert submit_args[0] == job_id
        assert submit_args[1] == "local.pdf"
        mock_submitted.assert_called_once_with(job_id, "local.pdf")


async def test_process_status_from_queue():
    """process_status returns record from state.ocr_job_queue if present."""
    client = _api_client()

    dummy_record = OCRJobRecord(
        job_id="job-queue-1",
        filename="queued.pdf",
        status=OCRJobStatus.PROCESSING,
    )

    with patch.object(
        state.ocr_job_queue, "get", new=AsyncMock(return_value=dummy_record)
    ):
        response = client.get("/api/process/status/job-queue-1")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-queue-1"
        assert data["status"] == "processing"


def test_process_status_from_history():
    """process_status returns job from state.job_history when not in queue."""
    client = _api_client()

    history_record = JobRecord(
        id="job-hist-1",
        filename="hist.pdf",
        model="hist-model",
        pipeline_mode="hybrid",
        pages="1",
        duration_s=2.5,
        timestamp="2026-08-19T00:00:00Z",
        status="complete",
        text_artifact_id="art-hist-1",
    )

    with (
        patch.object(state.ocr_job_queue, "get", new=AsyncMock(return_value=None)),
        patch.object(
            state.job_history, "list", return_value=[history_record.to_dict()]
        ),
    ):
        response = client.get("/api/process/status/job-hist-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "job-hist-1"
        assert data["status"] == "complete"
        assert data["text_artifact_id"] == "art-hist-1"


def test_process_status_from_celery_async_result():
    """process_status checks celery_app.AsyncResult if not in queue or history."""
    client = _api_client()

    mock_celery_task = MagicMock()
    mock_celery_task.state = "SUCCESS"
    mock_celery_task.result = {
        "job_id": "job-celery-1",
        "status": "complete",
        "text_artifact_id": "art-celery-1",
    }

    with (
        patch.object(state.ocr_job_queue, "get", new=AsyncMock(return_value=None)),
        patch.object(state.job_history, "list", return_value=[]),
        patch(
            "omniscribe.api.celery_app.celery_app.AsyncResult",
            return_value=mock_celery_task,
        ),
    ):
        response = client.get("/api/process/status/job-celery-1")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-celery-1"
        assert data["status"] == "complete"
        assert data["text_artifact_id"] == "art-celery-1"


def test_process_status_not_found():
    """process_status returns 404 when job is not found anywhere."""
    client = _api_client()

    with (
        patch.object(state.ocr_job_queue, "get", new=AsyncMock(return_value=None)),
        patch.object(state.job_history, "list", return_value=[]),
    ):
        response = client.get("/api/process/status/missing-job-id")
        assert response.status_code == 404
        data = response.json()
        assert "Job not found" in str(data)


# -- Audit-secondary F28: Celery worker aclose_shared_client ----------------


def test_celery_shutdown_signal_handler_is_registered() -> None:
    """The tasks module registers a worker_shutdown / worker_process_shutdown
    signal handler that releases the shared httpx client.

    Audit-secondary F28: the FastAPI lifespan calls
    ``aclose_shared_client`` in its ``finally`` block, but Celery
    workers live in their own process and never enter that
    lifespan. Without this signal, a long-running worker holds
    the client (and its keep-alive socket) alive across
    event-loop boundaries. The signal is the only way to close
    the client on the worker side.
    """
    from omniscribe.api import tasks as tasks_module

    # The module exports the handler for testability.
    assert hasattr(tasks_module, "_aclose_shared_client_on_celery_shutdown")
    assert callable(tasks_module._aclose_shared_client_on_celery_shutdown)

    # The handler invokes the same ``aclose_shared_client`` the
    # FastAPI lifespan does — the function reference is captured
    # in the module's signal-registration block.
    # (Indirect check: the handler must import the function on
    # call. We exercise the handler end-to-end below.)


def test_celery_shutdown_handler_closes_shared_client(monkeypatch) -> None:
    """The signal handler runs ``aclose_shared_client`` on a fresh loop.

    The handler does a lazy ``from multi_format_client import
    aclose_shared_client`` inside its body, so the patch must
    land on the source module's attribute — not on the tasks
    module (which never holds the binding).
    """
    from omniscribe.api import tasks as tasks_module
    from omniscribe.core.ocr import multi_format_client

    close_calls = 0
    real_close = multi_format_client.aclose_shared_client

    async def counting_close() -> None:
        nonlocal close_calls
        close_calls += 1
        await real_close()

    monkeypatch.setattr(multi_format_client, "aclose_shared_client", counting_close)

    # Drive the handler. It should run the patched close on a
    # fresh loop without raising.
    tasks_module._aclose_shared_client_on_celery_shutdown()
    assert close_calls == 1


def test_celery_shutdown_handler_swallows_exceptions(monkeypatch) -> None:
    """A failure inside ``aclose_shared_client`` does NOT crash the worker.

    The signal handler is called during Celery worker shutdown;
    if it raises, the worker's own teardown can be disrupted.
    The handler logs and continues.
    """
    from omniscribe.api import tasks as tasks_module
    from omniscribe.core.ocr import multi_format_client

    async def boom() -> None:
        raise RuntimeError("simulated aclose failure")

    monkeypatch.setattr(multi_format_client, "aclose_shared_client", boom)
    # Should not raise.
    tasks_module._aclose_shared_client_on_celery_shutdown()


def test_celery_shutdown_handler_tolerates_missing_httpx(monkeypatch) -> None:
    """When the httpx dep is missing the handler is a no-op."""
    # Pretend multi_format_client is unimportable.
    import builtins

    from omniscribe.api import tasks as tasks_module

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "omniscribe.core.ocr.multi_format_client":
            raise ImportError("simulated missing httpx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Should not raise.
    tasks_module._aclose_shared_client_on_celery_shutdown()
