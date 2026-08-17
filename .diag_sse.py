"""Diagnostic script for SSE test hangs."""
import sys
sys.path.insert(0, "src")

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

try:
    app = FastAPI()
    app.include_router(events_module.router)
    client = TestClient(app)
    print("Opening stream...")
    with client.stream("GET", "/api/process/job-x/events") as response:
        print(f"  status={response.status_code}")
        print(f"  content-type={response.headers.get('content-type')}")
        print("  Reading first line...")
        import time
        t0 = time.monotonic()
        line = next(response.iter_lines())
        t1 = time.monotonic()
        print(f"  first_line={line!r} (elapsed={t1-t0:.2f}s)")
finally:
    router_state.ocr_job_queue = orig_queue
    events_module.get_broker.__globals__["_broker"] = orig_broker
print("DONE")
