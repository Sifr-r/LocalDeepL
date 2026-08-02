import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlparse


def _local_ssrf_allowed() -> bool:
    return os.getenv("ALLOW_SSRF_LOCAL", "").strip().lower() == "true"


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast)


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


async def is_ssrf_target(url: str | None) -> bool:
    """
    Validates if a URL host corresponds to a private, loopback, or internal IP address.
    Supports dynamic DNS resolution to prevent DNS rebinding attacks.

    Returns True for malformed URLs, unsupported schemes, and DNS resolution
    failures so caller-supplied endpoints fail closed.
    """
    if not url:
        return True

    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return True
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return True

        allow_local = _local_ssrf_allowed()

        # Block cloud metadata endpoints regardless of local-development mode.
        if host == "metadata.google.internal":
            return True

        if host == "localhost" or host.endswith(".local"):
            return not allow_local

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None

        if ip is not None:
            return not allow_local if _is_blocked_ip(ip) else False

        resolved = await _resolve_host(host)
        if not resolved:
            return True

        for address, _port in resolved:
            resolved_ip = ipaddress.ip_address(address)
            if _is_blocked_ip(resolved_ip):
                return not allow_local

        return False
    except Exception:
        return True
