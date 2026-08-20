"""Diagnostic: SSE-style streaming via ``aiter_raw``.

Audit-secondary F24: moved out of ``tests/_diag/`` so the
file is no longer auto-collected by pytest. See
``test_minimal.py`` for the rationale.

How to run::

    uv run python scripts/diagnostics/test_async_stream2.py

What it checks: an infinite SSE-style stream can be read
chunk-by-chunk via ``aiter_raw`` without hanging. Useful when
debugging a slow SSE consumer — the first keepalive chunk
arrives within ~100 ms and the test exits.

Context: this file was created while debugging the audit's
"D2-12 QueueFull unhandled in SSE push" finding. The fix
(D2-12 in audit-secondary Phase 3) moved to
``api/routers/events.py:_put_with_drop_oldest``; this
diagnostic is kept for future debugging of related SSE
behaviour.
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
async def test_keepalive_via_aiter_raw():
    """Use aiter_raw to read chunks directly."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Use request directly to avoid the stream context manager
        request = client.build_request("GET", "/stream")
        response = await client.send(request, stream=True)
        print(f"status={response.status_code}")
        # Read the first chunk
        chunks = []
        async for chunk in response.aiter_raw():
            print(f"chunk={chunk!r}")
            chunks.append(chunk)
            if len(chunks) >= 1:
                break
        print(f"got {len(chunks)} chunks")
        await response.aclose()
        print("DONE")
        assert response.status_code == 200


if __name__ == "__main__":
    asyncio.run(test_keepalive_via_aiter_raw())
