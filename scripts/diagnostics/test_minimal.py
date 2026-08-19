"""Minimal async test to verify pytest-asyncio + AsyncClient works."""
import sys
sys.path.insert(0, "src")

import asyncio
import httpx
from httpx import ASGITransport
from fastapi import FastAPI

app = FastAPI()

@app.get("/ping")
async def ping():
    return {"pong": True}

async def test_minimal():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"pong": True}
        print("OK")
