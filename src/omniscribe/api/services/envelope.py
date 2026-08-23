"""Canonical API error envelope (Phase C).

Replaces four idioms:
  - `api_error_response(...)` (services/uploads.py)
  - `_ai_error_response(...)` (duplicated in translation.py + extraction.py)
  - raw `JSONResponse(status_code=..., content={"error": ..., "detail": ...})`
  - `HTTPException(detail="string")` for user-facing errors

Wire shape: ``{"error": "<stable_code>", "detail": "<human string>"}``.
``detail`` is omitted from the JSON body when ``None``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Pydantic mirror of the wire shape.

    Declared so ``response_model=ErrorEnvelope`` works on route decorators
    and OpenAPI surfaces the contract.
    """

    error: str = Field(..., description="Stable machine-readable error code.")
    detail: str | None = Field(
        default=None,
        description="Optional human-readable detail. Omitted when None.",
    )


class APIError(Exception):
    """Base class for all envelope-shaped exceptions.

    Subclasses set ``status_code`` + ``error``. The handler in
    ``register_envelope_handlers`` converts ``self`` to an
    ``ErrorEnvelope`` JSON response.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error: str = "internal_error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.error)
        self.detail = detail


class SSRFBlocked(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    error = "ssrf_blocked"

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"URL targets a blocked address: {reason}")
        self.url = url
        self.reason = reason


class BackendUnavailable(APIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error = "backend_unavailable"


class ValidationFailed(APIError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error = "validation_failed"


class NotFound(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    error = "not_found"


class RateLimited(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error = "rate_limited"


class BadRequest(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    error = "bad_request"


def envelope_error(
    *,
    status_code: int,
    error: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a JSONResponse in the canonical envelope shape.

    ``extra`` is a small bag of additional response keys to merge into
    the body alongside ``error`` and ``detail``. Reserved for the rare
    case where a status-style endpoint has to carry both canonical
    envelope fields and route-specific identity keys (e.g. ``job_id``
    on the async translation status endpoint). ``extra`` MUST NOT be
    used to set ``error`` or ``detail`` — those keys are owned by this
    helper; any such keys in ``extra`` are silently dropped.
    """
    body: dict[str, Any] = {"error": error}
    if detail is not None:
        body["detail"] = detail
    if extra is not None:
        merged = {k: v for k, v in extra.items() if k not in {"error", "detail"}}
        body.update(merged)
    return JSONResponse(status_code=status_code, content=body)


async def _apierror_handler(_request: Request, exc: APIError) -> JSONResponse:
    return envelope_error(
        status_code=exc.status_code, error=exc.error, detail=exc.detail
    )


async def _validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = f"{len(exc.errors())} validation error(s)."
    resp = envelope_error(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        error="validation_failed",
        detail=detail,
    )
    resp.headers["x-validation-errors"] = str(len(exc.errors()))
    return resp


def register_envelope_handlers(app: FastAPI) -> None:
    """Register both ``APIError`` and ``RequestValidationError`` handlers.

    Idempotent — safe to call from tests that build a throwaway app.
    """
    app.add_exception_handler(APIError, _apierror_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
