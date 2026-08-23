"""Health plugin: liveness always ok, readiness flips after mark_ready()."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.harness.context import Context
from omniscribe.plugins import health, runtime
from omniscribe.plugins.runtime import RuntimeService


async def _boot() -> Context:
    ctx = Context()
    await ctx.plugin(runtime.RuntimePlugin(), config={})
    await ctx.plugin(health.HealthPlugin(), config={})
    return ctx


def _make_app(ctx: Context) -> FastAPI:
    app = FastAPI()
    for router in ctx.routes():
        app.include_router(router)
    return app


async def test_liveness_is_always_ok() -> None:
    ctx = await _boot()
    try:
        with TestClient(_make_app(ctx)) as client:
            for path in ("/api/health", "/api/healthz"):
                response = client.get(path)
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
    finally:
        await ctx.dispose()


async def test_readiness_is_503_until_mark_ready_then_200() -> None:
    ctx = await _boot()
    try:
        runtime_service = ctx.inject(RuntimeService)
        assert runtime_service.ready is False
        with TestClient(_make_app(ctx)) as client:
            for path in ("/ready", "/readyz"):
                response = client.get(path)
                assert response.status_code == 503
                assert response.json() == {"status": "starting"}

            runtime_service.mark_ready()

            for path in ("/ready", "/readyz"):
                response = client.get(path)
                assert response.status_code == 200
                assert response.json() == {"status": "ready"}
    finally:
        await ctx.dispose()


async def test_health_plugin_requires_runtime_service() -> None:
    from omniscribe.harness.errors import ServiceNotFoundError

    ctx = Context()
    try:
        await ctx.plugin(health.HealthPlugin(), config={})
    except ServiceNotFoundError:
        pass
    else:  # pragma: no cover — defensive
        await ctx.dispose()
        raise AssertionError("HealthPlugin should fail loud without RuntimeService")
