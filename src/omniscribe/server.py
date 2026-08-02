# ruff: noqa: E402
"""
FastAPI web server: thin wrapper around OCRPipeline with WebSocket progress.

Provides endpoints for PDF/image OCR processing, runtime configuration,
model discovery, and job history tracking.
"""

from __future__ import annotations

import argparse
import importlib

from dotenv import load_dotenv

load_dotenv()
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIScope = dict[str, Any]

# ---------------------------------------------------------------------------
# Static files directory
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent / "static"


_WEB_EXTRA_MESSAGE = (
    "The web server requires the optional web dependencies. Install them with "
    "`uv sync --extra web` for a source checkout, or "
    "`pip install 'omniscribe[web]'` for an installed package."
)


class ASGIApplication(Protocol):
    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None: ...


def _load_optional_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Cannot start omniscribe-server because `{exc.name}` is not "
            f"installed. {_WEB_EXTRA_MESSAGE}"
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


def create_app() -> ASGIApplication:
    """Create the FastAPI app after optional web dependencies are available."""
    fastapi = _load_optional_module("fastapi")
    staticfiles = _load_optional_module("fastapi.staticfiles")

    from omniscribe.api.routers import (
        artifacts,
        config,
        extraction,
        glossary_imports,
        jobs,
        ocr,
        providers,
        state,
        transcription,
        translation,
        websocket,
    )
    from omniscribe.api.services.security_config import SecuritySettings
    from omniscribe.api.services.security_middleware import (
        BearerAuthMiddleware,
        MaxUploadSizeMiddleware,
        RateLimitMiddleware,
    )

    @asynccontextmanager
    async def lifespan(_app: Any) -> AsyncIterator[None]:
        await state.ocr_job_queue.start()
        try:
            yield
        finally:
            await state.ocr_job_queue.stop()

    web_app = fastapi.FastAPI(lifespan=lifespan)
    security = SecuritySettings.from_env()

    if security.cors_origins:
        cors = _load_optional_module("fastapi.middleware.cors")
        web_app.add_middleware(
            cors.CORSMiddleware,
            allow_origins=security.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Security middlewares wrap the inner app. Starlette applies them
    # in REVERSE add-order (last added is outermost), so to produce
    # request flow "Auth → Size → RateLimit → app" we add innermost
    # first. Outer-most first means a 401 doesn't burn a rate-limit
    # slot and a 413 likewise doesn't count against the bucket.
    if security.rate_limit_enabled:
        web_app.add_middleware(
            RateLimitMiddleware, per_minute=security.rate_limit_per_minute
        )
    web_app.add_middleware(MaxUploadSizeMiddleware, max_bytes=security.max_upload_bytes)
    # Per-service auth tokens (OCR / translation / transcription) take precedence over
    # the global ``auth_token`` for the matching route group. When a
    # per-service token is configured, the global token does NOT unlock
    # that namespace — see BearerAuthMiddleware._token_for for details.
    web_app.add_middleware(
        BearerAuthMiddleware,
        expected_token=security.auth_token,
        ocr_token=security.ocr_auth_token,
        translation_token=security.translation_auth_token,
        transcription_token=security.transcription_auth_token,
    )

    web_app.mount(
        "/static",
        staticfiles.StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

    web_app.include_router(config.router)
    web_app.include_router(ocr.router)
    web_app.include_router(websocket.router)
    web_app.include_router(jobs.router)
    web_app.include_router(artifacts.router)
    web_app.include_router(translation.router)
    web_app.include_router(transcription.router)
    web_app.include_router(extraction.router)
    web_app.include_router(glossary_imports.router)
    web_app.include_router(providers.router)
    web_app.get("/")(read_index)

    return cast(ASGIApplication, web_app)


class LazyASGIApp:
    """ASGI proxy that defers FastAPI imports until the server is used."""

    def __init__(self, factory: Callable[[], ASGIApplication]) -> None:
        self._factory = factory
        self._app: ASGIApplication | None = None

    def _load(self) -> ASGIApplication:
        if self._app is None:
            self._app = self._factory()
        return self._app

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        await self._load()(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)


app = LazyASGIApp(create_app)


async def read_index() -> Any:
    """Serve the single-page frontend."""
    responses = _load_optional_module("fastapi.responses")
    return responses.FileResponse(_STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _parse_host(value: str) -> str:
    host = value.strip()
    if not host:
        raise argparse.ArgumentTypeError("host must not be empty")
    return host


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Local LLM PDF OCR web server (FastAPI + WebSocket progress).",
    )
    parser.add_argument(
        "--host",
        type=_parse_host,
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=_parse_port,
        default=8000,
        help="Bind port (default: 8000)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (development)"
    )
    args = parser.parse_args(argv)

    try:
        uvicorn = _load_optional_module("uvicorn")
        app._load()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    uvicorn.run(
        "omniscribe.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
