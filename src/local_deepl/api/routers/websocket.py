"""WebSocket progress channel + bidirectional cancel events.

Frames (all JSON, one per message):

- ``{"type": "progress", "status", "percent", "stage"}`` (legacy, also used for translate stage)
- ``{"type": "block_complete", "page_idx", "block_idx", "bbox", "text", "kind", "confidence"}``
- ``{"type": "translate_chunk_complete", "chunk_idx", "source_chars", "translated_text", "target_language"}``
- ``{"type": "cancelled", "status", "percent", "stage"}`` (sent when a cancel is honored)

Inbound: ``{"type": "cancel"}`` is honored as soon as the next progress tick
arrives. The worker checks :data:`ConnectionManager.cancel_flags` between
OCR blocks / translation chunks.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from local_deepl.api.routers import state

router = APIRouter()
_progress_service = state.progress_service


class ConnectionManager:
    """Tracks token-bound WebSocket progress channels."""

    def __init__(self) -> None:
        self.active: dict[str, WebSocket] = {}
        self._tokens: dict[str, str] = {}
        self._cancel_flags: dict[str, asyncio.Event] = {}

    async def connect(
        self, websocket: WebSocket, channel_id: str, session_token: str
    ) -> None:
        channel_id = _progress_service.validate_channel_id(channel_id)
        session_token = _progress_service.validate_session_token(session_token)
        await websocket.accept()
        self.active[channel_id] = websocket
        self._tokens[channel_id] = session_token
        self._cancel_flags[channel_id] = asyncio.Event()

    def disconnect(self, channel_id: str) -> None:
        self.active.pop(channel_id, None)
        self._tokens.pop(channel_id, None)
        self._cancel_flags.pop(channel_id, None)

    def is_authorized(self, channel_id: str | None, session_token: str | None) -> bool:
        if not channel_id or not session_token:
            return False
        expected_token = self._tokens.get(channel_id)
        if expected_token is None:
            return False
        try:
            return _progress_service.is_bound(
                channel_id=channel_id,
                session_token=session_token,
                expected_channel_id=channel_id,
                expected_session_token=expected_token,
            )
        except (TypeError, ValueError):
            return False

    def request_cancel(self, channel_id: str) -> None:
        """Mark a channel as cancelled; the worker will honor it on its next tick."""
        evt = self._cancel_flags.get(channel_id)
        if evt is not None:
            evt.set()

    def is_cancelled(self, channel_id: str | None) -> bool:
        if not channel_id:
            return False
        evt = self._cancel_flags.get(channel_id)
        return evt is not None and evt.is_set()

    async def send(self, channel_id: str | None, payload: dict[str, Any]) -> None:
        """Send a JSON frame to an active channel. Silently drops on disconnect."""
        if not channel_id:
            return
        ws = self.active.get(channel_id)
        if ws is None:
            return
        try:
            await ws.send_json(payload)
        except Exception:
            self.disconnect(channel_id)

    async def send_progress(
        self,
        channel_id: str | None,
        message: str,
        percent: int,
        stage: str = "",
        warning: bool = False,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_progress_frame(message, percent, stage, warning),
        )

    async def send_block(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
        block_idx: int,
        bbox: list[float],
        text: str,
        kind: str = "text",
        confidence: float | None = None,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_block_frame(
                page_idx=page_idx,
                block_idx=block_idx,
                bbox=bbox,
                text=text,
                kind=kind,
                confidence=confidence,
            ),
        )

    async def send_translate_chunk(
        self,
        channel_id: str | None,
        *,
        chunk_idx: int,
        source_chars: int,
        translated_text: str,
        target_language: str,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_translate_chunk_frame(
                chunk_idx=chunk_idx,
                source_chars=source_chars,
                translated_text=translated_text,
                target_language=target_language,
            ),
        )

    async def send_page_complete(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_page_complete_frame(
                page_idx=page_idx,
            ),
        )


manager = ConnectionManager()


@router.post("/api/progress/session")
async def create_progress_session(body: dict | None = None):
    """Issue an opaque websocket progress channel and binding token."""
    display_client_id = body.get("client_id") if body else None
    try:
        channel = _progress_service.create_channel(display_client_id=display_client_id)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=422,
            content={"error": "Invalid progress session parameters."},
        )
    return {
        "channel_id": channel.channel_id,
        "session_token": channel.session_token,
    }


@router.post("/api/progress/cancel/{channel_id}")
async def cancel_channel(channel_id: str, body: dict | None = None):
    """Set the cancel flag for an active channel."""
    channel_id = _progress_service.validate_channel_id(channel_id)
    manager.request_cancel(channel_id)
    return {"status": "cancel_requested"}


@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str, token: str = ""):
    """Accept a token-bound WebSocket connection for real-time progress updates.

    The server reads inbound ``{"type": "cancel"}`` messages and sets the
    cancel flag for the channel. The OCR/translate worker checks this flag
    between blocks/chunks and aborts the run cleanly.
    """
    try:
        await manager.connect(websocket, channel_id, token)
    except (TypeError, ValueError):
        await websocket.close(code=1008)
        return
    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                import json

                msg = json.loads(raw)
            except Exception:
                continue
            if isinstance(msg, dict) and msg.get("type") == "cancel":
                manager.request_cancel(channel_id)
    finally:
        manager.disconnect(channel_id)
