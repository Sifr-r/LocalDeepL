"""WebSocket frame diagnostic for OmniScribe.

Captures the raw bytes the server sends on a progress channel so
we can tell whether the byte-level corruption seen in the browser
console ("Invalid frame header", mangled payloads like
"pairge" where the real text is "progress") is happening:

  (a) on the server side — uvicorn/websockets is producing bad
      bytes on the wire; OR
  (b) on the browser side — Chrome is mangling frames that the
      server sent correctly.

Run this against a live server while you trigger an OCR job:

    uv run python scripts/debug_websocket_frames.py --seconds 60

It opens a real WebSocket, prints every text frame it receives as
hex + UTF-8, and writes the same to a log file for offline
inspection. If the raw bytes match the JSON we expect, the
problem is on the browser side. If the bytes are already mangled
when they leave the server, the problem is uvicorn/websockets.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import websockets


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="milliseconds")


async def _open_session(base_url: str) -> tuple[str, str]:
    """Create a progress session and return (channel_id, token)."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post("/api/progress/session", json={})
        resp.raise_for_status()
        data = resp.json()
        return data["channel_id"], data["session_token"]


async def _capture(
    channel_id: str, token: str, base_url: str, seconds: float, log_path: Path
) -> None:
    ws_url = f"{base_url.replace('http', 'ws', 1)}/ws/{channel_id}"
    print(f"[{_now_iso()}] connecting to {ws_url}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"# WebSocket capture started at {_now_iso()}\n")
        log.write(f"# channel_id={channel_id}\n")
        log.write(f"# ws_url={ws_url}\n\n")
        log.flush()
        try:
            async with websockets.connect(ws_url) as ws:
                # The token travels in the first frame, not the URL.
                await ws.send(json.dumps({"type": "auth", "session_token": token}))
                print(f"[{_now_iso()}] connected", flush=True)
                deadline = asyncio.get_event_loop().time() + seconds
                frame_index = 0
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        print(f"[{_now_iso()}] capture window closed", flush=True)
                        return
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except TimeoutError:
                        print(
                            f"[{_now_iso()}] no frames in remaining window", flush=True
                        )
                        return
                    frame_index += 1
                    timestamp = _now_iso()
                    if isinstance(raw, bytes):
                        preview = raw[:200].hex()
                        kind = "BIN"
                        decoded: str | None = None
                        with contextlib.suppress(UnicodeDecodeError):
                            decoded = raw.decode("utf-8", errors="replace")
                        payload = decoded if decoded is not None else preview
                    else:
                        kind = "TXT"
                        payload = raw
                    # Validate as JSON if possible; report any parse error.
                    parsed: Any = None
                    parse_err: str | None = None
                    try:
                        parsed = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        parse_err = (
                            f"JSONDecodeError at line {exc.lineno} "
                            f"col {exc.colno}: {exc.msg}"
                        )
                    entry = {
                        "ts": timestamp,
                        "i": frame_index,
                        "kind": kind,
                        "len": len(raw),
                        "payload": payload,
                        "hex_first_200": (
                            raw.encode("utf-8").hex()[:200]
                            if isinstance(raw, str)
                            else raw.hex()[:200]
                        ),
                        "parse_ok": parsed is not None,
                        "parse_err": parse_err,
                    }
                    print(
                        f"[{timestamp}] frame #{frame_index} ({kind}, {len(raw)}B) "
                        f"parse_ok={entry['parse_ok']}",
                        flush=True,
                    )
                    if parse_err:
                        print(f"    parse_err: {parse_err}", flush=True)
                        print(f"    payload:   {payload!r}", flush=True)
                    elif isinstance(parsed, dict):
                        keys = sorted(parsed.keys())
                        print(f"    keys:      {keys}", flush=True)
                    log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    log.flush()
        except websockets.exceptions.ConnectionClosed as exc:
            print(f"[{_now_iso()}] connection closed: {exc}", flush=True)
            log.write(f"# connection closed at {_now_iso()}: {exc}\n")
        except Exception as exc:
            print(f"[{_now_iso()}] error: {type(exc).__name__}: {exc}", flush=True)
            log.write(f"# error at {_now_iso()}: {type(exc).__name__}: {exc}\n")


async def _main(args: argparse.Namespace) -> int:
    log_path = Path(args.log).resolve()
    try:
        channel_id, token = await _open_session(args.base_url)
    except Exception as exc:
        print(f"failed to open progress session: {exc}", file=sys.stderr)
        return 2
    print(f"channel_id={channel_id}")
    print(f"log file:  {log_path}")
    print()
    print(
        f"Trigger an OCR job from the UI within {args.seconds:.0f}s to generate frames."
    )
    await _capture(channel_id, token, args.base_url, args.seconds, log_path)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="OmniScribe HTTP base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=120.0,
        help="How long to listen for frames (default: 120s).",
    )
    parser.add_argument(
        "--log",
        default="ws_capture.jsonl",
        help="Where to write the frame log (default: ws_capture.jsonl).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(_parse_args())))
