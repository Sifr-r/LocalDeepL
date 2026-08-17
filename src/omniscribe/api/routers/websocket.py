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
  with five internal dicts: ``manager.active`` (channel_id → live
  :class:`fastapi.WebSocket`), ``manager._tokens`` (channel_id →
  session_token, used for ``is_authorized`` checks),
  ``manager._minted`` (channel_id → session_token as issued by
  ``/api/progress/session``, LRU-capped; the connect-time record that
  lets the handshake reject tokens the server never minted),
  ``manager._cancel_flags`` (channel_id → :class:`asyncio.Event`,
  flipped by :meth:`ConnectionManager.request_cancel` and read by the
  OCR/translate worker via :meth:`ConnectionManager.is_cancelled`), and
  ``manager._accept_loops`` (channel_id → the event loop that accepted
  the socket, so :meth:`ConnectionManager.send` can marshal
  foreign-loop sends back onto it before touching the transport).
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
import contextlib
import hmac
import json
from collections import OrderedDict
from http import HTTPStatus
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from omniscribe.api.routers import state

router = APIRouter()
_progress_service = state.progress_service

# Header used by the frontend ``/api/progress/cancel/{channel_id}`` POST
# to prove ownership of the channel. The token is the same
# ``session_token`` issued by ``/api/progress/session`` and stored in
# :class:`ConnectionManager._tokens`. Using a dedicated header (rather
# than reusing ``Authorization``) keeps the cancel route independent of
# the global bearer-auth policy — the cancel endpoint is always
# session-bound even when the server is open in local dev.
PROGRESS_SESSION_TOKEN_HEADER = "X-Progress-Token"

# Bound on the minted-channel registry. A session that never connects
# keeps its entry until evicted by this LRU cap, so the registry stays
# bounded no matter how many sessions clients mint and abandon.
_MINTED_CHANNEL_CAP = 1024

# How long the server waits for the first-frame auth message after
# accepting a progress socket before closing it with 1008.
_WS_AUTH_TIMEOUT_SECONDS = 10.0

# Per-message inbound cap (bytes). The receive loop reads each frame with
# ``receive_text()`` and closes the socket with WS 1009 (message too big)
# when the UTF-8 byte length exceeds this bound. Without this guard a
# client can stream a multi-GB payload and exhaust server memory before
# the application layer ever sees it. 64 KiB is generous for the JSON
# control frames the UI actually sends (``{"type": "cancel"}`` and the
# initial auth frame) and well below the WS default max-frame-size that
# uvicorn forwards.
MAX_WS_MESSAGE_BYTES: int = 64 * 1024  # 64 KiB; per-message cap
WS_CLOSE_MESSAGE_TOO_BIG: int = 1009


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
        chapters: list[dict[str, Any]] | None = None,
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
        chapters: list[dict[str, Any]] | None = None,
    ) -> None: ...


class ConnectionManager:
    """Tracks token-bound WebSocket progress channels."""

    def __init__(self) -> None:
        self.active: dict[str, WebSocket] = {}
        self._tokens: dict[str, str] = {}
        self._minted: OrderedDict[str, str] = OrderedDict()
        self._cancel_flags: dict[str, asyncio.Event] = {}
        # channel_id -> event loop that accepted the socket. ``send``
        # marshals foreign-loop sends back onto this loop (see below).
        self._accept_loops: dict[str, asyncio.AbstractEventLoop] = {}

    def register_minted(self, channel_id: str, session_token: str) -> None:
        """Record a freshly minted channel/token pair for connect-time checks.

        Without this record the WebSocket handshake would have to trust
        whatever token the connecting client presents — the connection
        itself would establish the binding, so any well-formed token
        would be accepted for any channel.
        """
        self._minted.pop(channel_id, None)
        self._minted[channel_id] = session_token
        while len(self._minted) > _MINTED_CHANNEL_CAP:
            self._minted.popitem(last=False)

    def verify_minted(self, channel_id: str, session_token: str) -> bool:
        """Constant-time compare of the presented token against the minted pair.

        Rejects channels the server never minted (or whose minted entry
        was evicted) and channels that already have a live socket, so a
        second client cannot take over an active channel's stream.
        """
        expected = self._minted.get(channel_id)
        if expected is None or channel_id in self.active:
            return False
        return hmac.compare_digest(expected, session_token)

    def register_channel(
        self, websocket: WebSocket, channel_id: str, session_token: str
    ) -> None:
        """Track an accepted, verified channel socket."""
        self.active[channel_id] = websocket
        self._tokens[channel_id] = session_token
        self._cancel_flags[channel_id] = asyncio.Event()
        self._accept_loops[channel_id] = asyncio.get_running_loop()

    async def connect(
        self, websocket: WebSocket, channel_id: str, session_token: str
    ) -> None:
        channel_id = _progress_service.validate_channel_id(channel_id)
        session_token = _progress_service.validate_session_token(session_token)
        await websocket.accept()
        self.register_channel(websocket, channel_id, session_token)

    def disconnect(self, channel_id: str) -> None:
        self.active.pop(channel_id, None)
        self._tokens.pop(channel_id, None)
        self._cancel_flags.pop(channel_id, None)
        self._accept_loops.pop(channel_id, None)

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
        """Send an NDJSON frame to an active channel. Silently drops on disconnect.

        The wire format is line-delimited JSON (one JSON object + ``\\n``
        per text frame). The trailing newline lets the browser split a
        text frame that happens to contain multiple concatenated objects
        — a real failure mode we've seen on the OmniScribe WebSocket
        when the OCR pipeline fires many progress / block_retry events
        in rapid succession. Even when the underlying transport
        delivers each ASGI ``websocket.send`` as a separate text frame
        (the common case), ``JSON.parse('{"a":1}\\n')`` is still valid
        and the extra byte costs us almost nothing.

        Thread/loop safety: the underlying uvicorn WebSocket (and its
        wsproto state machine) is bound to the event loop that accepted
        it and is **not** safe to write from any other loop. The
        ``/api/process`` worker drives ``pipeline.run`` under
        ``asyncio.run()`` in a thread with its own loop, so block-level
        senders are awaited there while progress frames go out on the
        main loop. When the calling loop differs from the accept loop we
        marshal the actual ``send_text`` back onto the accept loop via
        ``run_coroutine_threadsafe`` and await the wrapped future, which
        preserves the caller's ordering/backpressure semantics. Skipping
        this marshalling interleaved frame bytes from two threads on the
        socket — the browser saw mangled JSON fragments ("pairge") and
        eventually "Invalid frame header".
        """
        if not channel_id:
            return
        ws = self.active.get(channel_id)
        if ws is None:
            return
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
        accept_loop = self._accept_loops.get(channel_id)
        try:
            if accept_loop is None or accept_loop is asyncio.get_running_loop():
                await ws.send_text(text)
                return
            future = asyncio.run_coroutine_threadsafe(ws.send_text(text), accept_loop)
            await asyncio.wrap_future(future)
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
        chapters: list[dict[str, Any]] | None = None,
    ) -> None:
        """Emit the ``chunk_init`` pre-amble for a chunked OCR run."""
        await self.send(
            channel_id,
            _progress_service.build_chunk_init_frame(
                total_chunks=total_chunks, chapters=chapters
            ),
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
        chapters: list[dict[str, Any]] | None = None,
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
                chapters=chapters,
            ),
        )


