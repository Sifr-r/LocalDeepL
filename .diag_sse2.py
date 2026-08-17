"""Diagnostic script for SSE test hangs — read raw bytes with timeout."""
import sys
sys.path.insert(0, "src")

import asyncio
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import events as events_module
from omniscribe.api.services.sse_broker import SSEBroker
from omniscribe.api.services.ocr_jobs import OCRJobQueue, OCRJobRecord, OCRJobStatus
from omniscribe.api.routers import state as router_state

# Setup
orig_queue = router_state.ocr_job_queue
orig_broker = events_module.get_broker.__globals__["_broker"]
queue = OCRJobQueue()
queue._records["job-x"] = OCRJobRecord(
    job_id="job-x", filename="x.pdf", status=OCRJobStatus.PENDING
)
router_state.ocr_job_queue = queue
events_module.get_broker.__globals__["_broker"] = SSEBroker()
events_module._KEEPALIVE_TIMEOUT_S = 0.1

app = FastAPI()
app.include_router(events_module.router)
client = TestClient(app)

print("Opening stream...")
with client.stream("GET", "/api/process/job-x/events") as response:
    print(f"  status={response.status_code}")
    print(f"  content-type={response.headers.get('content-type')}")
    print("  Trying iter_lines with deadline...")
    # Use a thread with a deadline to break out of the hang
    result = {}
    def reader():
        try:
            line = next(response.iter_lines())
            result["line"] = line
        except Exception as e:
            result["error"] = e
    t = threading.Thread(target=reader, daemon=True)
    t0 = time.monotonic()
    t.start()
    t.join(timeout=3.0)
    print(f"  elapsed={time.monotonic()-t0:.2f}s result={result!r}")
    if t.is_alive():
        print("  THREAD STILL ALIVE — iter_lines blocked")

# Cleanup
router_state.ocr_job_queue = orig_queue
events_module.get_broker.__globals__["_broker"] = orig_broker
print("DONE")
