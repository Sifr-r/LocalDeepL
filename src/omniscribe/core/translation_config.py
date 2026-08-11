from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_TRANSLATION_API_BASE = "http://localhost:1234/v1"
DEFAULT_TRANSLATION_API_KEY = "lm-studio"
DEFAULT_TRANSLATION_MODEL = "allenai/olmocr-2-7b"
DEFAULT_TRANSLATION_MAX_ATTEMPTS = 3
DEFAULT_TRANSLATION_MIN_LENGTH_RATIO = 0.1
DEFAULT_TRANSLATION_ACCEPTANCE_SCORE = 0.8


class AsyncTranslationUnavailable(RuntimeError):
    """Raised when the optional async translation runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    """OpenAI-compatible endpoint settings used by async translation.

    Tunables for the translate/evaluate loop (``max_attempts``,
    ``min_length_ratio``, ``acceptance_score``) default to the package-level
    constants but can be overridden via env vars or
    :meth:`from_mapping` to make tuning the loop possible without code edits.
    """

    api_base: str = DEFAULT_TRANSLATION_API_BASE
    api_key: str = DEFAULT_TRANSLATION_API_KEY
    model: str = DEFAULT_TRANSLATION_MODEL
    max_attempts: int = DEFAULT_TRANSLATION_MAX_ATTEMPTS
    min_length_ratio: float = DEFAULT_TRANSLATION_MIN_LENGTH_RATIO
    acceptance_score: float = DEFAULT_TRANSLATION_ACCEPTANCE_SCORE

    def __post_init__(self) -> None:
        for field_name, value in (
            ("api_base", self.api_base),
            ("api_key", self.api_key),
            ("model", self.model),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if isinstance(self.max_attempts, bool) or not isinstance(
            self.max_attempts, int
        ):
            raise ValueError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if isinstance(self.min_length_ratio, bool) or not isinstance(
            self.min_length_ratio, (int, float)
        ):
            raise ValueError("min_length_ratio must be a number")
        if not 0.0 <= float(self.min_length_ratio) <= 1.0:
            raise ValueError("min_length_ratio must be between 0.0 and 1.0")

        if isinstance(self.acceptance_score, bool) or not isinstance(
            self.acceptance_score, (int, float)
        ):
            raise ValueError("acceptance_score must be a number")
        if not 0.0 <= float(self.acceptance_score) <= 1.0:
            raise ValueError("acceptance_score must be between 0.0 and 1.0")

    @classmethod
    def from_env(cls) -> TranslationSettings:
        """Build settings from environment variables.

        Endpoint fields reuse the shared ``LLM_*`` vars; the per-loop tunables
        use ``OMNISCRIBE_TRANSLATION_*`` names so they can be tuned without
        code changes. Invalid values for the tunables fall back to the
        defaults rather than raising — env misconfig should not crash the
        server at import time.
        """
        return cls(
            api_base=os.getenv("LLM_API_BASE", DEFAULT_TRANSLATION_API_BASE),
            api_key=os.getenv("LLM_API_KEY", DEFAULT_TRANSLATION_API_KEY),
            model=os.getenv("LLM_MODEL", DEFAULT_TRANSLATION_MODEL),
            max_attempts=_int_env(
                "OMNISCRIBE_TRANSLATION_MAX_ATTEMPTS",
                DEFAULT_TRANSLATION_MAX_ATTEMPTS,
                minimum=1,
            ),
            min_length_ratio=_float_env(
                "OMNISCRIBE_TRANSLATION_MIN_LENGTH_RATIO",
                DEFAULT_TRANSLATION_MIN_LENGTH_RATIO,
                minimum=0.0,
                maximum=1.0,
            ),
            acceptance_score=_float_env(
                "OMNISCRIBE_TRANSLATION_ACCEPTANCE_SCORE",
                DEFAULT_TRANSLATION_ACCEPTANCE_SCORE,
                minimum=0.0,
                maximum=1.0,
            ),
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> TranslationSettings:
        """Build settings from a broader runtime config mapping."""
        return cls(
            api_base=_string_value(values, "api_base", DEFAULT_TRANSLATION_API_BASE),
            api_key=_string_value(values, "api_key", DEFAULT_TRANSLATION_API_KEY),
            model=_string_value(values, "model", DEFAULT_TRANSLATION_MODEL),
            max_attempts=_int_value(
                values, "max_attempts", DEFAULT_TRANSLATION_MAX_ATTEMPTS, minimum=1
            ),
            min_length_ratio=_numeric_value(
                values,
                "min_length_ratio",
                DEFAULT_TRANSLATION_MIN_LENGTH_RATIO,
                minimum=0.0,
                maximum=1.0,
            ),
            acceptance_score=_numeric_value(
                values,
                "acceptance_score",
                DEFAULT_TRANSLATION_ACCEPTANCE_SCORE,
                minimum=0.0,
                maximum=1.0,
            ),
        )


def _string_value(values: Mapping[str, object], key: str, default: str) -> str:
    value = values.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _int_env(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if minimum <= parsed <= maximum else default


def _int_value(
    values: Mapping[str, object], key: str, default: int, *, minimum: int
) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value if value >= minimum else default


def _numeric_value(
    values: Mapping[str, object],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value) if minimum <= float(value) <= maximum else default