manager = ConnectionManager()


async def _close_with_code(websocket: WebSocket, code: int) -> None:
    """Best-effort close: a client that raced us with its own disconnect
    makes the close handshake fail, which must not mask the rejection."""
    with contextlib.suppress(Exception):
        await websocket.close(code=code)


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
    manager.register_minted(channel.channel_id, channel.session_token)
    return {
        "channel_id": channel.channel_id,
        "session_token": channel.session_token,
    }


@router.post("/api/progress/cancel/{channel_id}")
async def cancel_channel(
    channel_id: str,
    body: dict | None = None,
    x_progress_token: str | None = Header(
        default=None, alias=PROGRESS_SESSION_TOKEN_HEADER
    ),
):
    """Set the cancel flag for an active channel.

    The request must present the session token that was issued for the
    channel via :func:`create_progress_session` in the
    ``X-Progress-Token`` header. The token is verified by
    :meth:`ConnectionManager.is_authorized` (HMAC compare). Requests with
    a missing, malformed, or non-matching token are rejected with 403;
    the cancel flag is only flipped when the caller proves ownership of
    the channel.
    """
    channel_id = _progress_service.validate_channel_id(channel_id)
    if x_progress_token is None:
        return JSONResponse(
            status_code=HTTPStatus.FORBIDDEN,
            content={"error": f"Missing {PROGRESS_SESSION_TOKEN_HEADER} header."},
        )
    try:
        token = _progress_service.validate_session_token(x_progress_token)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=HTTPStatus.FORBIDDEN,
            content={"error": "Invalid session token."},
        )
    if not manager.is_authorized(channel_id, token):
        return JSONResponse(
            status_code=HTTPStatus.FORBIDDEN,
            content={"error": "Session token does not match channel."},
        )
    manager.request_cancel(channel_id)
    return {"status": "cancel_requested"}


@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    """Accept a token-bound WebSocket connection for real-time progress updates.

    The session token travels in the first inbound frame —
    ``{"type": "auth", "session_token": ...}`` — not in the URL query
    string: query-string secrets end up in server access logs, proxy
    logs, and browser history. The presented token is compared in
    constant time against the pair minted by ``/api/progress/session``;
    channels the server never minted (and channels that already hold a
    live socket) are closed with 1008 before any progress frame is
    emitted.

    After authentication the server reads inbound ``{"type": "cancel"}``
    messages and sets the cancel flag for the channel. The OCR/translate
    worker checks this flag between blocks/chunks and aborts the run
    cleanly.
    """
    try:
        channel_id = _progress_service.validate_channel_id(channel_id)
    except (TypeError, ValueError):
        await _close_with_code(websocket, 1008)
        return
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=_WS_AUTH_TIMEOUT_SECONDS
        )
        msg = json.loads(raw)
        if not isinstance(msg, dict) or msg.get("type") != "auth":
            raise ValueError("first frame must be an auth frame")
        raw_token = msg.get("session_token")
        if not isinstance(raw_token, str):
            raise ValueError("auth frame missing a session_token")
        session_token = _progress_service.validate_session_token(raw_token)
    except Exception:
        # Malformed channel/token, missing or non-auth first frame,
        # disconnect, or auth timeout — close without registering.
        await _close_with_code(websocket, 1008)
        return
    if not manager.verify_minted(channel_id, session_token):
        await _close_with_code(websocket, 1008)
        return
    manager.register_channel(websocket, channel_id, session_token)
    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            # Cap inbound payload size. The control frames the UI sends
            # (``{"type": "cancel"}``) are tens of bytes; anything over
            # 64 KiB is either a misbehaving client or an active DoS
            # attempt — close with WS 1009 before parsing.
            if len(raw.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                await websocket.close(
                    code=WS_CLOSE_MESSAGE_TOO_BIG, reason="message too big"
                )
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if isinstance(msg, dict) and msg.get("type") == "cancel":
                manager.request_cancel(channel_id)
    finally:
        manager.disconnect(channel_id)
