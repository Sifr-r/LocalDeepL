from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import config, extraction, translation
from omniscribe.api.services.envelope import register_envelope_handlers
from omniscribe.utils.security import SSRFCheckResult


def _api_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(config.router)
    app.include_router(translation.router)
    app.include_router(extraction.router)
    return TestClient(app)


def test_translate_provider_error_response_is_stable():
    async def fail_completion(*args, **kwargs):
        raise RuntimeError("secret-api-key leaked by provider")

    client = _api_client()
    with (
        patch(
            "omniscribe.api.services.ai.is_ssrf_target",
            new=AsyncMock(
                return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
            ),
        ),
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


def test_extract_invalid_json_returns_empty_object():
    async def invalid_json_completion(*args, **kwargs):
        return "not valid json"

    client = _api_client()
    with (
        patch(
            "omniscribe.api.services.ai.is_ssrf_target",
            new=AsyncMock(
                return_value=SSRFCheckResult(allowed=True, resolved_ip="203.0.113.1")
            ),
        ),
        patch("omniscribe.api.services.ai.call_llm", invalid_json_completion),
    ):
        response = client.post(
            "/api/extract",
            json={
                "text": "Invoice total is 10 USD.",
                "template": "invoice",
                "api_base": "http://api.openai.com/v1",
                "model": "openai/test-model",
                "api_key": "test-key",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"extracted_data": {}}


def test_translate_blocks_unsafe_api_base():
    client = _api_client()
    with (
        patch.dict("os.environ", {"ALLOW_SSRF_LOCAL": "false"}, clear=True),
        patch("omniscribe.api.services.ai._complete_text") as completion,
    ):
        response = client.post(
            "/api/translate",
            json={
                "text": "hello",
                "target_language": "Spanish",
                "api_base": "http://127.0.0.1:1234/v1",
                "model": "openai/test-model",
                "api_key": "test-key",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ssrf_blocked"
    assert "ALLOW_SSRF_LOCAL" in response.json()["detail"]
    completion.assert_not_called()


def test_translation_status_success_shape():
    class _Task:
        state = "SUCCESS"
        info = {"progress": 100, "status": "Complete"}

        def get(self):
            return {"document_id": "doc-1", "translated_text": "hola"}

    client = _api_client()
    with (
        patch("omniscribe.api.celery_app.celery_app.AsyncResult", return_value=_Task()),
    ):
        response = client.get("/api/translate/status/job-1")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "state": "SUCCESS",
        "info": {"progress": 100, "status": "Complete"},
        "result": {"document_id": "doc-1", "translated_text": "hola"},
    }
