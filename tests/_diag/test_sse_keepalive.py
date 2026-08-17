"""Test just the keepalive line."""
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
async def test_keepalive():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("GET", "/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            first = await anext(aiter(response.aiter_lines()))
            assert first == ": keepalive"
            print("GOT:", first)
