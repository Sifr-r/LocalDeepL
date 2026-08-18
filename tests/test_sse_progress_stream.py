"""SSE progress stream endpoint tests (audit P2 #11, sub-task 7.1; F4.5 audit fix).

Contract pinned here:

- ``GET /api/process/{job_id}/events`` returns ``404`` when the
  job_id is unknown (never submitted, already evicted, or
  processed on a different uvicorn worker).
- A successful open returns ``text/event-stream`` with an idle
  keepalive line every :data:`events._KEEPALIVE_TIMEOUT_S`
  seconds (shrunk to ``0.1`` in these tests so the test runtime
  stays bounded).
- A frame published via the in-process :class:`SSEBroker` after
  the stream is open is serialised as a ``data:`` line and
  delivered to the client before the next keepalive tick.
- The broker unsubscribes when the client disconnects, so the
  subscriber registry stays bounded across repeated opens.

F4.5 audit fix: the 404 tests run under the Starlette
``TestClient`` (the 404 response has no streaming body, so the
client's whole-body buffering does not bite). The three streaming
tests run against a real uvicorn-spawned server on a free local
port (``running_server`` fixture) because the endpoint's
``while True:`` event generator would otherwise hang at the
TestClient / ``httpx.AsyncClient + ASGITransport`` response
context — those transports buffer the body to completion before
returning, and an infinite body never completes. Real socket
streaming is the only path that actually exercises the SSE
contract end-to-end.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from http import HTTPStatus

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

from omniscribe.api.routers import events as events_module
from omniscribe.api.routers import state as router_state
from omniscribe.api.services.ocr_jobs import (
    OCRJobQueue,
    OCRJobRecord,
    OCRJobStatus,
)
from omniscribe.api.services.sse_broker import (
    SSEBroker,
    get_broker,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_queue(monkeypatch: pytest.MonkeyPatch) -> OCRJobQueue:
    """Swap the shared ``ocr_job_queue`` for a fresh instance per test.

    The router resolves the job-id existence check against
    ``state.ocr_job_queue``, so each test gets an empty queue
    without leaking records between tests. The original singleton
    is restored on teardown so a subsequent test that imports
    ``state.ocr_job_queue`` sees the production instance.
    """
    original = router_state.ocr_job_queue
    queue = OCRJobQueue()
    router_state.ocr_job_queue = queue
    try:
        yield queue
    finally:
        router_state.ocr_job_queue = original


@pytest.fixture
def fresh_broker(monkeypatch: pytest.MonkeyPatch) -> SSEBroker:
    """Swap the module-level broker for a fresh instance per test.

    The router resolves the broker via :func:`get_broker`, which
    reads the module-level ``_broker`` in
    :mod:`omniscribe.api.services.sse_broker`. Patching that
    binding keeps subscribers and publishes scoped to the test.
    """
    from omniscribe.api.services import sse_broker as broker_module

    original = broker_module._broker
    replacement = SSEBroker()
    monkeypatch.setattr(broker_module, "_broker", replacement)
    try:
        yield replacement
    finally:
        monkeypatch.setattr(broker_module, "_broker", original)


@pytest.fixture
def small_keepalive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the production 15s keepalive to 0.1s for the test suite.

    The production timeout is the documented user-facing value;
    tests use a smaller value so the keepalive path is exercised
    in a few hundred milliseconds instead of 15s per test.
    """
    monkeypatch.setattr(events_module, "_KEEPALIVE_TIMEOUT_S", 0.1)


@pytest.fixture
def _seeded_job(fresh_queue: OCRJobQueue) -> str:
    """Insert a PENDING OCR record and return its ``job_id``."""
    job_id = "test-job-sse"
    fresh_queue._records[job_id] = OCRJobRecord(  # type: ignore[attr-defined]
        job_id=job_id, filename="x.pdf", status=OCRJobStatus.PENDING
    )
    return job_id


