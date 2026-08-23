"""ASGI security middlewares for OmniScribe.

Exposes:
- :class:`BearerAuthMiddleware` for token-based route authorization.
- :class:`MaxUploadSizeMiddleware` for request body size and deadline guarding.
- :class:`RateLimitMiddleware` for sliding window per-IP rate limiting.
"""

from __future__ import annotations

from omniscribe.api.middleware.auth import (
    _HEALTH_PATHS,
    _INVALID_PATH,
    _UNAUTHORIZED,
    BearerAuthMiddleware,
    _is_health_path,
    _is_management_route,
    _is_ocr_route,
    _is_transcription_route,
    _is_translation_route,
    _normalize_path,
    _normalize_token,
)
from omniscribe.api.middleware.rate_limit import (
    _SWEEP_INTERVAL_S,
    _TOO_MANY_REQUESTS,
    RateLimitMiddleware,
)
from omniscribe.api.middleware.upload_guard import (
    _DEADLINE_EXCEEDED,
    _TOO_LARGE,
    MaxUploadSizeMiddleware,
    _UploadGuard,
)

__all__ = [
    "_DEADLINE_EXCEEDED",
    "_HEALTH_PATHS",
    "_INVALID_PATH",
    "_SWEEP_INTERVAL_S",
    "_TOO_LARGE",
    "_TOO_MANY_REQUESTS",
    "_UNAUTHORIZED",
    "BearerAuthMiddleware",
    "MaxUploadSizeMiddleware",
    "RateLimitMiddleware",
    "_UploadGuard",
    "_is_health_path",
    "_is_management_route",
    "_is_ocr_route",
    "_is_transcription_route",
    "_is_translation_route",
    "_normalize_path",
    "_normalize_token",
]
