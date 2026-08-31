"""SSRF-guarded URL fetch for glossary imports.

Adapted from the deleted `api/services/http_fetch.py` (`44ef123^`): the
URL and every redirect hop are validated against `is_ssrf_target`, the
TCP connection is pinned to the resolved IP (DNS-rebinding defense), and
redirects are followed manually up to ``_MAX_REDIRECTS``. Fetch failures
map to 502 `ai_error` (spec §8.3) and SSRF denials to 403 `ssrf_blocked`
via `GlossaryError`.
"""

from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urljoin

import httpx

from omniscribe.plugins.glossary.service import GlossaryError
from omniscribe.utils.security import is_ssrf_target

_MAX_REDIRECTS = 5
MAX_GLOSSARY_BYTES: int = 50 * 1024 * 1024


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """httpx transport pinning connections to the SSRF-resolved IP.

    The scoped ``getaddrinfo`` swap only maps the target host to its
    validated IP for the duration of one request; other coroutines
    resolving different hosts are unaffected, and same-host resolution
    during the window returns the same validated IP.
    """

    def __init__(self, resolved_ip: str) -> None:
        super().__init__()
        self._resolved_ip = resolved_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.extensions["server_hostname"] = request.url.host
        original_getaddrinfo = socket.getaddrinfo

        def _pinned_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            if host == request.url.host:
                return original_getaddrinfo(self._resolved_ip, *args, **kwargs)
            return original_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = _pinned_getaddrinfo
        try:
            return await super().handle_async_request(request)
        finally:
            socket.getaddrinfo = original_getaddrinfo


async def fetch_url_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch a URL's body as bytes with SSRF protection on every hop."""
    current_url = url

    for _ in range(_MAX_REDIRECTS + 1):
        check = await is_ssrf_target(current_url)
        if not check.allowed:
            raise GlossaryError(
                403,
                "ssrf_blocked",
                f"URL targets a blocked address: {check.reason or 'blocked'}",
            )
        if check.resolved_ip is None:
            raise GlossaryError(403, "ssrf_blocked", "URL resolved to no address.")

        transport = _PinnedIPTransport(resolved_ip=check.resolved_ip)
        client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
        )
        try:
            response = await client.get(current_url)
        finally:
            await client.aclose()

        if response.is_redirect:
            location = response.headers.get("Location")
            if not location:
                break
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content = response.content
        if len(content) > MAX_GLOSSARY_BYTES:
            raise GlossaryError(
                400, "bad_request", f"URL body exceeds {MAX_GLOSSARY_BYTES} bytes."
            )
        return content

    raise GlossaryError(
        502, "ai_error", f"Exceeded {_MAX_REDIRECTS} redirects for {url}"
    )
