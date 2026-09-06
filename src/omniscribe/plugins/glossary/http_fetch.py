"""SSRF-guarded URL fetch for glossary imports.

Adapted from the deleted `api/services/http_fetch.py` (`44ef123^`): the
URL and every redirect hop are validated against `is_ssrf_target`, the
TCP connection is pinned to the resolved IP (DNS-rebinding defense), and
redirects are followed manually up to ``_MAX_REDIRECTS``. Fetch failures
map to 502 `ai_error` (spec §8.3) and SSRF denials to 403 `ssrf_blocked`
via `GlossaryError`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

from omniscribe.plugins.glossary.service import GlossaryError
from omniscribe.utils.security import is_ssrf_target

_MAX_REDIRECTS = 5
MAX_GLOSSARY_BYTES: int = 50 * 1024 * 1024


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Network backend that redirects TCP connections for a specific host to a pinned IP."""

    def __init__(self, target_host: str, resolved_ip: str) -> None:
        self._target_host = target_host
        self._resolved_ip = resolved_ip
        self._backend: httpcore.AsyncNetworkBackend = AutoBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        target = self._resolved_ip if host == self._target_host else host
        return await self._backend.connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """httpx transport pinning connections to the SSRF-resolved IP without global socket mutation."""

    def __init__(self, target_host: str, resolved_ip: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        backend = _PinnedNetworkBackend(target_host, resolved_ip)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._pool._ssl_context,
            network_backend=backend,
            http2=self._pool._http2,
            retries=self._pool._retries,
        )


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

        parsed_target = urlparse(current_url)
        target_host = parsed_target.hostname or ""
        transport = _PinnedIPTransport(
            target_host=target_host, resolved_ip=check.resolved_ip
        )
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
                raise GlossaryError(
                    502,
                    "ai_error",
                    f"Redirect response missing Location header for {current_url}",
                )
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
