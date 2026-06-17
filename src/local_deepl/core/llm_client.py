from __future__ import annotations

import logging
from typing import Any

import litellm

from local_deepl.utils.litellm_provider import resolve_custom_provider

logger = logging.getLogger(__name__)


async def call_llm(
    *,
    model: str,
    api_base: str,
    api_key: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.1,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    """Make an asynchronous completion call using LiteLLM."""
    custom_provider = resolve_custom_provider(model)

    response = await litellm.acompletion(
        model=model,
        custom_llm_provider=custom_provider,
        api_base=api_base,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        messages=messages,
    )
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""
