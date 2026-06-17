"""Tests for `utils/litellm_provider` — provider prefix detection."""

from __future__ import annotations

import pytest

from local_deepl.utils.litellm_provider import (
    LITELLM_KNOWN_PREFIXES,
    resolve_custom_provider,
)


@pytest.mark.parametrize(
    "model", [f"{prefix}model-x" for prefix in LITELLM_KNOWN_PREFIXES]
)
def test_resolve_custom_provider_returns_none_for_known_prefixes(model: str) -> None:
    """Models with a known LiteLLM provider prefix get the None (auto) provider."""
    assert resolve_custom_provider(model) is None


def test_resolve_custom_provider_returns_openai_for_bare_model() -> None:
    """Bare model names default to the openai provider so local OpenAI-compatible endpoints work."""
    assert resolve_custom_provider("custom-local-model") == "openai"


def test_resolve_custom_provider_returns_openai_for_unknown_prefix() -> None:
    """Unknown vendor prefixes (e.g. 'foo/bar') still get openai as a safe default."""
    assert resolve_custom_provider("foo/some-model") == "openai"


def test_resolve_custom_provider_is_case_sensitive() -> None:
    """LiteLLM prefixes are case-sensitive — uppercase prefixes fall through to the default."""
    assert resolve_custom_provider("OpenAI/gpt-4") == "openai"
