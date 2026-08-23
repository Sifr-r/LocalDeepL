"""Per-IP token bucket rate-limiting middleware for ASGI.

Maintains a 60s sliding window per client IP with bounded memory footprint
and amortized cleanup sweeps.
"""

from __future__ import annotations

import ipaddress
import json
import sys
import time
from collections import OrderedDict, deque
from typing import Any, Final

_TOO_MANY_REQUESTS: Final[dict[str, str]] = {"error": "Rate limit exceeded"}

#: Minimum interval between rate-limit memory sweeps. D2-04 audit
#: fix: the previous code ran the full O(N) sweep on the request
#: that triggered the overflow, so request 10,001 of a 10,000-IP
#: flood took the full sweep latency. The sweep is now amortized:
#: at most one full sweep per ``_SWEEP_INTERVAL_S`` seconds, and
#: only the request that crosses the cap pays for it. The 5 s
#: default matches the WebSocket keepalive cadence.
_SWEEP_INTERVAL_S: float = 5.0


def _get_sweep_interval() -> float:
    """Return the effective sweep interval, checking legacy compatibility shim."""
    sm = sys.modules.get("omniscribe.api.services.security_middleware")
    if (
        sm is not None
        and hasattr(sm, "_SWEEP_INTERVAL_S")
        and sm._SWEEP_INTERVAL_S != 5.0
    ):
        return float(sm._SWEEP_INTERVAL_S)
    return _SWEEP_INTERVAL_S


async def _send_json(
    scope: dict[str, Any], receive: Any, send: Any, payload: dict[str, str], status: int
) -> None:
    """Send a small JSON error response via raw ASGI (no FastAPI import)."""
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class RateLimitMiddleware:
    """Per-IP fixed-window rate limiter; in-memory and process-local.

    Each request from a given client IP appends a timestamp to a deque;
    before forwarding the request we evict entries older than 60s and
    reject if the deque is at capacity. Suitable for soft abuse
    protection on a single-worker server; not a substitute for a proper
    edge gateway.

    When ``trusted_proxies`` is non-empty, the limiter consults the
    ``X-Forwarded-For`` header on requests whose ASGI peer is inside
    one of the configured CIDR ranges. Requests from untrusted peers
    never see the header (the standard "do not trust client-supplied
    headers from an untrusted source" rule).
    """

    WINDOW_SECONDS: Final[float] = 60.0
    MAX_TRACKED_IPS: Final[int] = 10_000
    _XFF_HEADER: Final[bytes] = b"x-forwarded-for"

    def __init__(
        self,
        app: Any,
        per_minute: int,
        clock: Any = time.monotonic,
        trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
        | None = None,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        # D2-04 audit fix: amortize the O(N) sweep across many
        # requests. ``_last_sweep`` is the ``clock()`` value at the
        # last full sweep; subsequent overflow triggers within
        # ``_SWEEP_INTERVAL_S`` skip the sweep and only the first
        # request that crosses the interval pays the cost. A
        # rotating-IP attacker can no longer pin p99 at the sweep
        # latency.
        self._last_sweep: float = 0.0
        self._trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = (
            list(trusted_proxies) if trusted_proxies else []
        )

    def _extract_xff(self, scope: dict[str, Any]) -> str | None:
        """Return the rightmost *untrusted* ``X-Forwarded-For`` entry, or ``None``.

        ``X-Forwarded-For`` is a comma-separated chain where each proxy
        appends the IP it received the connection from. The rightmost
        entry is the most-recently appended (added by the proxy we just
        received the request from); the leftmost is the original client.

        An attacker controls the leftmost end of the chain — they can put
        anything they want there. The standard "right-to-left trust"
        pattern walks the chain from the right and skips entries that
        fall inside the configured trusted-proxy CIDR list. The first
        entry that is NOT in that list is the real client IP. If every
        entry is trusted (or the chain is empty / unparseable) we return
        ``None`` so the caller falls back to the ASGI peer — never
        forwarding the raw header value into the bucket key.
        """
        for name, value in scope.get("headers", ()) or ():
            if name.lower() == self._XFF_HEADER:
                try:
                    raw = value.decode("latin-1").strip()
                except (UnicodeDecodeError, AttributeError):
                    return None
                if not raw:
                    return None
                parts: list[str] = raw.split(",")
                entries: list[str] = [item.strip() for item in parts if item.strip()]
                if not entries:
                    return None
                for entry in reversed(entries):
                    try:
                        ip = ipaddress.ip_address(entry)
                    except ValueError:
                        # A malformed token anywhere in the chain means
                        # the chain is untrustworthy; fall back to the
                        # peer rather than guessing.
                        return None
                    if not any(ip in network for network in self._trusted_proxies):
                        return entry
                # Every entry in the chain is a trusted hop — there is
                # no original client in the header. Fall back to the
                # ASGI peer.
                return None
        return None

    def _client_key(self, scope: dict[str, Any]) -> str:
        client = scope.get("client")
        if client is None:
            return "unknown"
        peer_ip = str(client[0])
        if not self._trusted_proxies:
            return peer_ip
        try:
            peer = ipaddress.ip_address(peer_ip)
        except ValueError:
            return peer_ip
        if not any(peer in network for network in self._trusted_proxies):
            return peer_ip
        candidate = self._extract_xff(scope)
        if candidate is None:
            return peer_ip
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return peer_ip
        return candidate

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        # F2.4 audit fix: the per-IP bucket used to short-circuit on
        # ``scope["type"] != "http"`` so WebSocket upgrade floods were
        # bounded only by the 10 s ``verify_minted`` auth-frame
        # timeout. The ASGI peer is the same for the HTTP upgrade
        # request and the upgraded WebSocket, so we can apply the
        # bucket to the upgrade itself and let the inner app accept
        # frames freely. Lifespan (``scope["type"] == "lifespan"``)
        # and unknown types still pass through — the bucket is keyed
        # to per-client network identity, not server housekeeping.
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        key = self._client_key(scope)
        if key in self._hits:
            self._hits.move_to_end(key, last=True)
        now = self.clock()
        cutoff = now - self.WINDOW_SECONDS
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.per_minute:
            await _send_json(scope, receive, send, _TOO_MANY_REQUESTS, 429)
            return
        hits.append(now)

        # Bounded memory footprint: If len(self._hits) > MAX_TRACKED_IPS,
        # sweep empty or stale entries, then pop LRU items from OrderedDict start.
        # D2-04 audit fix: the sweep is amortized — at most one full
        # pass per ``_SWEEP_INTERVAL_S`` seconds. The first overflow
        # trigger within the window pays the cost; later triggers
        # skip the sweep and trust the next window to clean up.
        sweep_interval = _get_sweep_interval()
        if (
            len(self._hits) > self.MAX_TRACKED_IPS
            and now - self._last_sweep >= sweep_interval
        ):
            self._last_sweep = now
            stale_keys = [
                k
                for k, v in self._hits.items()
                if (not v or v[-1] < cutoff) and k != key
            ]
            for sk in stale_keys:
                self._hits.pop(sk, None)
            while len(self._hits) > self.MAX_TRACKED_IPS:
                first_k = next(iter(self._hits))
                if first_k == key:
                    break
                self._hits.popitem(last=False)

        await self.app(scope, receive, send)


__all__ = [
    "_SWEEP_INTERVAL_S",
    "_TOO_MANY_REQUESTS",
    "RateLimitMiddleware",
    "_send_json",
]
