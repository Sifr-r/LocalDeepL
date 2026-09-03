"""Middleware package for OmniScribe."""

from __future__ import annotations

from omniscribe.middleware.auth import BearerAuthMiddleware
from omniscribe.middleware.rate_limit import RateLimitMiddleware
from omniscribe.middleware.upload_limit import (
    DEFAULT_MAX_BYTES,
    UploadSizeLimitMiddleware,
)

__all__ = [
    "DEFAULT_MAX_BYTES",
    "BearerAuthMiddleware",
    "RateLimitMiddleware",
    "UploadSizeLimitMiddleware",
]
