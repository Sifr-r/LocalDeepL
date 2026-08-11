import os

from fastapi import Header, Query
from fastapi.responses import JSONResponse

from omniscribe.api.services.security import (
    SERVER_ERROR_MESSAGE,
    api_error_response,
    cleanup_files,
)


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
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> str | None:
    return _extract_bearer_token(authorization) or token


def _path_exists(path: str) -> bool:
    return os.path.exists(path)
