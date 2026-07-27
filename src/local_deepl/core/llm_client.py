"""Thin async wrapper around the OpenAI SDK for OpenAI-compatible endpoints.

All LLM calls in the app funnel through :func:`call_llm` so callers never
touch the SDK directly. This keeps retry/timeout/error-handling policy in
one place and makes the rest of the codebase provider-agnostic.

Previously this module delegated to ``litellm``; it now uses the ``openai``
SDK directly (the only wire protocol we target is OpenAI-compatible).
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Cache one client per (api_base, api_key) pair so we reuse the
# underlying httpx connection pool across calls within a job.
_client_cache: dict[tuple[str, str], AsyncOpenAI] = {}


def _get_client(api_base: str, api_key: str) -> AsyncOpenAI:
    key = (api_base, api_key)
    client = _client_cache.get(key)
    if client is None:
        client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        _client_cache[key] = client
    return client


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
    """Make an asynchronous chat-completion call against an OpenAI-compatible endpoint."""
    client = _get_client(api_base, api_key)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout is not None:
        kwargs["timeout"] = timeout

    response = await client.chat.completions.create(**kwargs)
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""
