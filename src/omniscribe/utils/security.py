"""URL/host security primitives: SSRF guard with DNS-pinning support.

Public API
----------
- :class:`SSRFCheckResult` — structured outcome of an SSRF check, including
  the IP that was validated so callers can pin the TCP connection to it
  (TOCTOU defense).
- :func:`is_ssrf_target` — async guard that validates a URL and returns
  the result.

The contract is "fail closed": malformed URLs, unsupported schemes, and
DNS resolution failures return ``SSRFCheckResult(allowed=False, ...)`` so
caller-supplied endpoints cannot slip through. The :attr:`resolved_ip`
slot is populated whenever ``allowed`` is True so the caller can hand
the same IP to the HTTP transport and bypass DNS re-resolution.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


def _local_ssrf_allowed() -> bool:
    return os.getenv("ALLOW_SSRF_LOCAL", "").strip().lower() == "true"


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast)


@dataclass(frozen=True)
class SSRFCheckResult:
    """Structured outcome of :func:`is_ssrf_target`.

    ``allowed`` is True only when the URL is safe to fetch AND a concrete
    ``resolved_ip`` is available for the caller to pin the TCP connection
    to. For URL-as-literal-IP inputs, ``resolved_ip`` is the literal IP.
    For DNS-resolved hosts, it's the first resolved address (a transport
    that pins this IP neutralises the DNS-rebinding TOCTOU window that
    exists when the HTTP client re-resolves the hostname on connect).

    ``reason`` is a short, stable tag describing the failure mode when
    ``allowed`` is False (used for logging / metrics). It is ``None`` for
    successful checks.
    """

    allowed: bool
    resolved_ip: str | None
    reason: str | None = None


async def _resolve_host(host: str) -> list[tuple[str, int]]:
    """Resolve ``host`` off the event loop to avoid blocking it.

    Returns a list of resolved ``(address, port)`` pairs (port unused), or
    an empty list on failure.
    """
    try:
        addr_info = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except (socket.gaierror, Exception):
        return []
    resolved: list[tuple[str, int]] = []
    for _family, _st, _p, _cn, sockaddr in addr_info:
        # IPv4 sockaddr is 2-tuple (str, int); IPv6 is 4-tuple (str, int, int, int)
        # (or the legacy 4-tuple (bytes, int, int, int) on some platforms).
        # We only use the address slot, so normalise both shapes to (str, int).
        raw_address = sockaddr[0]
        port = int(sockaddr[1])
        address: str
        if isinstance(raw_address, bytes):
            address = raw_address.decode("utf-8", errors="replace")
        else:
            # mypy's getaddrinfo stub types sockaddr[0] as `str | int`; in
            # practice it's always str at this point, so cast to lock that in.
            address = str(raw_address)
        resolved.append((address, port))
    return resolved


async def is_ssrf_target(url: str | None) -> SSRFCheckResult:
    """Validate a URL against the SSRF blocklist and return the validated IP.

    Returns an :class:`SSRFCheckResult` whose :attr:`allowed` is True only
    when the URL passes every check AND a concrete IP is available. The
    :attr:`resolved_ip` slot is the IP the caller should pin the TCP
    connection to (TOCTOU defense). For invalid / blocked / unresolved
    inputs, ``allowed`` is False and ``resolved_ip`` is None.
    """
    if not url:
        return SSRFCheckResult(False, None, "empty-url")

    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return SSRFCheckResult(False, None, "unsupported-scheme")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return SSRFCheckResult(False, None, "empty-host")

        allow_local = _local_ssrf_allowed()

        # Block cloud metadata endpoints regardless of local-development mode.
        if host == "metadata.google.internal":
            return SSRFCheckResult(False, None, "metadata-endpoint")

        # Literal IP in the URL — no DNS involved, so TOCTOU is moot.
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None

        if ip is not None:
            if _is_blocked_ip(ip):
                if not allow_local:
                    return SSRFCheckResult(False, None, "literal-blocked-ip")
                return SSRFCheckResult(True, str(ip), "literal-blocked-but-allowed")
            return SSRFCheckResult(True, str(ip))

        if (host == "localhost" or host.endswith(".local")) and not allow_local:
            return SSRFCheckResult(False, None, "localhost-blocked")
        # Fall through to DNS resolution when allow_local is True —
        # the transport still needs an IP to pin, and 127.0.0.1 / ::1
        # is what getaddrinfo returns.

        resolved = await _resolve_host(host)
        if not resolved:
            return SSRFCheckResult(False, None, "dns-resolution-failed")

        # If ANY resolved IP is blocked, the URL is blocked (unless the
        # caller opted in to local addresses). The pinned IP for the
        # transport is the first resolved address — same one httpx
        # would have used, so HTTPS SNI / cert verification still matches.
        for address, _port in resolved:
            try:
                resolved_ip = ipaddress.ip_address(address)
            except ValueError:
                return SSRFCheckResult(False, None, "invalid-resolved-ip")
            if _is_blocked_ip(resolved_ip):
                if not allow_local:
                    return SSRFCheckResult(False, None, "resolved-blocked-ip")
                return SSRFCheckResult(
                    True, str(resolved_ip), "resolved-blocked-but-allowed"
                )

        return SSRFCheckResult(True, resolved[0][0])
    except Exception as exc:
        return SSRFCheckResult(False, None, f"unexpected-error: {exc}")
