"""Comprehensive tests for multi-format OpenAI and provider model discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from omniscribe.api.schemas.requests import ProviderConfig, ProviderFormatEnum
from omniscribe.api.services.provider_manager import (
    ProviderManager,
    extract_model_ids_from_response,
    reset_provider_manager,
)
from omniscribe.server import create_app

# ---------------------------------------------------------------------------
# Unit tests for extract_model_ids_from_response
# ---------------------------------------------------------------------------


def test_extract_model_ids_openai_standard():
    payload = {
        "object": "list",
        "data": [
            {"id": "gpt-4o", "object": "model", "created": 1715368132},
            {"id": "gpt-4o-mini", "object": "model", "created": 1721297593},
        ],
    }
    extracted = extract_model_ids_from_response(payload)
    assert extracted == ["gpt-4o", "gpt-4o-mini"]


def test_extract_model_ids_ollama_tags():
    payload = {
        "models": [
            {
                "name": "llama3.2:latest",
                "model": "llama3.2:latest",
                "modified_at": "2024-10-01T12:00:00Z",
            },
            {
                "name": "qwen2.5:7b",
                "model": "qwen2.5:7b",
                "modified_at": "2024-10-01T12:00:00Z",
            },
        ]
    }
    extracted = extract_model_ids_from_response(payload)
    assert extracted == ["llama3.2:latest", "qwen2.5:7b"]


def test_extract_model_ids_anthropic():
    payload = {
        "data": [
            {
                "id": "claude-3-5-sonnet-20241022",
                "display_name": "Claude 3.5 Sonnet",
                "type": "model",
            },
            {
                "id": "claude-3-5-haiku-20241022",
                "display_name": "Claude 3.5 Haiku",
                "type": "model",
            },
        ],
        "has_more": False,
    }
    extracted = extract_model_ids_from_response(payload)
    assert extracted == ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]


def test_extract_model_ids_top_level_list_and_plain_strings():
    payload_dicts = [{"id": "model-a"}, {"name": "model-b"}]
    assert extract_model_ids_from_response(payload_dicts) == ["model-a", "model-b"]

    payload_strings = ["model-1", "model-2", "model-1"]
    assert extract_model_ids_from_response(payload_strings) == ["model-1", "model-2"]


def test_extract_model_ids_custom_results():
    payload = {
        "result": [
            {"model_id": "meta-llama/llama-3-8b"},
            {"model": "mistralai/mistral-7b"},
        ]
    }
    assert extract_model_ids_from_response(payload) == [
        "meta-llama/llama-3-8b",
        "mistralai/mistral-7b",
    ]


def test_extract_model_ids_empty_or_malformed():
    assert extract_model_ids_from_response(None) == []
    assert extract_model_ids_from_response({}) == []
    assert extract_model_ids_from_response([]) == []
    assert extract_model_ids_from_response({"unknown_key": 123}) == []


# ---------------------------------------------------------------------------
# ProviderManager candidate URL & model discovery tests
# ---------------------------------------------------------------------------


def test_provider_manager_candidate_url_fallback(tmp_path: Path):
    """Test that if primary /v1/models returns 404, fallback to /models succeeds."""
    config_file = tmp_path / "providers.yaml"
    pm = ProviderManager(config_path=config_file)

    p = ProviderConfig(
        id="custom-server",
        display_name="Custom Server",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:8000",
        requires_auth=False,
        models=["fallback-1"],
    )
    pm.save_provider(p)

    def fake_get(url, headers=None):
        mock_resp = MagicMock()
        if url.endswith("/v1/models"):
            mock_resp.status_code = 404
        elif url.endswith("/models"):
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"data": [{"id": "remote-model-1"}]}
        else:
            mock_resp.status_code = 404
        return mock_resp

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        models = pm.list_provider_models("custom-server")
        assert "remote-model-1" in models


def test_provider_manager_anthropic_headers(tmp_path: Path):
    """Test that Anthropic-compatible provider sends x-api-key and anthropic-version."""
    config_file = tmp_path / "providers.yaml"
    pm = ProviderManager(config_path=config_file)
    p = pm.get_provider("anthropic")
    assert p is not None
    p.api_key = "test-anthropic-key"
    pm.save_provider(p)

    sent_headers: dict[str, str] = {}

    def fake_get(url, headers=None):
        if headers:
            sent_headers.update(headers)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "claude-test"}]}
        return mock_resp

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        models = pm.list_provider_models("anthropic")
        assert "claude-test" in models
        assert "x-api-key" in sent_headers
        assert sent_headers.get("anthropic-version") == "2023-06-01"


# ---------------------------------------------------------------------------
# API Endpoint Integration Tests (GET /api/models/*)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from omniscribe.utils.security import SSRFCheckResult

    reset_provider_manager()
    allow_mock = AsyncMock(
        return_value=SSRFCheckResult(allowed=True, resolved_ip="127.0.0.1", reason=None)
    )
    monkeypatch.setattr("omniscribe.utils.security.is_ssrf_target", allow_mock)
    # Phase C / Task 9: ``/api/models*`` was extracted into
    # ``routers/models.py``. The handlers look up ``is_ssrf_target`` via
    # that module's globals now, so the mock target moves with them.
    monkeypatch.setattr("omniscribe.api.routers.config.is_ssrf_target", allow_mock)
    monkeypatch.setattr("omniscribe.api.routers.models.is_ssrf_target", allow_mock)
    monkeypatch.setattr("omniscribe.api.routers.providers.is_ssrf_target", allow_mock)
    app = create_app()
    return TestClient(app)


def test_get_api_models_endpoint(client: TestClient):
    """Test GET /api/models returns models discovered from configured endpoint."""
    with patch(
        "omniscribe.api.routers.models._discover_models_for_endpoint",
        new=AsyncMock(return_value=["gpt-4o", "gpt-4o-mini"]),
    ):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "gpt-4o" in data["models"]


def test_get_api_models_ocr_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Test GET /api/models/ocr endpoint."""
    with patch(
        "omniscribe.api.routers.models._discover_models_for_endpoint",
        new=AsyncMock(return_value=["qwen2.5-vl-72b", "olmocr-2"]),
    ):
        resp = client.get("/api/models/ocr")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "qwen2.5-vl-72b" in data["models"]


