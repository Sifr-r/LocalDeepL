from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from omniscribe.api.services.security_config import (
    DEFAULT_MAX_UPLOAD_MB as _DEFAULT_MAX_UPLOAD_MB,
)

logger = logging.getLogger(__name__)

# Module-level constant kept in sync with SecuritySettings.DEFAULT_MAX_UPLOAD_MB
# so the in-process upload validator (``save_validated_upload``) defaults its
# cap from the same source as the middleware. If the two drift apart, a
# request rejected by one layer can be silently accepted by the other.
MAX_UPLOAD_BYTES: int = _DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

# Wall-clock deadline for a single in-progress upload. The byte cap above
# already rejects bodies larger than ``MAX_UPLOAD_BYTES``, but a slow-loris
# client streaming 1 byte at a time would otherwise pin a worker forever
# without ever crossing the size threshold. The deadline is env-driven
# (default 60s) so deployments on slow links can extend it.
_DEFAULT_UPLOAD_DEADLINE_SECONDS = 60.0


def _get_upload_deadline_seconds() -> float:
    """Resolve the per-request upload deadline from the env, clamped to
    a sane range. ``0`` or negative disables the check (used in tests)."""
    raw = os.getenv("OMNISCRIBE_UPLOAD_DEADLINE_SECONDS")
    if not raw:
        return _DEFAULT_UPLOAD_DEADLINE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "OMNISCRIBE_UPLOAD_DEADLINE_SECONDS=%r is not numeric; using default %.0fs",
            raw,
            _DEFAULT_UPLOAD_DEADLINE_SECONDS,
        )
        return _DEFAULT_UPLOAD_DEADLINE_SECONDS
    if value <= 0:
        return 0.0  # explicit disable
    return max(1.0, min(value, 24 * 3600.0))  # clamp 1s..24h


SAFE_API_BASE_ERROR = (
    "Invalid api_base. Local, private, malformed, or unresolvable endpoints are "
    "blocked unless ALLOW_SSRF_LOCAL=true is explicitly configured."
)

SERVER_ERROR_MESSAGE = "The request could not be completed. Please try again later."


def api_error_response(
    status_code: int,
    error: str,
    detail: Any | None = None,
) -> JSONResponse:
    """Build the standard API error envelope ``{"error": ..., "detail": ...}``.

    ``detail`` is omitted when ``None`` so opaque 500s don't leak internals
    while validation errors and value errors can attach structured detail.
    See refactor §3.4 in ``deep_refactor_report.md``.
    """
    content: dict[str, Any] = {"error": error}
    if detail is not None:
        content["detail"] = detail
    return JSONResponse(status_code=status_code, content=content)


@dataclass(frozen=True)
class UploadResult:
    path: str
    suffix: str
    size_bytes: int


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def detect_upload_suffix(header: bytes) -> str:
    if header.startswith(b"%PDF-"):
        return ".pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if header.startswith(b"BM"):
        return ".bmp"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return ".webp"
    if (
        len(header) >= 12
        and header[4:8] == b"ftyp"
        and header[8:12]
        in {
            b"avif",
            b"avis",
        }
    ):
        return ".avif"
    raise UploadValidationError("Unsupported file type.", status_code=415)


async def save_validated_upload(
    file: UploadFile,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    deadline_seconds: float | None = None,
) -> UploadResult:
    first_chunk = await file.read(UPLOAD_CHUNK_BYTES)
    if not first_chunk:
        raise UploadValidationError("Uploaded file is empty.")

    suffix = detect_upload_suffix(first_chunk[:64])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    input_path = tmp.name
    size = 0

    # Wall-clock deadline. Resolved lazily so env changes (or test
    # fixtures that swap ``OMNISCRIBE_UPLOAD_DEADLINE_SECONDS``) are
    # honored without re-importing the module. A value of ``0`` or
    # ``None`` disables the check.
    if deadline_seconds is None:
        deadline_seconds = _get_upload_deadline_seconds()
    deadline_enabled = deadline_seconds > 0
    started = time.monotonic() if deadline_enabled else 0.0

    try:
        while first_chunk:
            size += len(first_chunk)
            if size > max_bytes:
                raise UploadValidationError(
                    f"File too large. Maximum size is {max_bytes // (1024 * 1024)}MB.",
                    status_code=413,
                )
            if deadline_enabled and time.monotonic() - started > deadline_seconds:
                raise UploadValidationError(
                    f"Upload exceeded {deadline_seconds:.0f}s deadline.",
                    status_code=408,
                )
            await asyncio.to_thread(tmp.write, first_chunk)
            first_chunk = await file.read(UPLOAD_CHUNK_BYTES)
    except Exception:
        tmp.close()
        try:
            Path(input_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove rejected upload %s", input_path)
        raise
    else:
        tmp.close()
        return UploadResult(path=input_path, suffix=suffix, size_bytes=size)


def cleanup_files(*paths: str | None) -> None:
    temp_dir = Path(tempfile.gettempdir()).resolve()
    for path in paths:
        if not path:
            continue
        try:
            resolved = Path(path).resolve()
            if (
                temp_dir in resolved.parents or temp_dir == resolved.parent
            ) and resolved.exists():
                os.remove(resolved)
        except OSError:
            logger.warning("Could not remove temporary file %s", path)
