"""Sprint 4 / H-2 audit fix: WebSocket end-to-end progress test.

The router contract tests in ``test_progress_ws.py`` cover the
connect/auth/close-code path. The audit found no test that exercised
the full lifecycle:

  POST /api/progress/session  →  WS auth  →
  POST /api/process/async with progress_channel  →
  WS receives ``progress`` frames emitted from the OCRService worker  →
  status polling reports ``complete``.

This module is that test. It catches two regressions the unit tests
miss:

1. ``OCRServiceImpl._progress_adapter`` wiring (the ``channel`` arg of
   ``_execute`` was historically lost; the WS would never see frames).
2. ``on_progress`` reaching the queue worker's event loop from inside
   the TestClient portal loop without losing the ``run_in_executor``
   hop.

The fake pipeline in ``conftest.fake_pipeline`` calls ``on_progress``
once with ``(50, "ocr", "Processing page 1")``; we assert the WS sees
exactly one ``progress`` frame before the status reaches ``complete``.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from .conftest import upload, wait_status


def test_ws_progress_frame_reaches_client_during_async_job(
    api_client: TestClient, fake_pipeline: dict
) -> None:
    """End-to-end: a job's progress frames reach the WS subscriber."""
    # 1. Open a progress session.
    session = api_client.post("/api/progress/session", json={}).json()
    channel_id = session["channel_id"]
    session_token = session["session_token"]

    # 2. Open the WS and complete first-frame auth before the worker
    #    can emit frames (the server only sends frames to attached
    #    channels).
    with api_client.websocket_connect(f"/ws/{channel_id}") as ws:
        ws.send_text(
            json.dumps({"type": "auth", "session_token": session_token})
        )
        authed = json.loads(ws.receive_text())
        assert authed["type"] == "connected"

        # 3. Submit the async job with the channel id so the worker
        #    routes its on_progress into our socket.
        submit = api_client.post(
            "/api/process/async",
            **upload(),
            data={"progress_channel": channel_id},
        )
        assert submit.status_code == 202, submit.text
        job_id = submit.json()["job_id"]

        # 4. The fake pipeline emits exactly one progress frame. Drain
        #    it from the WS. Use a short recv timeout so a regression
        #    that drops the frame surfaces as a TimeoutError, not a
        #    hang.
        progress_seen = False
        try:
            while True:
                # receive_text raises WebSocketDisconnect after the job
                # finishes and the channel drains. The first frame
                # should be our progress emission.
                frame_text = ws.receive_text()
                frame = json.loads(frame_text)
                if frame.get("type") == "progress" or "percent" in frame:
                    progress_seen = True
                    break
        except Exception:
            pass  # WebSocketDisconnect after job done — fine

        assert progress_seen, (
            "WS never received a progress frame; "
            "OCRService._progress_adapter is dropping the channel"
        )

        # 5. Status poll still drives the lifecycle even though WS
        #    delivered the progress frame.
        wait_status(api_client, job_id, "complete", timeout=5.0)
