import logging
import os
import warnings

from fastapi import Header, Query
from fastapi.responses import JSONResponse

from omniscribe.api.services.security import (
    SERVER_ERROR_MESSAGE,
    api_error_response,
    cleanup_files,
)

logger = logging.getLogger(__name__)


def _cleanup(*paths):
    cleanup_files(*paths)


def _stable_server_error(status_code: int = 500) -> JSONResponse:
    return api_error_response(status_code, SERVER_ERROR_MESSAGE)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_access_token(
    token: str | None = Query(
        default=None,
        description="Deprecated query parameter for artifact token; prefer X-Artifact-Token or Authorization: Bearer header.",
    ),
    authorization: str | None = Header(default=None),
    x_artifact_token: str | None = Header(default=None, alias="X-Artifact-Token"),
) -> str | None:
    resolved_token = token if isinstance(token, str) else None
    resolved_auth = authorization if isinstance(authorization, str) else None
    resolved_x_token = x_artifact_token if isinstance(x_artifact_token, str) else None

    if resolved_token is not None:
        warnings.warn(
            "Query parameter '?token=' is deprecated and will be removed in a future release. Use 'Authorization: Bearer <token>' or 'X-Artifact-Token' header instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.warning(
            "Deprecated query parameter '?token=' used; prefer 'Authorization: Bearer' or 'X-Artifact-Token' header."
        )
    return resolved_x_token or _extract_bearer_token(resolved_auth) or resolved_token


def _path_exists(path: str) -> bool:
    return os.path.exists(path)