def test_get_api_models_translation_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Test GET /api/models/translation endpoint."""
    with patch(
        "omniscribe.api.routers.models._discover_models_for_endpoint",
        new=AsyncMock(return_value=["gpt-4o-mini", "llama-3.3-70b"]),
    ):
        resp = client.get("/api/models/translation")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "llama-3.3-70b" in data["models"]


def test_get_api_models_transcription_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Test GET /api/models/transcription endpoint."""
    with patch(
        "omniscribe.api.services.provider_manager.extract_model_ids_from_response",
        return_value=["whisper-1", "whisper-large-v3"],
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "whisper-large-v3"}]}

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            resp = client.get("/api/models/transcription")
            assert resp.status_code == 200
            data = resp.json()
            assert "models" in data
            assert "whisper-large-v3" in data["models"]


def test_get_provider_models_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """Test GET /api/providers/{provider_id}/models endpoint."""
    from omniscribe.api.services.provider_manager import get_provider_manager

    mgr = get_provider_manager()
    monkeypatch.setattr(
        mgr,
        "async_list_provider_models",
        AsyncMock(return_value=["test-provider-model"]),
    )

    resp = client.get("/api/providers/openai/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == ["test-provider-model"]


# ---------------------------------------------------------------------------
# 422 Prevention & Request Resilience Tests
# ---------------------------------------------------------------------------


def test_process_settings_empty_api_key_defaults_to_lm_studio():
    from omniscribe.api.schemas.requests import (
        DenseMode,
        PipelineMode,
        ProcessSettings,
        SpellcheckMode,
    )

    # Empty string api_key
    settings = ProcessSettings(
        api_base="http://localhost:1234/v1",
        api_key="",
        model="qwen2.5-vl-72b",
        pipeline_mode=PipelineMode.HYBRID,
        dpi=200,
        concurrency=2,
        dense_mode=DenseMode.AUTO,
        dense_threshold=60,
        refine=True,
        max_image_dim=1024,
        self_correction=False,
        binarize=False,
        dual_engine=False,
        spellcheck=SpellcheckMode.NONE,
        cross_page=False,
        preprocess_pages=False,
        orientation_detection=False,
        deskew=False,
        denoise=False,
        normalize_contrast=False,
        crop_cleanup=False,
        quality_routing=False,
    )
    assert settings.api_key == "lm-studio"


def test_config_update_accepts_empty_api_key_and_nested_namespaces():
    from omniscribe.api.schemas.requests import ConfigUpdate

    update = ConfigUpdate.model_validate(
        {
            "api_key": "",
            "ocr": {
                "ocr_api_base": "http://localhost:1234/v1",
                "ocr_model": "test-model",
            },
            "translation": {"sliding_window_words": 100},
        }
    )
    assert update.api_key == ""
    assert update.ocr is not None and update.ocr["ocr_model"] == "test-model"


def test_ocr_config_update_accepts_document_processors():
    from omniscribe.api.schemas.requests import OcrConfigUpdate

    update = OcrConfigUpdate.model_validate(
        {
            "ocr_api_base": "http://localhost:1234/v1",
            "document_processors": ["reading_order", "table_extraction"],
        }
    )
    assert update.document_processors == ["reading_order", "table_extraction"]


def test_transcription_config_update_accepts_faster_whisper():
    from omniscribe.api.schemas.requests import (
        TranscriptionConfigUpdate,
        TranscriptionEngineType,
    )

    update = TranscriptionConfigUpdate.model_validate(
        {
            "engine": "faster-whisper",
            "temperature": 0.2,
        }
    )
    assert update.engine == TranscriptionEngineType.FASTER_WHISPER_DASH
