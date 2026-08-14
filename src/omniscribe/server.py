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
import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

from omniscribe.config import RuntimeSettings, load_settings
from omniscribe.utils import configure_logging  # noqa: F401  -- re-exported for tests
from omniscribe.utils.structured_logging import _resolve_log_format

_LOGGER = logging.getLogger(__name__)
_log = logging.getLogger("omniscribe.server")
_DEFAULT_ARTIFACT_CLEANUP_INTERVAL_S = 60.0
_ARTIFACT_CLEANUP_TASK_NAME = "omniscribe-artifact-cleanup"

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
        health,
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
            RateLimitMiddleware,
            per_minute=security.rate_limit_per_minute,
            trusted_proxies=security.trusted_proxies,
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
    web_app.include_router(health.router)
    web_app.get("/")(read_index)

    @web_app.exception_handler(ValueError)
    async def value_error_handler(request: Any, exc: ValueError) -> Any:
        responses = _load_optional_module("fastapi.responses")
        return responses.JSONResponse(status_code=400, content={"error": str(exc)})

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
# Startup validation
# ---------------------------------------------------------------------------


def _validate_runtime_settings() -> RuntimeSettings:
    """Load, validate, and log startup-time settings.

    Validates:

    * ``OMNISCRIBE_LOG_FORMAT`` is a known format (raises ``ValueError``).
    * ``OMNISCRIBE_ARTIFACT_DIR`` is a directory when it exists (raises
      ``RuntimeError`` if a file is in the way).

    Logs a single ``info`` record with the non-secret settings so an
    operator can confirm the process started with the expected backend
    configuration. Auth tokens are surfaced only as an ``auth_enabled``
    boolean — the actual token value never lands in the log.
    """
    settings = load_settings()
    # Validate the log format eagerly so a malformed env var fails
    # startup with a clear message, not a stack trace.
    _resolve_log_format(settings.log_format)

    artifact_base = settings.artifact_base_dir
    if artifact_base.exists() and not artifact_base.is_dir():
        raise RuntimeError(
            f"OMNISCRIBE_ARTIFACT_DIR={artifact_base} must point to a "
            "directory, but it is an existing file."
        )

    log_extras = {
        "llm_api_base": settings.llm_api_base,
        "llm_model": settings.llm_model,
        "grounded_model": settings.grounded_model,
        "vlm_page_timeout": settings.vlm_page_timeout,
        "vlm_crop_timeout": settings.vlm_crop_timeout,
        "artifact_base_dir": str(artifact_base),
        "allow_ssrf_local": settings.allow_ssrf_local,
        "state_backend": settings.state_backend,
        "auth_enabled": bool(settings.auth_token),
    }
    _log.info("omniscribe startup settings", extra=log_extras)
    return settings


# ---------------------------------------------------------------------------
# Artifact TTL background sweeper
# ---------------------------------------------------------------------------


def _artifact_cleanup_interval_s() -> float:
    """Read the cleanup interval from ``OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S``.

    A non-numeric or empty value falls back to the configured default. A
    negative value is clamped to ``0.0`` (which disables the sweeper).
    Returning ``0.0`` is the documented "off" sentinel — the cleanup
    loop checks for it before scheduling.
    """
    raw = os.getenv("OMNISCRIBE_ARTIFACT_CLEANUP_INTERVAL_S")
    if raw is None or not raw.strip():
        return _DEFAULT_ARTIFACT_CLEANUP_INTERVAL_S
    try:
        return max(0.0, float(raw.strip()))
    except (TypeError, ValueError):
        return _DEFAULT_ARTIFACT_CLEANUP_INTERVAL_S


def _artifact_cleanup_stores() -> Sequence[Any]:
    """Return the ``state`` stores that the sweeper should sweep.

    Wires up every store that owns a bounded-time-in-memory record: the
    three text/metadata/export ``TextArtifactStore`` instances, the
    FIFO-capped ``JobHistory``, and the ``OCRJobQueue`` whose
    terminal-state records are now evicted by an explicit ``cleanup_expired``
    sweep (``OMNISCRIBE_OCR_JOB_RETENTION_S`` controls the retention
    window; default 24h, ``0`` disables).
    """
    from omniscribe.api.routers import state as router_state

    return (
        router_state.text_artifacts,
        router_state.metadata_artifacts,
        router_state.export_artifacts,
        router_state.job_history,
        router_state.ocr_job_queue,
    )


async def _artifact_cleanup_loop(interval_s: float) -> None:
    """Forever sweep every artifact store, sleeping ``interval_s`` between ticks.

    The loop is cancellation-friendly: callers cancel the task on shutdown
    and the next ``asyncio.sleep`` raises :class:`asyncio.CancelledError`
    which we let propagate. One broken store (e.g. a permissions error
    on a single artifact directory) must not stop the other stores from
    being swept, so each ``cleanup_expired`` call is wrapped in a
    ``try``/``except`` that logs and continues.
    """
    if interval_s <= 0:
        return
    stores = _artifact_cleanup_stores()
    while True:
        for store in stores:
            cleanup = getattr(store, "cleanup_expired", None)
            if cleanup is None:
                continue
            try:
                cleanup()
            except Exception:
                _LOGGER.exception(
                    "artifact cleanup pass failed; continuing with other stores"
                )
        await asyncio.sleep(interval_s)


async def _start_artifact_cleanup() -> asyncio.Task[None] | None:
    """Spawn the artifact cleanup loop if the interval is positive.

    Returns ``None`` when the interval is ``0`` (the "off" sentinel),
    letting the caller skip cleanup wiring entirely. The spawned task is
    named for diagnostics in ``asyncio.all_tasks()`` output.
    """
    interval = _artifact_cleanup_interval_s()
    if interval <= 0:
        return None
    task = asyncio.create_task(
        _artifact_cleanup_loop(interval), name=_ARTIFACT_CLEANUP_TASK_NAME
    )
    return task


async def _stop_artifact_cleanup(task: asyncio.Task[None] | None) -> None:
    """Cancel the cleanup task cleanly; ``None`` is a no-op.

    Cancellation is cooperative — the running sleep in the loop raises
    :class:`asyncio.CancelledError` on the next iteration. We
    ``await`` the task so the event loop reaps it before returning.
    """
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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


def _parse_workers(value: str) -> int:
    """Validate the ``--workers`` CLI argument.

    Workers must be an integer in the inclusive range ``[1, 64]``. The
    upper bound matches uvicorn's documented safe range for fork-based
    workers; the lower bound rejects zero workers and negative numbers
    which uvicorn would otherwise reject with a less helpful message.
    """
    try:
        workers = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("workers must be an integer") from exc
    if not 1 <= workers <= 64:
        raise argparse.ArgumentTypeError("workers must be between 1 and 64")
    return workers


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
        "--workers",
        type=_parse_workers,
        default=1,
        help="Number of worker processes (1-64). Default: 1.",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (development)"
    )
    args = parser.parse_args(argv)

    # ``--reload`` is a single-process development aid; combining it with
    # multiple workers would silently demote uvicorn to one worker. Fail
    # loudly so the operator notices the misconfiguration.
    if args.reload and args.workers > 1:
        parser.error(
            "--reload cannot be combined with --workers > 1 "
            f"(got --workers {args.workers})"
        )

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
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
