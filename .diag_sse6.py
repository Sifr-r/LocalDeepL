"""Diagnostic — add lots of print statements to find the hang."""
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

print(f"t={time.monotonic():.2f}: before stream()")

def reader():
    try:
        print(f"t={time.monotonic():.2f}: thread start, opening stream")
        with client.stream("GET", "/api/process/job-x/events") as response:
            print(f"t={time.monotonic():.2f}: status={response.status_code}")
            print(f"t={time.monotonic():.2f}: content-type={response.headers.get('content-type')}")
            print(f"t={time.monotonic():.2f}: about to iter_lines")
            for line in response.iter_lines():
                print(f"t={time.monotonic():.2f}: line={line!r}")
                break
    except Exception as e:
        print(f"t={time.monotonic():.2f}: error={e!r}")

t = threading.Thread(target=reader, daemon=True)
t0 = time.monotonic()
t.start()
t.join(timeout=3.0)
print(f"t={time.monotonic():.2f}: elapsed={time.monotonic()-t0:.2f}s alive={t.is_alive()}")

router_state.ocr_job_queue = orig_queue
events_module.get_broker.__globals__["_broker"] = orig_broker
print("DONE")