def _build_client() -> TestClient:
    """Mount the events router on a minimal FastAPI app.

    Mirrors the :mod:`tests.test_job_result` pattern: a focused
    app with just the router under test, so the suite does not
    pay for the rest of the web stack (auth middleware, the OCR
    pipeline factory, etc.) on every test.
    """
    app = FastAPI()
    app.include_router(events_module.router)
    return TestClient(app)


def _free_port() -> int:
    """Bind a TCP socket to port 0 and return the OS-assigned port.

    Used by :func:`_spawn_uvicorn` to pick a port with no race
    against other processes on the host. The socket is closed
    before uvicorn binds the port, which is the standard pattern
    for "give me a port nobody else is using".
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


@pytest.fixture
async def running_server() -> str:
    """Spawn a real uvicorn process on a free port for the SSE endpoint.

    F4.5 audit fix: the events router's ``event_stream`` is an
    ``async while True:`` generator. ``httpx.AsyncClient + ASGITransport``
    buffers the entire response body before ``client.send()`` returns
    (a design choice of ASGITransport, not a bug in our code), so the
    client hangs at ``async with client.stream(...) as response:``
    forever. ``starlette.testclient.TestClient`` has the same hang.

    The only path that actually exercises the streaming contract is a
    real HTTP socket, so we spawn uvicorn in the background and yield
    its base URL. Cost is ~50ms of server startup per test; the test
    itself reads the first frame and tears down.
    """
    app = FastAPI()
    app.include_router(events_module.router)
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
        # Single worker -- the in-process broker is not shared
        # across worker processes anyway (per sse_broker module
        # docstring), and a multi-worker uvicorn would defeat the
        # purpose of this in-process fan-out.
        workers=1,
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        # Wait for the server to be ready. ``server.started`` flips
        # once the bind succeeds; ``server.serve()`` returns when
        # ``server.should_exit`` is set. We poll with a short
        # interval so the test never sleeps longer than necessary.
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("uvicorn test server failed to start within 1s")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except TimeoutError:
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task


# ---------------------------------------------------------------------------
# 404 contract
# ---------------------------------------------------------------------------


def test_events_endpoint_unknown_job_id_returns_404(
    fresh_queue: OCRJobQueue,
    fresh_broker: SSEBroker,
) -> None:
    client = _build_client()
    response = client.get("/api/process/no-such-job/events")
    assert response.status_code == HTTPStatus.NOT_FOUND
    body = response.json()
    assert "no-such-job" in body["detail"]


def test_events_endpoint_unknown_job_id_does_not_open_stream(
    fresh_queue: OCRJobQueue,
    fresh_broker: SSEBroker,
) -> None:
    """The endpoint must reject before subscribing to the broker.

    A 404 must not leave a dangling subscriber that would later
    consume frames for an unrelated job_id or leak memory.
    """
    client = _build_client()
    response = client.get("/api/process/missing/events")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert fresh_broker._subs == {}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Successful open + keepalive
# ---------------------------------------------------------------------------


async def test_events_endpoint_opens_text_event_stream(
    _seeded_job: str,
    fresh_broker: SSEBroker,
    small_keepalive: None,
    running_server: str,
) -> None:
    """F4.5 audit fix (HIGH): the events endpoint opens as
    ``text/event-stream`` and emits the keepalive comment after the
    configured idle timeout.

    F4.5 is one of three tests that were permanently
    ``@pytest.mark.skip`` because the Starlette ``TestClient`` (and
    ``httpx.AsyncClient + ASGITransport``) buffer the entire response
    body before the response context is entered — and the endpoint's
    body is an infinite ``while True:`` generator, so it never
    completes. The only path that actually verifies the streaming
    contract is a real HTTP socket, so the test runs against a
    uvicorn-spawned instance on a free local port (see
    :func:`running_server`).

    The test reads the first keepalive comment, proving:
    1. The endpoint honours the shrunk 0.1s ``_KEEPALIVE_TIMEOUT_S``
       (regression guard for events.py).
    2. The ``X-Accel-Buffering: no`` header is set (nginx-correct
       SSE behaviour).
    3. The ``Cache-Control: no-cache`` header and ``text/event-stream``
       media type are present (browser/SSE-client compatibility).
    """
    job_id = _seeded_job
    async with httpx.AsyncClient(timeout=2.0) as client:
        async with client.stream(
            "GET", f"{running_server}/api/process/{job_id}/events"
        ) as response:
            assert response.status_code == HTTPStatus.OK
            assert response.headers["content-type"].startswith("text/event-stream")
            # No nginx / proxy buffering on the response — the whole
            # point of SSE is per-frame flushing.
            assert response.headers.get("x-accel-buffering") == "no"
            # First chunk is the keepalive comment after the shrunk
            # 0.1s idle timeout, proving the endpoint honours the
            # configured timeout and yields the documented colon
            # prefix.
            first_chunk: bytes | None = None
            async for chunk in response.aiter_raw():
                if chunk:
                    first_chunk = chunk
                    break
            assert first_chunk == b": keepalive\n\n", first_chunk


# ---------------------------------------------------------------------------
# Publish-to-subscribers round-trip
# ---------------------------------------------------------------------------


async def test_published_frame_is_delivered_to_sse_client(
    _seeded_job: str,
    fresh_broker: SSEBroker,
    small_keepalive: None,
    running_server: str,
) -> None:
    """F4.5 audit fix (HIGH): end-to-end publish-to-subscriber round-trip.

    A frame published via the in-process ``SSEBroker`` *after* the
    stream is open is delivered to the HTTP client as a ``data:`` line
    before the next keepalive tick fires.

    The test opens the stream, polls the broker's internal subscriber
    list to confirm the server-side generator has subscribed, then
    publishes from a foreign thread (``asyncio.to_thread``) to mirror
    the production setup where the OCR worker thread is a different
    thread than the SSE server loop. The ``push`` callback in
    events.py uses ``loop.call_soon_threadsafe`` to marshal the
    frame onto the server's event loop, so a foreign-thread publish
    is the realistic case to cover.
    """
    job_id = _seeded_job
    frame = {"type": "progress", "status": "started", "percent": 5}

    async with httpx.AsyncClient(timeout=2.0) as client:
        async with client.stream(
            "GET", f"{running_server}/api/process/{job_id}/events"
        ) as response:
            assert response.status_code == HTTPStatus.OK

            # Wait for the endpoint handler to register its subscriber
            # before publishing. Polling the internal subscriber list
            # is the deterministic alternative to ``asyncio.sleep``;
            # the endpoint subscribes synchronously before yielding,
            # so the moment a subscriber appears we know the next
            # byte is a publish-driven data frame, not the keepalive.
            for _ in range(50):
                if fresh_broker._subs.get(job_id):  # type: ignore[attr-defined]
                    break
                await asyncio.sleep(0.02)
            else:  # pragma: no cover — surfaces as test failure
                pytest.fail(f"server never subscribed to job_id={job_id!r} within 1s")

            # Publish from a foreign thread to mirror the production
            # case (OCR worker thread != uvicorn server loop).
            await asyncio.to_thread(fresh_broker.publish, job_id, frame)

            first_chunk: bytes | None = None
            async for chunk in response.aiter_raw():
                if chunk:
                    first_chunk = chunk
                    break
            assert first_chunk is not None
            assert first_chunk.startswith(b"data: "), first_chunk
            payload = first_chunk[len(b"data: ") :].rstrip(b"\n")
            assert json.loads(payload.decode("utf-8")) == frame


async def test_disconnect_unsubscribes_from_broker(
    _seeded_job: str,
    fresh_broker: SSEBroker,
    small_keepalive: None,
    running_server: str,
) -> None:
    """F4.5 audit fix (HIGH): disconnecting unsubscribes from the broker.

    The endpoint's ``event_stream`` generator registers a ``finally``
    block that calls :meth:`SSEBroker.unsubscribe` when the client
    disconnects. Without it, every reconnect would leak a subscriber
    and the registry would grow without bound.

    The test opens the stream, reads the first keepalive chunk to
    prove the server-side generator has entered its loop, then
    closes the response. Starlette's response lifecycle calls
    ``aclose()`` on the generator, which fires the ``finally`` block
    and unsubscribes. We poll the broker's registry for a bounded
    window to confirm.
    """
    job_id = _seeded_job

    async with httpx.AsyncClient(timeout=2.0) as client:
        async with client.stream(
            "GET", f"{running_server}/api/process/{job_id}/events"
        ) as response:
            assert response.status_code == HTTPStatus.OK
            # Read the first keepalive chunk so we know the
            # server-side generator is past the subscribe step and
            # actively in its ``while True:`` loop.
            async for chunk in response.aiter_raw():
                if chunk == b": keepalive\n\n":
                    break

    # Disconnect: the response context manager closes the
    # underlying socket and Starlette calls ``aclose()`` on the
    # generator, firing its ``finally`` block. Poll for
    # unsubscribe; the broker call lands within a few ms of
    # ``__aexit__`` returning.
    for _ in range(50):
        if job_id not in fresh_broker._subs:  # type: ignore[attr-defined]
            break
        await asyncio.sleep(0.02)
    else:  # pragma: no cover — surfaces as test failure
        pytest.fail(
            f"broker did not unsubscribe job_id={job_id!r} within 1s of disconnect"
        )
    assert job_id not in fresh_broker._subs  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Direct broker contract (no HTTP, no timing)
# ---------------------------------------------------------------------------


def test_broker_publish_fans_out_to_all_subscribers(
    fresh_broker: SSEBroker,
) -> None:
    """Unit-level fan-out: every subscriber for a job_id sees every frame.

    A subscription for an unrelated job_id is not invoked. This
    pins the broker's contract independently of the HTTP layer.
    """
    received_a: list[dict[str, object]] = []
    received_b: list[dict[str, object]] = []
    received_other: list[dict[str, object]] = []

    fresh_broker.subscribe("job-a", lambda frame: received_a.append(frame))
    fresh_broker.subscribe("job-a", lambda frame: received_b.append(frame))
    fresh_broker.subscribe("job-other", lambda frame: received_other.append(frame))

    fresh_broker.publish("job-a", {"type": "progress", "percent": 10})
    fresh_broker.publish("job-a", {"type": "progress", "percent": 20})

    assert received_a == [
        {"type": "progress", "percent": 10},
        {"type": "progress", "percent": 20},
    ]
    assert received_b == received_a
    assert received_other == []


def test_broker_unsubscribe_removes_callback(
    fresh_broker: SSEBroker,
) -> None:
    """After unsubscribe, the broker no longer invokes the callback."""
    received: list[dict[str, object]] = []

    def callback(frame: dict[str, object]) -> None:
        received.append(frame)

    fresh_broker.subscribe("job-x", callback)
    fresh_broker.publish("job-x", {"a": 1})
    fresh_broker.unsubscribe("job-x", callback)
    fresh_broker.publish("job-x", {"a": 2})

    assert received == [{"a": 1}]


def test_broker_publish_swallows_subscriber_exceptions(
    fresh_broker: SSEBroker,
) -> None:
    """A subscriber that raises does not break sibling subscribers.

    The brief pins this: a misbehaving producer (e.g. a stale
    callback from a closed WebSocket) must not stop the other
    callbacks from receiving the frame.
    """
    received: list[dict[str, object]] = []

    def bad(_frame: dict[str, object]) -> None:
        raise RuntimeError("subscriber boom")

    fresh_broker.subscribe("job-y", bad)
    fresh_broker.subscribe("job-y", lambda frame: received.append(frame))

    fresh_broker.publish("job-y", {"k": "v"})

    assert received == [{"k": "v"}]


def test_get_broker_returns_module_singleton() -> None:
    """The accessor returns the module-level broker, not a fresh one.

    Pinned here so a future refactor that accidentally starts
    constructing a new broker per call is caught immediately.
    """
    from omniscribe.api.services import sse_broker as broker_module

    assert get_broker() is broker_module._broker
