"""Diagnostic — minimal async endpoint with async generator.

See also ``scripts/diagnostics/test_sse_keepalive.py`` for the canonical
keepalive-line smoke test used by CI.
"""
import sys
sys.path.insert(0, "src")

import asyncio
import time
import threading

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/simple")
async def simple():
    async def gen():
        await asyncio.sleep(0.1)
        yield b": keepalive\n\n"
        await asyncio.sleep(0.1)
        yield b": keepalive\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/with_is_disconnected")
async def with_is_disconnected(request: Request):
    async def gen():
        while True:
            if await request.is_disconnected():
                break
            try:
                await asyncio.sleep(0.1)
                yield b": keepalive\n\n"
            except asyncio.CancelledError:
                break
    return StreamingResponse(gen(), media_type="text/event-stream")

client = TestClient(app)

for path in ["/simple", "/with_is_disconnected"]:
    print(f"\n=== Testing {path} ===")
    def reader(p=path):
        try:
            with client.stream("GET", p) as response:
                print(f"  status={response.status_code}")
                print(f"  content-type={response.headers.get('content-type')}")
                for line in response.iter_lines():
                    print(f"  line={line!r}")
                    break
        except Exception as e:
            print(f"  error={e!r}")
    t = threading.Thread(target=reader, daemon=True)
    t0 = time.monotonic()
    t.start()
    t.join(timeout=3.0)
    print(f"  elapsed={time.monotonic()-t0:.2f}s alive={t.is_alive()}")

print("DONE")
