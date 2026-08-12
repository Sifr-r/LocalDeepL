"""Unit tests for multi_format_client and llm_client integration."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from omniscribe.api.schemas.requests import ProviderConfig, ProviderFormatEnum
from omniscribe.core.llm_client import call_llm, call_vlm
from omniscribe.core.ocr.exceptions import LLMCallError
from omniscribe.core.ocr.multi_format_client import complete_vlm_prompt


@pytest.fixture
def openai_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-openai",
        display_name="Test OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://mock-llm.local/v1",
        api_key="test-sk-key",
        models=["gpt-4o"],
    )


@pytest.fixture
def anthropic_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-anthropic",
        display_name="Test Anthropic",
        format=ProviderFormatEnum.ANTHROPIC_COMPATIBLE,
        api_url="http://mock-anthropic.local",
        api_key="test-anthropic-key",
        models=["claude-3-5-sonnet"],
    )


@pytest.fixture
def ollama_config() -> ProviderConfig:
    return ProviderConfig(
        id="test-ollama",
        display_name="Test Ollama",
        format=ProviderFormatEnum.OLLAMA_COMPATIBLE,
        api_url="http://mock-ollama.local:11434",
        requires_auth=False,
        models=["llama3.2-vision"],
    )


async def test_openai_compatible_dispatch(openai_config: ProviderConfig) -> None:
    expected_resp = {"choices": [{"message": {"content": "Extracted OCR text"}}]}

    async def mock_post(url: str, json: dict, headers: dict):
        assert "chat/completions" in url
        assert headers["Authorization"] == "Bearer test-sk-key"
        assert json["model"] == "gpt-4o"
        assert json["messages"][0]["role"] == "user"
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            openai_config,
            prompt="OCR prompt text",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Extracted OCR text"


async def test_anthropic_compatible_dispatch(anthropic_config: ProviderConfig) -> None:
    expected_resp = {"content": [{"type": "text", "text": "Anthropic response text"}]}

    async def mock_post(url: str, json: dict, headers: dict):
        assert "messages" in url
        assert headers["x-api-key"] == "test-anthropic-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert json["model"] == "claude-3-5-sonnet"
        assert json["messages"][0]["content"][0]["type"] == "image"
        assert json["messages"][0]["content"][0]["source"]["data"] == "aW1hZ2VfZGF0YQ=="
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            anthropic_config,
            prompt="Transcribe page",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Anthropic response text"


async def test_ollama_compatible_dispatch(ollama_config: ProviderConfig) -> None:
    expected_resp = {"message": {"content": "Ollama extracted text"}}

    async def mock_post(url: str, json: dict, headers: dict):
        assert "api/chat" in url
        assert json["model"] == "llama3.2-vision"
        assert json["messages"][0]["images"] == ["aW1hZ2VfZGF0YQ=="]
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await complete_vlm_prompt(
            ollama_config,
            prompt="Read this image",
            image_base64="aW1hZ2VfZGF0YQ==",
        )
        assert result == "Ollama extracted text"


async def test_non_200_raises_llm_call_error(openai_config: ProviderConfig) -> None:
    async def mock_post(url: str, json: dict, headers: dict):
        return httpx.Response(400, text="Bad Request: Model not found")

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(LLMCallError) as exc_info:
            await complete_vlm_prompt(openai_config, prompt="Hello")
        assert "400" in str(exc_info.value)


async def test_call_vlm_wrapper(openai_config: ProviderConfig) -> None:
    expected_resp = {"choices": [{"message": {"content": "VLM wrapper output"}}]}

    async def mock_post(url: str, json: dict, headers: dict):
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await call_vlm("Recognize this", provider_config=openai_config)
        assert res == "VLM wrapper output"


async def test_call_llm_wrapper_with_messages() -> None:
    expected_resp = {"choices": [{"message": {"content": "LLM wrapper output"}}]}

    async def mock_post(url: str, json: dict, headers: dict):
        return httpx.Response(200, json=expected_resp)

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await call_llm(
            api_base="http://localhost:1234/v1",
            api_key="key",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Translate this sentence"}],
        )
        assert res == "LLM wrapper output"
