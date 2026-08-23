"""Process-route safety: partial failures, warning frames, error leakage.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from tests.api._safety_helpers import (
    _api_client,
    _pdf_upload,
    _process_form,
    _public_dns,
)


def test_process_surfaces_partial_page_failures_in_headers_and_history(tmp_path: Path):
    """A page whose OCR call raises must be reported in the response
    ``X-Failed-Pages`` header and the job-history record. The job
    status stays ``"complete"`` — the pipeline degrades gracefully and
    writes a PDF even with bad pages.

    The WebSocket frame shape is covered separately by
    ``test_websocket_manager_emits_warning_flag``; here we just confirm
    the router wires the partial-failure signal through.
    """

    class _FailingDummyPipeline:
        def __init__(self, *args, **kwargs):
            self.last_document_result = None
            self.last_failed_pages: list[int] = [1]  # 0-indexed page 1 fails

        async def run(self, input_path, output_path, **kwargs):
            on_warning = kwargs.get("on_warning")
            if on_warning is not None:
                await on_warning(1, RuntimeError("simulated page 1 failure"))
            Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF\n")
            return {0: ["page0"], 1: [], 2: ["page2"]}

    client = _api_client()

    with (
        patch("omniscribe.utils.security.socket.getaddrinfo", side_effect=_public_dns),
        patch(
            "omniscribe.api.services.ocr.pipeline_factory.OCRPipeline",
            _FailingDummyPipeline,
        ),
        patch("omniscribe.api.services.ocr.pipeline_factory.get_shared_hybrid_aligner"),
        patch("omniscribe.api.services.ocr.pipeline_factory.PDFHandler"),
    ):
        response = client.post(
            "/process",
            data=_process_form(),
            files={"file": _pdf_upload()},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Failed-Pages") == "1"

    # The job record reflects the partial failure.
    jobs = client.get("/api/jobs").json()
    assert jobs, "no job history recorded"
    latest = jobs[0]
    assert latest["status"] == "complete"
    assert latest["failed_pages"] == [1]


def test_websocket_manager_emits_warning_flag():
    """The ConnectionManager.send_progress path must serialize the
    ``warning`` flag in the WebSocket frame so the UI can render a
    partial-failure indicator without parsing the message text."""
    from omniscribe.api.routers.websocket import ConnectionManager

    sent_frames: list[dict] = []

    class _StubWS:
        async def accept(self):
            pass

        async def send_text(self, text: str) -> None:
            # NDJSON wire format: parse the JSON line and store the
            # dict so the existing assertion keeps working.
            sent_frames.append(json.loads(text))

        async def send_json(self, payload):
            # Kept for any path that bypasses the NDJSON envelope.
            sent_frames.append(payload)

    async def _drive():
        manager = ConnectionManager()
        await manager.connect(_StubWS(), "abcd" * 8, "efgh" * 8)  # 32-char tokens
        await manager.send_progress("abcd" * 8, "all good", 50, stage="ocr")
        await manager.send_progress(
            "abcd" * 8,
            "OCR failed for page 7: TimeoutError",
            0,
            stage="ocr",
            warning=True,
        )

    asyncio.run(_drive())

    assert sent_frames[0] == {
        "status": "all good",
        "percent": 50,
        "stage": "ocr",
    }
    assert sent_frames[1] == {
        "status": "OCR failed for page 7: TimeoutError",
        "percent": 0,
        "stage": "ocr",
        "warning": True,
    }


def test_translate_error_response_does_not_expose_internal_exception():
    async def fail_completion(*args, **kwargs):
        raise RuntimeError("secret-api-key leaked by provider")

    client = _api_client()
    with (
        patch("omniscribe.utils.security.socket.getaddrinfo", side_effect=_public_dns),
        patch("omniscribe.api.services.ai.call_llm", fail_completion),
    ):
        response = client.post(
            "/api/translate",
            json={
                "text": "hello",
                "target_language": "Spanish",
                "api_base": "http://api.openai.com/v1",
                "model": "openai/test-model",
                "api_key": "secret-api-key",
            },
        )

    assert response.status_code == 500
    payload = json.dumps(response.json())
    assert "secret-api-key" not in payload
    assert "provider" not in payload


def test_static_js_has_no_html_injection_sinks():
    static_js = Path("src/omniscribe/static/js")
    for path in static_js.glob("*.js"):
        source = path.read_text(encoding="utf-8")
        assert "innerHTML" not in source
        assert "insertAdjacentHTML" not in source
        assert "outerHTML" not in source
