"""Request schemas for the translate plugin.

Field constraints reproduce the pre-harness contract (commit ``44ef123^``,
``api/schemas/requests.py``) so the existing Flutter client keeps working
without changes. The local ``_TrimmedModel`` mirrors the documents
plugin's shared base (it is private there, so it is copied, not imported).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _TrimmedModel(BaseModel):
    """Shared config: reject unknown fields, trim string values."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TranslationRequest(_TrimmedModel):
    text: str = ""
    text_artifact_id: str | None = None
    text_artifact_token: str | None = None
    target_language: str = Field(default="Spanish", min_length=1, max_length=80)
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    glossary: list[dict] | None = Field(default=None, max_length=1000)
    glossary_text: str | None = None
    sliding_window_words: int = Field(default=80, ge=0, le=2000)
    dual_translate: bool = False
    second_api_base: str | None = None
    second_api_key: str | None = None
    second_model: str | None = None


class AsyncTranslationRequest(TranslationRequest):
    """Async (tree-aware) submission: artifact pair required, legacy
    defaults, ``text``/``channel_id`` accepted and ignored."""

    text_artifact_id: str = Field(min_length=32, max_length=32)
    text_artifact_token: str = Field(min_length=32, max_length=256)
    target_language: str = Field(default="English", min_length=1, max_length=80)
    channel_id: str | None = None


class NllbRequest(_TrimmedModel):
    text: str = ""
    target_language: str = "English"
