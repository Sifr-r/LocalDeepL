"""Async LLM completion client for OmniScribe.

Directs call_llm / call_vlm to use the active provider configuration from ProviderManager
and multi_format_client for completion dispatch across OpenAI, Anthropic, and Ollama formats.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from omniscribe.api.schemas import ProviderConfig

from omniscribe.core.ocr.multi_format_client import complete_vlm_prompt

logger = logging.getLogger(__name__)


def _extract_prompt_and_image(
    messages: list[dict[str, Any]] | None,
    prompt: str | None = None,
    image_base64: str | None = None,
) -> tuple[str, str | None]:
    """Parse messages payload or direct args into text prompt and optional image_base64 string."""
    extracted_prompt = prompt or ""
    extracted_image = image_base64

    if messages:
        p_parts: list[str] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                p_parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        p_parts.append(item)
                    elif isinstance(item, dict):
                        item_type = item.get("type")
                        if item_type == "text":
                            text_val = item.get("text")
                            if text_val:
                                p_parts.append(str(text_val))
                        elif item_type == "image_url":
                            img_obj = item.get("image_url")
                            url_str = ""
                            if isinstance(img_obj, str):
                                url_str = img_obj
                            elif isinstance(img_obj, dict):
                                url_str = str(img_obj.get("url", ""))
                            if url_str and extracted_image is None:
                                if "base64," in url_str:
                                    extracted_image = url_str.split("base64,", 1)[1]
                                else:
                                    extracted_image = url_str
                        elif item_type == "image":
                            src = item.get("source", {})
                            if isinstance(src, dict) and extracted_image is None:
                                extracted_image = str(src.get("data", ""))
        if p_parts and not extracted_prompt:
            extracted_prompt = "\n".join(p_parts)

    return extracted_prompt, extracted_image


async def call_vlm(
    prompt: str,
    image_base64: str | None = None,
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    provider_config: ProviderConfig | None = None,
) -> str:
    """Make an asynchronous VLM call using active ProviderManager configuration or explicit settings."""
    if provider_config is None:
        if api_base:
            from omniscribe.api.schemas import ProviderConfig, ProviderFormatEnum

            provider_config = ProviderConfig(
                id="custom",
                display_name="Custom",
                format=ProviderFormatEnum.OPENAI_COMPATIBLE,
                api_url=api_base,
                api_key=api_key,
                models=[model] if model else [],
            )
        else:
            from omniscribe.api.services.provider_manager import get_provider_manager

            mgr = get_provider_manager()
            provider_config = mgr.get_active_provider()

    return await complete_vlm_prompt(
        provider_config=provider_config,
        prompt=prompt,
        image_base64=image_base64,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def call_llm(
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    prompt: str | None = None,
    image_base64: str | None = None,
    temperature: float = 0.1,
    max_tokens: int | None = None,
    timeout: float | None = None,
    provider_config: ProviderConfig | None = None,
) -> str:
    """Make an asynchronous LLM chat completion call using active ProviderManager config."""
    extracted_prompt, extracted_image = _extract_prompt_and_image(
        messages=messages,
        prompt=prompt,
        image_base64=image_base64,
    )

    if provider_config is None:
        if api_base:
            from omniscribe.api.schemas import ProviderConfig, ProviderFormatEnum

            provider_config = ProviderConfig(
                id="custom",
                display_name="Custom",
                format=ProviderFormatEnum.OPENAI_COMPATIBLE,
                api_url=api_base,
                api_key=api_key,
                models=[model] if model else [],
            )
        else:
            from omniscribe.api.services.provider_manager import get_provider_manager

            mgr = get_provider_manager()
            provider_config = mgr.get_active_provider()

    return await complete_vlm_prompt(
        provider_config=provider_config,
        prompt=extracted_prompt,
        image_base64=extracted_image,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens or 4096,
    )


__all__ = [
    "call_llm",
    "call_vlm",
]
