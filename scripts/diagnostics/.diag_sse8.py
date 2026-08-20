"""Diagnostic — copy SSE endpoint setup exactly but minimal generator.

See also ``scripts/diagnostics/test_sse_keepalive.py`` for the canonical
keepalive-line smoke test used by CI.
"""
import sys
sys.path.insert(0, "src")

import asyncio
import json
import time
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse

app = FastAPI()

# Mimic state.ocr_job_queue behavior
class FakeQueue:
    def __init__(self):
        self._records = {"job-x": {"id": "job-x"}}
    async def get(self, job_id):
        return self._records.get(job_id)

fake_state = type("S", (), {"ocr_job_queue": FakeQueue()})()

@app.get("/api/process/{job_id}/events")
async def stream_events(job_id: str):
    async def event_stream():
        yield b": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

client = TestClient(app)

def reader():
    try:
        with client.stream("GET", "/api/process/job-x/events") as response:
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
t.join(timeout=5.0)
print(f"elapsed={time.monotonic()-t0:.2f}s alive={t.is_alive()}")
print("DONE")
