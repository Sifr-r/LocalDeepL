"""Core voice transcription module for OmniScribe."""

from __future__ import annotations

from omniscribe.core.transcription.api_engine import GenericAudioAPIEngine
from omniscribe.core.transcription.factory import (
    TranscriptionEngineProtocol,
    get_transcription_engine,
)
from omniscribe.core.transcription.local_engine import WhisperLocalEngine
from omniscribe.core.transcription.types import (
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
)
from omniscribe.core.transcription.validation import (
    DEFAULT_MAX_AUDIO_BYTES,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_AUDIO_MIME_TYPES,
    AudioValidationError,
    validate_audio_input,
)

__all__ = [
    "DEFAULT_MAX_AUDIO_BYTES",
    "SUPPORTED_AUDIO_EXTENSIONS",
    "SUPPORTED_AUDIO_MIME_TYPES",
    "AudioValidationError",
    "GenericAudioAPIEngine",
    "TranscriptionEngineProtocol",
    "TranscriptionError",
    "TranscriptionResult",
    "TranscriptionSegment",
    "WhisperLocalEngine",
    "get_transcription_engine",
    "validate_audio_input",
]
