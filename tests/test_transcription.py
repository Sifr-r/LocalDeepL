from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import config, transcription
from omniscribe.api.services.security_middleware import BearerAuthMiddleware
from omniscribe.core.transcription import (
    AudioValidationError,
    GenericAudioAPIEngine,
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
    WhisperLocalEngine,
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


@pytest.fixture
def _cross_worker_config_store():
    """Install a cross-worker-visible in-memory config store for tests
    that exercise the transcription /api/config routes.

    The default :class:`LocalStateBackend` ships with a per-process
    in-memory config store, which the config router now refuses with
    a 503 (issue H1). Transcription tests that POST to
    ``/api/config/transcription`` need the cross-worker path active;
    this fixture flips the test-only flag on the store, then restores
    the original on teardown.
    """
    from omniscribe.api.routers import state as router_state
    from omniscribe.api.services.config_store import InMemoryConfigStore

    original = router_state.backend.config_store
    store = InMemoryConfigStore(initial=dict(config._config))
    store._cross_worker_visible = True
    router_state.backend.config_store = store
    try:
        yield store
    finally:
        router_state.backend.config_store = original
        config._config.clear()
        config._config.update(
            {
                "api_base": "https://api.openai.com/v1",
                "api_key": "lm-studio",
                "model": "openai/gpt-oss-20b",
            }
        )


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
        wav_header = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        files = {"file": ("test.wav", wav_header, "audio/wav")}
        response = client.post(
            "/api/transcribe", files=files, data={"model": "whisper-1"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Sample transcribed speech text"
    assert data["language"] == "en"
    assert "text_artifact_id" in data
    assert "text_artifact_token" in data


def test_transcription_config_endpoints(_cross_worker_config_store):
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


def test_config_response_redacts_api_key(_cross_worker_config_store):
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


def test_whisper_local_engine_missing_dependency():
    """Missing faster_whisper dependency raises a 503 TranscriptionError."""
    engine = WhisperLocalEngine()
    with patch.dict("sys.modules", {"faster_whisper": None}):
        with pytest.raises(TranscriptionError) as exc_info:
            engine._get_model()
        assert exc_info.value.status_code == 503
        assert "transcription" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_whisper_local_engine_mock_transcribe():
    """Mock faster_whisper transcription returns segment text and language."""
    engine = WhisperLocalEngine(model_size_or_path="base", device="cpu")

    mock_word = SimpleNamespace(word="OmniScribe", start=0.0, end=1.5, probability=0.98)
    mock_segment = SimpleNamespace(
        id=0,
        start=0.0,
        end=2.0,
        text="  OmniScribe voice transcription  ",
        avg_logprob=-0.15,
        words=[mock_word],
    )
    mock_info = SimpleNamespace(language="en", duration=2.0)

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)
    engine._model = mock_model

    result = await engine.transcribe(b"fake audio data", filename="test.wav")
    assert result.text == "OmniScribe voice transcription"
    assert result.language == "en"
    assert result.duration == 2.0
    assert len(result.segments) == 1
    assert result.segments[0].text == "OmniScribe voice transcription"
    assert result.segments[0].confidence == -0.15
    assert len(result.segments[0].words) == 1
    assert result.segments[0].words[0]["word"] == "OmniScribe"


@pytest.mark.asyncio
async def test_whisper_local_engine_temp_file_unlinked_in_finally():
    """Verify temp files created during transcription are deleted in finally block."""
    engine = WhisperLocalEngine(model_size_or_path="base")
    mock_segment = SimpleNamespace(
        id=0, start=0.0, end=1.0, text="Test", avg_logprob=-0.1, words=[]
    )
    mock_info = SimpleNamespace(language="en", duration=1.0)

    mock_model = MagicMock()
    captured_paths: list[str] = []

    def _side_effect(path, **kwargs):
        captured_paths.append(path)
        # Verify the temp file exists on disk while transcribe is running
        assert Path(path).is_file()
        return ([mock_segment], mock_info)

    mock_model.transcribe.side_effect = _side_effect
    engine._model = mock_model

    # 1. Success case: temp file is deleted
    await engine.transcribe(b"audio-bytes-success", filename="test_success.wav")
    assert len(captured_paths) == 1
    assert not Path(captured_paths[0]).exists()

    # 2. Error case: temp file is deleted even when transcribe raises
    error_paths: list[str] = []

    def _failing_side_effect(path, **kwargs):
        error_paths.append(path)
        assert Path(path).is_file()
        raise RuntimeError("Transcribe backend error")

    mock_model.transcribe.side_effect = _failing_side_effect
    with pytest.raises(RuntimeError, match="Transcribe backend error"):
        await engine.transcribe(b"audio-bytes-error", filename="test_error.wav")
    assert len(error_paths) == 1
    assert not Path(error_paths[0]).exists()
