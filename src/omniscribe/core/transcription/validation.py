"""Audio input validation helper and exception definitions."""

from __future__ import annotations

from pathlib import Path

# Supported audio MIME types and extensions
SUPPORTED_AUDIO_EXTENSIONS: set[str] = {
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".ogg",
    ".webm",
    ".aac",
    ".opus",
    ".mp4",
}

SUPPORTED_AUDIO_MIME_TYPES: set[str] = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "audio/webm",
    "audio/aac",
    "audio/opus",
    "video/mp4",
    "video/webm",
}

DEFAULT_MAX_AUDIO_BYTES: int = 100 * 1024 * 1024  # 100 MB default cap for audio


class AudioValidationError(Exception):
    """Raised when an audio input fails validation (unsupported format or size)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_audio_input(
    filename: str,
    content_type: str | None = None,
    file_size: int | None = None,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
) -> str:
    """Validate audio filename, MIME type, and file size.

    Returns the normalized lowercase file extension if valid.
    Raises `AudioValidationError` if validation fails.
    """
    if not filename or not filename.strip():
        raise AudioValidationError("Audio filename must not be empty.", status_code=400)

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported audio format '{ext}'. Supported formats: {sorted(SUPPORTED_AUDIO_EXTENSIONS)}",
            status_code=415,
        )

    if (
        content_type
        and content_type.split(";")[0].strip().lower() != "application/octet-stream"
        and content_type.split(";")[0].strip().lower() not in SUPPORTED_AUDIO_MIME_TYPES
    ):
        normalized_mime = content_type.split(";")[0].strip().lower()
        if normalized_mime.startswith("text/") or normalized_mime.startswith("image/"):
            raise AudioValidationError(
                f"MIME type '{normalized_mime}' is not a valid audio content type.",
                status_code=415,
            )

    if file_size is not None:
        if file_size <= 0:
            raise AudioValidationError(
                "Audio file is empty (0 bytes).", status_code=400
            )
        if file_size > max_bytes:
            max_mb = max_bytes // (1024 * 1024)
            raise AudioValidationError(
                f"Audio file size ({file_size} bytes) exceeds maximum allowed size ({max_mb} MB).",
                status_code=413,
            )

    return ext
