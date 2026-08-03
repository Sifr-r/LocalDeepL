from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import config, transcription
from omniscribe.api.services.security_middleware import BearerAuthMiddleware
from omniscribe.core.transcription import (
    AudioValidationError,
    GenericAudioAPIEngine,
    TranscriptionResult,
    TranscriptionSegment,
    get_transcription_engine,
    validate_audio_input,
)

# Test fixture constants (not real credentials)
TEST_FAKE_API_KEY = "test-key"
TEST_DUMMY_MODEL = "whisper-large-v3"
TEST_PLACEHOLDER_TOKEN = "super-secret-transcription-token-1234567890"
TEST_FAKE_SK_KEY = "sk-test-transcription-key-123456789"


def test_validate_audio_input_success():
    ext = validate_audio_input("speech.mp3", content_type="audio/mpeg", file_size=1024)
    assert ext == ".mp3"


def test_validate_audio_input_invalid_extension():
    with pytest.raises(AudioValidationError) as exc_info:
        validate_audio_input(
            "document.pdf", content_type="application/pdf", file_size=1024
        )
    assert exc_info.value.status_code == 415


def test_validate_audio_input_oversized():
    with pytest.raises(AudioValidationError) as exc_info:
        validate_audio_input("audio.wav", file_size=1000, max_bytes=500)
    assert exc_info.value.status_code == 413


def test_transcription_result_to_document_result():
    segments = [
        TranscriptionSegment(
            id=0, start=0.0, end=2.5, text="Hello world", confidence=0.98
        ),
        TranscriptionSegment(
            id=1, start=2.5, end=5.0, text="OmniScribe voice test", confidence=0.95
        ),
    ]
    result = TranscriptionResult(
        text="Hello world OmniScribe voice test",
        language="en",
        duration=5.0,
        segments=segments,
    )

    doc_result = result.to_document_result()
    assert len(doc_result.pages) == 1
    page = doc_result.pages[0]
    assert len(page.blocks) == 2
    assert page.blocks[0].text == "Hello world"
    assert page.blocks[0].metadata["start_time"] == 0.0
    assert page.blocks[0].metadata["end_time"] == 2.5
    assert page.blocks[1].text == "OmniScribe voice test"


def test_factory_get_transcription_engine():
    api_engine = get_transcription_engine(
        engine_type="api",
        model="custom-model",
        api_base="http://localhost:8000/v1",
        api_key=TEST_FAKE_API_KEY,
    )
    assert isinstance(api_engine, GenericAudioAPIEngine)
    assert api_engine.model == "custom-model"
    assert api_engine.api_key == TEST_FAKE_API_KEY


@pytest.mark.asyncio
async def test_generic_audio_api_engine_transcribe_mock():
    engine = GenericAudioAPIEngine(
        model=TEST_DUMMY_MODEL, api_base="http://fake-api/v1", api_key=TEST_FAKE_API_KEY
    )

    mock_json = {
        "text": "Testing generic audio API engine",
        "language": "english",
        "duration": 3.2,
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.2,
                "text": "Testing generic audio API engine",
                "avg_logprob": -0.1,
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_json

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=MockResponse())):
        res = await engine.transcribe(b"fake-audio-bytes", filename="sample.wav")
        assert res.text == "Testing generic audio API engine"
        assert res.language == "english"
        assert len(res.segments) == 1


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(config.router)
    app.include_router(transcription.router)
    return app


def test_transcribe_endpoint_success():
    app = _create_test_app()
    client = TestClient(app)

    mock_result = TranscriptionResult(
        text="Sample transcribed speech text",
        language="en",
        duration=4.0,
        segments=[
            TranscriptionSegment(
                id=0, start=0.0, end=4.0, text="Sample transcribed speech text"
            )
        ],
    )

    with patch(
        "omniscribe.core.transcription.api_engine.GenericAudioAPIEngine.transcribe",
        new=AsyncMock(return_value=mock_result),
    ):
        files = {"file": ("test.wav", b"dummy wav content", "audio/wav")}
        response = client.post(
            "/api/transcribe", files=files, data={"model": "whisper-1"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Sample transcribed speech text"
    assert data["language"] == "en"
    assert "text_artifact_id" in data
    assert "text_artifact_token" in data


def test_transcription_config_endpoints():
    app = _create_test_app()
    client = TestClient(app)

    get_resp = client.get("/api/config/transcription")
    assert get_resp.status_code == 200
    assert get_resp.json()["transcription_model"] is not None

    post_resp = client.post(
        "/api/config/transcription",
        json={
            "model": "gpt-4o-audio-preview",
            "transcription_api_key": TEST_FAKE_SK_KEY,
            "engine": "api",
        },
    )
    assert post_resp.status_code == 200
    updated = post_resp.json()
    assert updated["transcription_model"] == "gpt-4o-audio-preview"
    assert "..." in updated["transcription_api_key"]


def test_config_response_redacts_api_key():
    """Ensure POST /api/config/transcription masks the API key in response."""
    app = _create_test_app()
    client = TestClient(app)
    response = client.post(
        "/api/config/transcription",
        json={
            "model": "gpt-4o-audio",
            "transcription_api_key": "my-real-secret-key-xyz123",
            "engine": "api",
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Verify the key is redacted in the response
    assert "my-real-secret-key" not in data.get("transcription_api_key", "")
    assert "..." in data.get("transcription_api_key", "")


def test_transcription_auth_middleware_enforcement():
    app = FastAPI()
    app.add_middleware(
        BearerAuthMiddleware,
        expected_token=None,
        transcription_token=TEST_PLACEHOLDER_TOKEN,
    )
    app.include_router(transcription.router)
    client = TestClient(app)

    # Missing token -> 401
    resp_unauth = client.get("/api/config/transcription")
    assert resp_unauth.status_code == 401

    # Correct token -> 200
    resp_auth = client.get(
        "/api/config/transcription",
        headers={"Authorization": f"Bearer {TEST_PLACEHOLDER_TOKEN}"},
    )
    assert resp_auth.status_code == 200
