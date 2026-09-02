# ruff: noqa: E402
"""
FastAPI web server for OmniScribe.

Mounts the Cordis-style plugin harness inside the FastAPI lifespan: the
shipped ``resources/cordis.yml`` tree (plus operator patches and env
overrides) is loaded onto a fresh harness ``Context`` at startup, the
plugin-registered routers are included, readiness flips, and every effect
is disposed in LIFO order on shutdown.
"""

from __future__ import annotations

import argparse
import importlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

from dotenv import load_dotenv

load_dotenv()

from omniscribe.config import RuntimeSettings, load_settings
from omniscribe.utils import configure_logging  # noqa: F401  -- re-exported for tests
from omniscribe.utils.structured_logging import _resolve_log_format

_log = logging.getLogger("omniscribe.server")

# Sprint 5 / M-10 audit fix: placeholder auth tokens that the operator
# might paste from the documentation without replacing. Compared in
# lowercase so ``Change-Me-In-Prod`` (capitalised by accident) is also
# caught. Add new entries here ONLY after updating SECURITY.md and
# the operator-facing ``.env.example`` to point at the same string.
_PLACEHOLDER_AUTH_TOKENS: frozenset[str] = frozenset(
    {
        "change-me-in-prod",
        "placeholder",
        "example-token-replace-me",
        "replace-this-with-a-real-secret",
    }
)

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIScope = dict[str, Any]

# --- Static files directory ---
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


# --- Optional module loading ---
def _load_optional_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            module_name
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Cannot start omniscribe-server because `{exc.name}` is not "
            f"installed. {_WEB_EXTRA_MESSAGE}"
        ) from exc


def _load_attr(target: str) -> Any:
    """Load an attribute from an optional module (e.g. 'fastapi:FastAPI')."""
    module_name, _, attr_name = target.partition(":")
    mod = _load_optional_module(module_name)
    if not attr_name:
        return mod
    try:
        return getattr(mod, attr_name)
    except AttributeError as exc:
        raise RuntimeError(
            f"Cannot start omniscribe-server because `{target}` could not be resolved."
        ) from exc


# --- Harness boot ---


async def _load_harness(settings: RuntimeSettings) -> Any:
    """Load the cordis.yml plugin tree onto a fresh harness Context.

    Imports stay inside the function so the module-level import surface of
    ``omniscribe.server`` remains free of the harness (and yaml) until the
    app is actually created.
    """
    from omniscribe.harness.context import Context
    from omniscribe.harness.loader import Loader

    ctx = Context()
    await Loader(ctx).load(
        settings.cordis_config_path,
        patch_paths=settings.cordis_patch_paths,
    )
    return ctx


# --- FastAPI application ---


def create_app() -> ASGIApplication:
    """Create the FastAPI app with the plugin-harness lifespan."""
    settings = load_settings()
    fastapi = _load_optional_module("fastapi")
    staticfiles = _load_optional_module("fastapi.staticfiles")
    responses = _load_optional_module("fastapi.responses")

    @asynccontextmanager
    async def lifespan(web_app: Any) -> AsyncIterator[None]:
        from omniscribe.plugins.runtime import RuntimeService

        runtime_settings = _validate_runtime_settings(settings)
        ctx = await _load_harness(runtime_settings)
        web_app.state.context = ctx
        # Routers were registered as effects at plugin apply time; mount
        # them now that the tree is fully loaded.
        for router in ctx.routes():
            web_app.include_router(router)
        # Readiness is owned by the runtime plugin; patched trees may drop it.
        if ctx.has(RuntimeService):
            ctx.inject(RuntimeService).mark_ready()
        try:
            yield
        finally:
            await ctx.dispose()

    web_app = fastapi.FastAPI(
        title="OmniScribe API",
        description="OmniScribe PDF OCR and document processing API",
        lifespan=lifespan,
    )

    # M-1 audit fix: wire CORS middleware. ``OMNISCRIBE_CORS_ORIGINS`` is
    # a comma-separated allowlist (e.g. ``https://app.example.com``);
    # the empty default denies cross-origin requests from a browser
    # but still allows the Flutter desktop client (no Origin header)
    # to call the API. A bare ``*`` opens the open wildcard.
    cors_origins = settings.cors_origins
    cors_module = _load_optional_module("fastapi.middleware.cors")
    web_app.add_middleware(
        cors_module.CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=bool(cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        expose_headers=[
            "Content-Disposition",
            "X-Document-Trust",
            "X-Artifact-Token",
        ],
        max_age=600,
    )

    # Audit 6.1a: ASGI bearer-token auth on the rebuilt harness route
    # surface. The startup guard in ``_validate_runtime_settings`` is
    # the operator-facing backstop (refuses placeholder tokens on
    # non-loopback binds); this middleware is the request-time gate.
    # The middleware is a no-op when ``auth_token`` is unset so local
    # dev and CI keep working without a token.
    from omniscribe.middleware.auth import BearerAuthMiddleware

    web_app.add_middleware(
        BearerAuthMiddleware, expected_token=settings.auth_token
    )

    if _STATIC_DIR.is_dir():
        web_app.mount(
            "/static",
            staticfiles.StaticFiles(directory=str(_STATIC_DIR)),
            name="static",
        )

    @web_app.get("/")
    async def index() -> Any:
        index_file = _STATIC_DIR / "index.html"
        if index_file.is_file():
            return responses.FileResponse(index_file)
        return responses.JSONResponse(
            {"status": "ok", "message": "OmniScribe API Server"}
        )

    @web_app.exception_handler(ValueError)
    async def value_error_handler(request: Any, exc: ValueError) -> Any:
        return responses.JSONResponse(
            status_code=400,
            content={"error": "bad_request", "detail": str(exc)},
        )

    # M-3 audit fix: catch-all handler logs the traceback (so genuine
    # bugs surface in the operator's structured log) but does NOT
    # leak the traceback to the client. A 500 with a stable error
    # code (``internal_error``) is the documented contract — clients
    # can display a generic failure message and operators can grep
    # the log for ``omniscribe.server unhandled``.
    @web_app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Any, exc: Exception) -> Any:
        _log.exception("unhandled exception in %s %s", request.method, request.url.path)
        return responses.JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "see server log"},
        )

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


