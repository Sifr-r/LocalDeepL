"""Diagnostic script — minimal streaming test, no with-block.

See also ``scripts/diagnostics/test_sse_keepalive.py`` for the canonical
keepalive-line smoke test used by CI.
"""
import sys
sys.path.insert(0, "src")

import time
import threading

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

print("Opening stream (no with-block)...")
t0 = time.monotonic()
response = client.get("/api/process/job-x/events")
print(f"  status={response.status_code} ({time.monotonic()-t0:.2f}s)")
print(f"  content-type={response.headers.get('content-type')}")
print(f"  content-length={response.headers.get('content-length')}")
print(f"  text[:200]={response.text[:200]!r}")

# Cleanup
router_state.ocr_job_queue = orig_queue
events_module.get_broker.__globals__["_broker"] = orig_broker
print(f"DONE in {time.monotonic()-t0:.2f}s")
