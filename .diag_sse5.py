"""Diagnostic — does ANY streaming response work with TestClient?"""
import sys
sys.path.insert(0, "src")

import time
import threading
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse

# Trivial streaming app
app = FastAPI()

@app.get("/stream")
def stream():
    def gen():
        yield b"hello\n"
        yield b"world\n"
    return StreamingResponse(gen(), media_type="text/plain")

client = TestClient(app)

def reader():
    try:
        with client.stream("GET", "/stream") as response:
            print(f"  status={response.status_code}")
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
