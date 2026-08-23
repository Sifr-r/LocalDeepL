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
import json
import logging
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple, Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

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
                asyncio.run_coroutine_threadsafe(
                    connection.send(frame), connection.loop
                )
                sent += 1
        return sent

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


def build_progress_router(service: ProgressServiceImpl) -> APIRouter:
    """Routes for the progress session, cancel mirror, and WS attach."""
    router = APIRouter(tags=["progress"])

    @router.post("/api/progress/session")
    async def open_session(body: _SessionRequest) -> dict[str, str]:
        handle = await service.open_channel(job_id=body.client_id)
        return {
            "channel_id": handle.channel_id,
            "session_token": handle.session_token,
        }

    @router.post("/api/progress/cancel/{channel_id}")
    async def cancel_channel(channel_id: str) -> dict[str, bool]:
        cancelled = await service.cancel(channel_id)
        return {"cancelled": cancelled}

    async def _handle_ws(websocket: WebSocket, channel_id: str) -> None:
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
                if isinstance(message, dict) and message.get("type") == "cancel":
                    await service.cancel(channel_id)
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
        ctx.mount_router(build_progress_router(service))
        _LOGGER.info(
            "progress plugin mounted (frame_cap=%d)",
            int(self.config.get("frame_cap", 1000)),
        )


plugin = ProgressPlugin()
