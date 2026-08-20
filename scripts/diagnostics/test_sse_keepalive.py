"""Diagnostic: SSE keepalive line via ``aiter_lines``.

Audit-secondary F24: moved out of ``tests/_diag/`` so the
file is no longer auto-collected by pytest. See
``test_minimal.py`` for the rationale.

How to run::

    uv run python scripts/diagnostics/test_sse_keepalive.py

What it checks: a single SSE keepalive line (``: keepalive``)
is delivered through ``aiter_lines`` without hanging. Useful
when the SSE keepalive cadence is the suspect — the
production path in ``api/routers/events.py`` uses the same
15-second idle timeout and a similar ``aiter_lines`` consumer.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
# _common.py lives in the parent ``scripts/`` directory; add it to sys.path
# before importing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import setup_sys_path  # noqa: E402

setup_sys_path()

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport

app = FastAPI()


@app.get("/stream")
async def stream():
    async def gen():
        try:
            while True:
                await asyncio.sleep(0.1)
                yield b": keepalive\n\n"
        finally:
            pass

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


@pytest.mark.asyncio
async def test_keepalive():
    async with (
        httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client,
        client.stream("GET", "/stream") as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        first = await anext(aiter(response.aiter_lines()))
        assert first == ": keepalive"
        print("GOT:", first)


if __name__ == "__main__":
    asyncio.run(test_keepalive())