# --- Startup validation ---


def _validate_runtime_settings(
    settings: RuntimeSettings | None = None,
) -> RuntimeSettings:
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
    if settings is None:
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


# --- CLI entry-point ---


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
    parser.add_argument(
        "--allow-placeholder-token",
        action="store_true",
        help="Allow startup with a placeholder OMNISCRIBE_AUTH_TOKEN "
        "(M-10 audit opt-out; default is to refuse).",
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

    # C-1 audit fix: refuse to start bound to a non-loopback host
    # without ``OMNISCRIBE_AUTH_TOKEN``. The rebuilt route surface is
    # currently unauthenticated (deferred per AGENTS.md); exposing
    # that surface to any network is unsafe. Loopback binds are the
    # documented local-trusted mode and remain allowed without a
    # token.
    _settings_for_guard = load_settings()
    is_loopback = args.host in {"127.0.0.1", "::1", "localhost"}
    if not is_loopback and not _settings_for_guard.auth_token:
        raise SystemExit(
            f"Refusing to start: --host {args.host} is non-loopback and "
            "OMNISCRIBE_AUTH_TOKEN is unset. Set OMNISCRIBE_AUTH_TOKEN "
            "(32+ chars) or bind to 127.0.0.1 / ::1 / localhost. See "
            "SECURITY.md."
        )
    # M-10 audit fix: refuse placeholder tokens on non-loopback binds.
    # A common operator mistake is to copy ``.env.example`` and forget
    # to replace the placeholder. The check is opt-out via the same
    # ``--allow-placeholder-token`` flag, defaulting to refusal, so
    # the surface-area of accepting a placeholder is one CLI flag
    # rather than a config-file knob. ``change-me-in-prod`` is the
    # documented placeholder per ``.env.example``; the lowercase
    # comparison catches accidental case swaps.
    if (
        not is_loopback
        and _settings_for_guard.auth_token
        and _settings_for_guard.auth_token.lower() in _PLACEHOLDER_AUTH_TOKENS
        and not getattr(args, "allow_placeholder_token", False)
    ):
        raise SystemExit(
            "Refusing to start: OMNISCRIBE_AUTH_TOKEN is a known "
            "placeholder value. Replace it with a random secret "
            "(e.g. `python -c 'import secrets; print(secrets.token_urlsafe(32))'`) "
            "or pass --allow-placeholder-token if you understand the risk. "
            "See SECURITY.md."
        )
    # C-2 audit fix: when ``ALLOW_SSRF_LOCAL=true`` AND the bind host is
    # non-loopback, log a loud WARNING that any LAN caller can reach the
    # SSRF-disabled private-network endpoints via ``/api/providers/*``.
    # The default is preserved for local dev; operators who expose the
    # server to a LAN should set ``ALLOW_SSRF_LOCAL=false``.
    if not is_loopback and getattr(_settings_for_guard, "allow_ssrf_local", False):
        _log.warning(
            "ALLOW_SSRF_LOCAL=true with non-loopback bind %s: SSRF guard "
            "permits private / loopback URLs from any LAN caller. "
            "Set ALLOW_SSRF_LOCAL=false on public / LAN deployments.",
            args.host,
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
