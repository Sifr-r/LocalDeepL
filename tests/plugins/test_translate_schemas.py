"""Unit tests for translate plugin request schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from omniscribe.plugins.translate.schemas import (
    AsyncTranslationRequest,
    NllbRequest,
    TranslationRequest,
)


def test_translation_request_defaults() -> None:
    body = TranslationRequest()
    assert body.text == ""
    assert body.text_artifact_id is None
    assert body.text_artifact_token is None
    assert body.target_language == "Spanish"
    assert body.glossary is None
    assert body.glossary_text is None
    assert body.sliding_window_words == 80
    assert body.dual_translate is False
    assert body.second_api_base is None
    assert body.second_api_key is None
    assert body.second_model is None
    assert body.api_base is None
    assert body.api_key is None
    assert body.model is None


def test_translation_request_rejects_extra_fields() -> None:
    # The old contract was extra="forbid"; the client never sends
    # prompt_template/channel_id (notifier leaves them None).
    with pytest.raises(ValidationError):
        TranslationRequest(text="x", prompt_template="y")


def test_target_language_bounds() -> None:
    assert TranslationRequest(target_language="French").target_language == "French"
    with pytest.raises(ValidationError):
        TranslationRequest(target_language="")


def test_target_language_max_length() -> None:
    with pytest.raises(ValidationError):
        TranslationRequest(target_language="x" * 81)


def test_sliding_window_words_bounds() -> None:
    assert TranslationRequest(sliding_window_words=0).sliding_window_words == 0
    assert TranslationRequest(sliding_window_words=2000).sliding_window_words == 2000
    with pytest.raises(ValidationError):
        TranslationRequest(sliding_window_words=2001)
    with pytest.raises(ValidationError):
        TranslationRequest(sliding_window_words=-1)


def test_glossary_max_entries() -> None:
    entries = [{"source": "a", "target": "b"}] * 1000
    assert TranslationRequest(glossary=entries).glossary == entries
    with pytest.raises(ValidationError):
        TranslationRequest(glossary=entries + entries)


def test_strings_are_trimmed() -> None:
    body = TranslationRequest(text="  hello  ", api_base="  http://x  ")
    assert body.text == "hello"
    assert body.api_base == "http://x"


def test_async_request_requires_and_bounds_artifact_pair() -> None:
    body = AsyncTranslationRequest(
        text_artifact_id="a" * 32, text_artifact_token="t" * 43
    )
    assert body.target_language == "English"
    assert body.channel_id is None
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(text_artifact_id="short", text_artifact_token="t" * 43)
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(text_artifact_id="a" * 32, text_artifact_token="t" * 31)
    with pytest.raises(ValidationError):
        AsyncTranslationRequest(
            text_artifact_id="a" * 32, text_artifact_token="t" * 257
        )


def test_async_request_accepts_text_and_channel_id_for_tolerance() -> None:
    # The client posts the same toJson for async as for sync; text and
    # channel_id are accepted and ignored (spec: tolerant superset).
    body = AsyncTranslationRequest(
        text="ignored",
        text_artifact_id="a" * 32,
        text_artifact_token="t" * 43,
        channel_id="ch-1",
    )
    assert body.text == "ignored"
    assert body.channel_id == "ch-1"


def test_nllb_request_defaults() -> None:
    body = NllbRequest()
    assert body.text == ""
    assert body.target_language == "English"
