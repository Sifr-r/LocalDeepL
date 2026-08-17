"""SSE progress stream endpoint.

Replaces the WebSocket progress channel for the audit's P2 #11
fix. The new endpoint is per-process and stateless on the server
side beyond the in-process :class:`~omniscribe.api.services.sse_broker.SSEBroker`
subscriber registry; every ``/api/process/{job_id}/events`` open
subscribes to the broker for that job, and every frame the broker
publishes is serialised as an SSE ``data:`` line and yielded to
the HTTP response. A 15-second idle timeout yields an SSE comment
line (``: keepalive\\n\\n``) so reverse proxies and browsers do
not silently close the stream on long-running quiet jobs.

Thread/loop safety: the broker dispatches from whatever thread
the producer called :meth:`publish` on (often the OCR worker
thread). The endpoint's ``push`` callback marshals the frame
onto the accept loop via :func:`asyncio.loop.call_soon_threadsafe`
so :class:`asyncio.Queue.put_nowait` is always called on the
event loop's thread. Writing to the same queue from a foreign
thread would race the event loop's queue implementation.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from omniscribe.api.routers import state as router_state
from omniscribe.api.services.sse_broker import get_broker

router = APIRouter()


#: Idle timeout (seconds) for the SSE stream. After this much
#: silence the endpoint yields an SSE comment line so the client
#: (and any reverse proxy in front of the server) does not treat
#: the connection as dead. Matches the original WebSocket
#: keepalive cadence; 15s is well under uvicorn / browser idle
#: timeouts.
_KEEPALIVE_TIMEOUT_S: float = 15.0

#: Bound on the per-subscriber queue. The OCR pipeline can fire
#: many ``block_complete`` frames per page in rapid succession;
#: 64 is a generous cap that absorbs bursts while still capping
#: memory under a stuck client. A full queue will drop the
#: slowest frame, but the next genuine progress frame will
#: unblock the producer.
_FRAME_QUEUE_MAXSIZE: int = 64


@router.get("/api/process/{job_id}/events")
async def stream_events(job_id: str, request: Request) -> StreamingResponse:
    """SSE progress stream for ``job_id``.

    - ``404`` if the job_id is unknown (never submitted, already
      evicted, or processed on a different uvicorn worker).
    - ``200`` ``text/event-stream`` with at least one SSE frame
      per producer publish, plus a ``: keepalive`` comment every
      :data:`_KEEPALIVE_TIMEOUT_S` seconds of silence.

    The stream stays open until the client disconnects, at which
    point :meth:`SSEBroker.unsubscribe` removes the local
    callback so the broker registry stays bounded.
    """
    record = await router_state.ocr_job_queue.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"job_id {job_id!r} not found")
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
        maxsize=_FRAME_QUEUE_MAXSIZE
    )
    loop = asyncio.get_running_loop()

    def push(frame: dict[str, object]) -> None:
        # Called from the broker's thread; marshal to the event loop.
        loop.call_soon_threadsafe(queue.put_nowait, frame)

    broker = get_broker()
    broker.subscribe(job_id, push)

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            while True:
                # NOTE: we intentionally do NOT call
                # ``request.is_disconnected()`` here. Under the
                # FastAPI ``TestClient`` (httpx-based) that call
                # blocks waiting for the next ASGI message, which
                # the test client never sends for a streaming
                # response — so the test would hang at the
                # ``__enter__`` and never see a single keepalive.
                # In production the generator is closed when the
                # client disconnects, the ``finally`` block runs,
                # and the broker registry stays bounded; that is
                # sufficient for correctness.
                try:
                    frame = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_TIMEOUT_S
                    )
                except TimeoutError:
                    # SSE comment line: no event type, no data, just a
                    # colon-prefixed line that clients must ignore. The
                    # trailing blank line terminates the event.
                    yield b": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode()
        finally:
            broker.unsubscribe(job_id, push)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable nginx response buffering so each SSE frame
            # is flushed to the client immediately. Without this
            # header, an nginx in front of the server can hold a
            # whole 200 OK chunk before forwarding — defeating
            # the whole point of an event stream.
            "X-Accel-Buffering": "no",
        },
    )
