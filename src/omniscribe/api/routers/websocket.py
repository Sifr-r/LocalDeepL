"""WebSocket progress channel + bidirectional cancel events.

Frames (all JSON, one per message):

- ``{"type": "progress", "status", "percent", "stage"}`` (legacy, also used for translate stage)
- ``{"type": "block_complete", "page_idx", "block_idx", "bbox", "text", "kind", "confidence"}``
- ``{"type": "translate_chunk_complete", "chunk_idx", "source_chars", "translated_text", "target_language"}``
- ``{"type": "cancelled", "status", "percent", "stage"}`` (sent when a cancel is honored)

Inbound: ``{"type": "cancel"}`` is honored as soon as the next progress tick
arrives. The worker checks :data:`ConnectionManager.cancel_flags` between
OCR blocks / translation chunks.

Process-lifetime boundary
-------------------------

This module owns two pieces of process-bound state:

- ``manager`` (the module-level :class:`ConnectionManager` singleton)
  with three internal dicts: ``manager.active`` (channel_id → live
  :class:`fastapi.WebSocket`), ``manager._tokens`` (channel_id →
  session_token, used for ``is_authorized`` checks), and
  ``manager._cancel_flags`` (channel_id → :class:`asyncio.Event`,
  flipped by :meth:`ConnectionManager.request_cancel` and read by the
  OCR/translate worker via :meth:`ConnectionManager.is_cancelled`).
- ``_progress_service`` (the :class:`ProgressService` resolved from
  ``state.progress_service``), used to validate token shape and compare
  bindings.

Both live in the Python process that runs the uvicorn worker. A
restart — or simply reloading this router module — empties ``active``,
``_tokens``, and ``_cancel_flags`` in one shot: every channel that was
open is gone, every in-flight cancel flag is lost, and clients that
reconnect with the old ``channel_id`` will fail authentication
(:meth:`ConnectionManager.is_authorized` returns ``False`` because the
expected token is no longer in ``_tokens``). The worker checks
``is_cancelled`` between blocks, so a process kill mid-run silently
aborts any unsent cancellation; there is no on-disk durability here.

See the *Known Tech Debt* section of ``AGENTS.md`` for the project-level
acknowledgement: "Job/artifact state is in-memory only
(``api/routers/state.py`` singletons) — restarts lose history; no
horizontal scaling."
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from omniscribe.api.routers import state

router = APIRouter()
_progress_service = state.progress_service


@runtime_checkable
class ConnectionManagerLike(Protocol):
    """Structural surface that the chunked runner depends on.

    Declared as a ``Protocol`` so the chunked runner can be type-hinted
    against the real :class:`ConnectionManager` (or a stub for tests)
    without importing the websocket router at module load time. Keeping
    the surface here means the runner does not need to know about
    WebSocket internals — it just calls ``send_progress``,
    ``send_block``, ``is_cancelled``, and friends.
    """

    def is_cancelled(self, channel_id: str | None) -> bool: ...

    async def send_progress(
        self,
        channel_id: str | None,
        message: str,
        percent: int,
        stage: str = "",
        warning: bool = False,
    ) -> None: ...

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
    ) -> None: ...

    async def send_page_complete(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
    ) -> None: ...

    async def send_block_retry(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        confidence: float,
        target: float,
    ) -> None: ...

    async def send_block_revised(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        bbox: list[float],
        text: str,
        kind: str = "text",
        confidence: float | None = None,
    ) -> None: ...

    async def send_quality_summary(
        self,
        channel_id: str | None,
        *,
        scope: str,
        target: float,
        avg_confidence: float,
        repaired_count: int,
        below_target_count: int,
        page_idx: int | None = None,
    ) -> None: ...

    async def send_chunk_init(
        self,
        channel_id: str | None,
        *,
        total_chunks: int,
    ) -> None: ...

    async def send_chunk_complete(
        self,
        channel_id: str | None,
        *,
        chunk_idx: int,
        total_chunks: int,
        page_range: str,
        source_pages: list[int],
        text_chars_so_far: int,
        overall_percent: int | None = None,
    ) -> None: ...


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

    async def send_block_retry(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        confidence: float,
        target: float,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_block_retry_frame(
                page_idx=page_idx,
                block_idx=block_idx,
                attempt=attempt,
                confidence=confidence,
                target=target,
            ),
        )

    async def send_block_revised(
        self,
        channel_id: str | None,
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        bbox: list[float],
        text: str,
        kind: str = "text",
        confidence: float | None = None,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_block_revised_frame(
                page_idx=page_idx,
                block_idx=block_idx,
                attempt=attempt,
                bbox=bbox,
                text=text,
                kind=kind,
                confidence=confidence,
            ),
        )

    async def send_quality_summary(
        self,
        channel_id: str | None,
        *,
        scope: str,
        target: float,
        avg_confidence: float,
        repaired_count: int,
        below_target_count: int,
        page_idx: int | None = None,
    ) -> None:
        await self.send(
            channel_id,
            _progress_service.build_quality_summary_frame(
                scope=scope,
                target=target,
                avg_confidence=avg_confidence,
                repaired_count=repaired_count,
                below_target_count=below_target_count,
                page_idx=page_idx,
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

    async def send_chunk_init(
        self,
        channel_id: str | None,
        *,
        total_chunks: int,
    ) -> None:
        """Emit the ``chunk_init`` pre-amble for a chunked OCR run."""
        await self.send(
            channel_id,
            _progress_service.build_chunk_init_frame(total_chunks=total_chunks),
        )

    async def send_chunk_complete(
        self,
        channel_id: str | None,
        *,
        chunk_idx: int,
        total_chunks: int,
        page_range: str,
        source_pages: list[int],
        text_chars_so_far: int,
        overall_percent: int | None = None,
    ) -> None:
        """Emit the per-chunk terminal frame after a chunk finishes."""
        await self.send(
            channel_id,
            _progress_service.build_chunk_complete_frame(
                chunk_idx=chunk_idx,
                total_chunks=total_chunks,
                page_range=page_range,
                source_pages=list(source_pages),
                text_chars_so_far=text_chars_so_far,
                overall_percent=overall_percent,
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
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
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
