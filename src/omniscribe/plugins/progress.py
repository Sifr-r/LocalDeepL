"""ProgressService plugin — WebSocket progress channels with cross-loop marshaling.

Channels are short-lived (TTL seconds from config) and bound to one session
token. The WS handler records each connection's accept loop; sends issued
from any other loop/thread are marshaled back onto it via
``asyncio.run_coroutine_threadsafe`` (the AGENTS.md cross-loop contract).

Frames are line-delimited JSON text: every text frame is one JSON object
terminated by ``\\n`` — the frontend parses per line to survive concatenated
bursts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple, Protocol, runtime_checkable

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from omniscribe.config import RuntimeSettings, load_settings
from omniscribe.harness.context import Context
from omniscribe.harness.events import AgentEvent
from omniscribe.harness.plugin import Plugin
from omniscribe.plugins.state_backend import ChannelRecord, StateBackend

_LOGGER = logging.getLogger("omniscribe.plugins.progress")

_AUTH_FRAME_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ProgressFrame(AgentEvent):
    """Live progress frame destined for a channel (and the event bus)."""

    job_id: str
    channel_id: str | None = None
    frame: dict[str, Any] = field(default_factory=dict)


class ChannelHandle(NamedTuple):
    """Channel id plus the session token required to attach to it."""

    channel_id: str
    session_token: str


@runtime_checkable
class ProgressService(Protocol):
    """Channel registry + WebSocket fan-out seam."""

    async def open_channel(self, *, job_id: str = "") -> ChannelHandle: ...

    async def get_channel(self, channel_id: str) -> ChannelRecord | None: ...

    async def consume_channel(
        self, channel_id: str, session_token: str
    ) -> ChannelRecord | None: ...

    async def broadcast(self, channel_id: str, frame: Mapping[str, Any]) -> int: ...

    async def emit_progress(
        self, job_id: str, channel_id: str | None, frame: Mapping[str, Any]
    ) -> int: ...

    async def cancel(self, channel_id: str) -> bool: ...

    def is_cancelled(self, channel_id: str) -> bool: ...


class _Connection:
    """One attached socket plus the loop that accepted it."""

    def __init__(self, ws: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.ws = ws
        self.loop = loop
        self._lock = asyncio.Lock()

    async def send(self, frame: Mapping[str, Any]) -> None:
        async with self._lock:
            await self.ws.send_text(json.dumps(dict(frame)) + "\n")


def _build_foreign_send_done_callback(
    service: ProgressServiceImpl, channel_id: str, connection: Any
) -> Callable[[concurrent.futures.Future[Any]], None]:
    """Return a ``Future.add_done_callback`` callable for the foreign-loop branch.

    Extracted as a top-level helper so mypy can infer the closure
    parameter types instead of reporting ``Cannot infer type of
    lambda``. ``asyncio.run_coroutine_threadsafe`` returns a
    ``concurrent.futures.Future``, which is what ``add_done_callback``
    expects.
    """

    def _done(fut: concurrent.futures.Future[Any]) -> None:
        service._on_foreign_send_done(channel_id, connection, fut)

    return _done


class ProgressServiceImpl:
    """In-process connection registry persisted via the StateBackend."""

    def __init__(
        self,
        ctx: Context,
        backend: StateBackend,
        *,
        frame_cap: int = 1000,
        channel_ttl_seconds: int = 600,
    ) -> None:
        self._ctx = ctx
        self._backend = backend
        self._frame_cap = frame_cap
        self._channel_ttl_seconds = channel_ttl_seconds
        self._connections: dict[str, set[_Connection]] = {}
        self._cancelled: set[str] = set()
        self._frame_counts: dict[str, int] = {}

    # -- channel lifecycle ----------------------------------------------------

    async def open_channel(self, *, job_id: str = "") -> ChannelHandle:
        handle = ChannelHandle(
            channel_id=uuid.uuid4().hex, session_token=secrets.token_urlsafe(32)
        )
        await self._backend.put_channel(
            handle.channel_id, handle.session_token, job_id, self._channel_ttl_seconds
        )
        return handle

    async def get_channel(self, channel_id: str) -> ChannelRecord | None:
        return await self._backend.get_channel(channel_id)

    async def consume_channel(
        self, channel_id: str, session_token: str
    ) -> ChannelRecord | None:
        return await self._backend.consume_channel(channel_id, session_token)

    # -- connection registry ----------------------------------------------------

    def attach(
        self, channel_id: str, ws: Any, loop: asyncio.AbstractEventLoop
    ) -> _Connection:
        connection = _Connection(ws, loop)
        self._connections.setdefault(channel_id, set()).add(connection)
        return connection

    def detach(self, channel_id: str, connection: _Connection) -> None:
        connections = self._connections.get(channel_id)
        if connections is not None:
            connections.discard(connection)
            if not connections:
                self._connections.pop(channel_id, None)

    # -- fan-out --------------------------------------------------------------------

    async def broadcast(self, channel_id: str, frame: Mapping[str, Any]) -> int:
        """Send ``frame`` to every attached socket; returns the fan-out count.

        Sends from a foreign loop are marshaled onto the connection's accept
        loop; sends from the current loop are awaited directly.
        """
        connections = list(self._connections.get(channel_id, ()))
        if not connections:
            return 0
        sent_so_far = self._frame_counts.get(channel_id, 0)
        if sent_so_far >= self._frame_cap:
            _LOGGER.warning(
                "progress channel %s hit its %d-frame cap", channel_id, self._frame_cap
            )
            return 0
        self._frame_counts[channel_id] = sent_so_far + 1
        current = asyncio.get_running_loop()
        sent = 0
        for connection in connections:
            if connection.loop is current:
                try:
                    await connection.send(frame)
                    sent += 1
                except Exception:
                    _LOGGER.warning(
                        "progress send failed on channel %s; detaching", channel_id
                    )
                    self.detach(channel_id, connection)
            else:
                # H-2 audit fix: marshal the foreign-loop send and
                # detach on failure. ``asyncio.run_coroutine_threadsafe``
                # returns a ``concurrent.futures.Future`` whose
                # ``add_done_callback`` fires when the coroutine settles.
                # If the coroutine raises (the socket was closed between
                # the loop's accept phase and our send attempt), the
                # future's exception is surfaced and we detach the
                # connection so the next broadcast doesn't try to write
                # to a dead socket. Previously the future's exception
                # was silently swallowed — the same-loop branch already
                # detaches, this brings the foreign-loop branch to parity.
                future = asyncio.run_coroutine_threadsafe(
                    connection.send(frame), connection.loop
                )
                future.add_done_callback(
                    _build_foreign_send_done_callback(self, channel_id, connection)
                )
                sent += 1
        return sent

    def _on_foreign_send_done(
        self, channel_id: str, connection: Any, future: Any
    ) -> None:
        """Callback fired when a foreign-loop ``connection.send`` settles.

        Sprint 2 / H-2 audit fix: detach the connection on exception
        so the next broadcast does not try to write to a socket that
        already errored. ``asyncio.run_coroutine_threadsafe`` returns
        a ``concurrent.futures.Future`` (not an awaitable), so we
        inspect the exception via ``future.exception()``.
        """
        exc = future.exception()
        if exc is not None:
            _LOGGER.warning(
                "foreign-loop progress send failed on channel %s (%s); detaching",
                channel_id,
                exc,
            )
            try:
                self.detach(channel_id, connection)
            except KeyError:
                pass
            except Exception:
                _LOGGER.exception("detach after foreign-loop send failure also failed")

    async def emit_progress(
        self, job_id: str, channel_id: str | None, frame: Mapping[str, Any]
    ) -> int:
        """Bus-visible wrapper: emits a ProgressFrame event then fans out."""
        await self._ctx.emit(
            ProgressFrame(job_id=job_id, channel_id=channel_id, frame=dict(frame))
        )
        if channel_id is None:
            return 0
        return await self.broadcast(channel_id, frame)

    # -- cancellation ----------------------------------------------------------------

    async def cancel(self, channel_id: str) -> bool:
        self._cancelled.add(channel_id)
        await self.broadcast(
            channel_id, {"type": "cancelled", "status": "Cancelled by user."}
        )
        return True

    def is_cancelled(self, channel_id: str) -> bool:
        return channel_id in self._cancelled


# -- HTTP + WebSocket routes --------------------------------------------------------


class _SessionRequest(BaseModel):
    client_id: str = ""


def build_progress_router(
    service: ProgressServiceImpl,
    settings: RuntimeSettings | None = None,
) -> APIRouter:
    """Routes for the progress session, cancel mirror, and WS attach."""
    router = APIRouter(tags=["progress"])
    if settings is None:
        settings = load_settings()

    @router.post("/api/progress/session")
    async def open_session(body: _SessionRequest) -> dict[str, str]:
        handle = await service.open_channel(job_id=body.client_id)
        return {
            "channel_id": handle.channel_id,
            "session_token": handle.session_token,
        }

    @router.post("/api/progress/cancel/{channel_id}")
    async def cancel_channel(
        channel_id: str,
        session_token: str | None = Query(None),
        x_session_token: str | None = Header(None, alias="X-Session-Token"),
    ) -> dict[str, bool]:
        # Audit S6: a cancel request is a denial-of-service surface
        # against an in-progress job (an attacker who knows the
        # ``channel_id`` can cancel a victim's job). The handler now
        # requires a session token (X-Session-Token header or
        # ``?session_token=`` query param, the latter accepted for
        # parity with the SSE channel_id query-param convention)
        # and validates it via ``secrets.compare_digest`` against the
        # channel's session_token (the same token the legitimate
        # client received in the ``job_started`` / ``process``
        # response). The BearerAuthMiddleware covers the non-loopback
        # deployments (Profiles 2 + 3); the session token covers the
        # loopback dev profile (Profile 1) where bearer auth is not
        # required.
        token = x_session_token or session_token
        if not token:
            raise HTTPException(
                status_code=401,
                detail="session token required (X-Session-Token header or session_token query param)",
            )
        record = await service.get_channel(channel_id)
        if record is None:
            raise HTTPException(status_code=404, detail="channel not found")
        if not secrets.compare_digest(record.session_token, token):
            raise HTTPException(status_code=403, detail="invalid session token")
        cancelled = await service.cancel(channel_id)
        return {"cancelled": cancelled}

    async def _handle_ws(websocket: WebSocket, channel_id: str) -> None:
        # S14 (audit 4.14): WebSocket origin check. The check is
        # deny-by-default against the operator-supplied
        # ``OMNISCRIBE_CORS_ORIGINS`` allowlist — but it has three
        # *fall-through* cases that intentionally allow the request
        # through to the auth layer:
        #
        #   1. ``origin`` is None / empty — non-browser clients
        #      (Flutter desktop, curl, the bundled binary) do not
        #      send an Origin header at all. The auth frame that
        #      follows the upgrade is the only gate for them.
        #   2. ``cors_origins`` is empty — operator opted out of
        #      cross-origin restrictions entirely (loopback dev
        #      profile; the only guard is the loopback bind itself).
        #   3. ``*`` is in ``cors_origins`` — operator chose the
        #      wildcard, which the audit's C2 finding flagged
        #      because it does not combine with credentials, so
        #      this is a "trusted environment" signal.
        #
        # The cross-origin check is *first*, before auth, so a
        # browser-origin mismatch is rejected without consuming a
        # session token. See ``docs/SECURITY.md`` §"WebSocket origin
        # check" for the full threat model.
        origin = websocket.headers.get("origin")
        cors_origins = settings.cors_origins
        if (
            origin
            and cors_origins
            and "*" not in cors_origins
            and origin not in cors_origins
        ):
            await websocket.close(code=4403, reason="origin not allowed")
            return

        query_token = websocket.query_params.get("token") or ""
        await websocket.accept()
        if query_token:
            record = await service.consume_channel(channel_id, query_token)
            if record is None:
                await websocket.close(code=4401, reason="invalid channel token")
                return
        else:
            # Frontend contract: the session token rides in the first frame,
            # never in the URL (query-string secrets leak into logs).
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_AUTH_FRAME_TIMEOUT_SECONDS
                )
                payload = json.loads(raw)
            except (TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
                await websocket.close(code=1008, reason="missing auth frame")
                return
            token = payload.get("session_token") if isinstance(payload, dict) else None
            if (
                not isinstance(payload, dict)
                or payload.get("type") != "auth"
                or not token
            ):
                await websocket.close(code=1008, reason="malformed auth frame")
                return
            record = await service.consume_channel(channel_id, str(token))
            if record is None:
                await websocket.close(code=1008, reason="auth rejected")
                return
        loop = asyncio.get_running_loop()
        connection = service.attach(channel_id, websocket, loop)
        try:
            await service.broadcast(
                channel_id, {"type": "connected", "channel_id": channel_id}
            )
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    msg_type = message.get("type")
                    if msg_type == "cancel":
                        await service.cancel(channel_id)
                    elif msg_type == "ping":
                        await service.broadcast(channel_id, {"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            service.detach(channel_id, connection)

    @router.websocket("/ws/{channel_id}")
    async def progress_ws(websocket: WebSocket, channel_id: str) -> None:
        await _handle_ws(websocket, channel_id)

    @router.websocket("/api/progress/ws/{channel_id}")
    async def progress_ws_alias(websocket: WebSocket, channel_id: str) -> None:
        await _handle_ws(websocket, channel_id)

    return router


# -- plugin -------------------------------------------------------------------------


class ProgressSchema(BaseModel):
    frame_cap: int = 1000
    channel_ttl_seconds: int = 600


class ProgressPlugin(Plugin):
    """Registers the ProgressService and mounts its routes."""

    Schema = ProgressSchema

    async def apply(self, ctx: Context) -> None:
        backend = ctx.inject(StateBackend)
        service = ProgressServiceImpl(
            ctx,
            backend,
            frame_cap=int(self.config.get("frame_cap", 1000)),
            channel_ttl_seconds=int(self.config.get("channel_ttl_seconds", 600)),
        )
        ctx.service(ProgressService, service)
        try:
            from omniscribe.plugins.runtime import RuntimeService

            runtime_settings = (
                ctx.inject(RuntimeService).settings if ctx.has(RuntimeService) else None
            )
        except Exception:
            runtime_settings = None
        ctx.mount_router(build_progress_router(service, settings=runtime_settings))
        _LOGGER.info(
            "progress plugin mounted (frame_cap=%d)",
            int(self.config.get("frame_cap", 1000)),
        )


plugin = ProgressPlugin()
