"""Test with explicit asyncio loop and transport."""
import sys
sys.path.insert(0, "src")

import asyncio
import httpx
from httpx import ASGITransport
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import pytest

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
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

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
