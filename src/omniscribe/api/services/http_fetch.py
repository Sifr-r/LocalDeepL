"""Tiny URL fetcher used by the glossary import URL endpoint.

Security contract
-----------------
The URL is validated against :func:`omniscribe.utils.security.is_ssrf_target`
on entry *and* on every 3xx ``Location`` hop. A 301/302 that points at
``http://169.254.169.254/`` or ``file:///etc/passwd`` is rejected before
the connection is opened.

The TCP connection is pinned to the IP the SSRF guard resolved. A DNS
rebinding attack that flips the record between validation and connect
cannot redirect the request to an attacker-controlled address because
the transport never re-resolves the hostname.

Only ``httpx`` is used. The previous ``urllib`` fallback was removed
because :func:`urllib.request.urlopen` follows redirects natively and
accepts ``file://`` schemes — both of which silently re-introduce the
SSRF surface this module is meant to close.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from omniscribe.utils.security import is_ssrf_target

logger = logging.getLogger(__name__)


_MAX_REDIRECTS = 5
MAX_GLOSSARY_BYTES: int = 50 * 1024 * 1024


class SSRFBlockedError(Exception):
    """Raised when a URL (initial or redirect target) fails SSRF validation."""

    def __init__(self, url: str, reason: str | None) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"SSRF-blocked URL {url!r}: {reason}")


class _PinnedIPTransport(httpx.AsyncBaseTransport):
    """HTTPX transport that pins the TCP connection to a pre-validated IP.

    Bypasses the DNS resolution that ``httpx.AsyncHTTPTransport`` would
    perform on connect — the transport opens the socket straight to
    ``resolved_ip``. For HTTPS, the URL's hostname is passed as
    ``server_hostname`` so the TLS handshake still does SNI and
    certificate verification against the original hostname (i.e. an
    attacker who rebinds the hostname to an internal IP between check
    and connect still fails cert verification).
    """

    def __init__(self, *, resolved_ip: str, timeout: float) -> None:
        self._resolved_ip = resolved_ip
        self._timeout = timeout

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        parsed = urlparse(url_str)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        ssl_context: ssl.SSLContext | None = None
        server_hostname: str | None = None
        if parsed.scheme == "https":
            ssl_context = ssl.create_default_context()
            server_hostname = hostname

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=self._resolved_ip,
                    port=port,
                    ssl=ssl_context,
                    server_hostname=server_hostname,
                ),
                timeout=self._timeout,
            )
        except (TimeoutError, OSError) as exc:
            raise httpx.ConnectError(
                f"Failed to connect to {self._resolved_ip}:{port}: {exc}",
                request=request,
            ) from exc

        try:
            request_lines = [f"{request.method} {path} HTTP/1.1"]
            request_headers = dict(request.headers)
            request_headers["Host"] = hostname or self._resolved_ip
            request_headers.setdefault("Accept", "*/*")
            request_headers.setdefault("User-Agent", "omniscribe-http_fetch/1.0")
            request_headers.setdefault("Connection", "close")
            for name, value in request_headers.items():
                request_lines.append(f"{name}: {value}")
            request_lines.append("")
            request_lines.append("")

            payload = "\r\n".join(request_lines).encode("latin-1", errors="replace")
            if request.content:
                payload += request.content

            writer.write(payload)
            await writer.drain()

            chunks: list[bytes] = []
            total_bytes = 0
            while True:
                chunk = await asyncio.wait_for(
                    reader.read(64 * 1024),
                    timeout=self._timeout,
                )
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_GLOSSARY_BYTES:
                    raise httpx.RequestError(
                        f"Response body exceeds maximum allowed size of {MAX_GLOSSARY_BYTES} bytes",
                        request=request,
                    )
                chunks.append(chunk)
            response_data = b"".join(chunks)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass

        return self._parse_response(response_data, request)

    @staticmethod
    def _parse_response(data: bytes, request: httpx.Request) -> httpx.Response:
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            raise httpx.RemoteProtocolError(
                "Invalid HTTP response (no header terminator)", request=request
            )

        header_block = data[:header_end]
        body = data[header_end + 4 :]

        header_lines = header_block.split(b"\r\n")
        if not header_lines:
            raise httpx.RemoteProtocolError("Empty status line", request=request)

        status_line = header_lines[0]
        parts = status_line.split(b" ", 2)
        if len(parts) < 2:
            raise httpx.RemoteProtocolError(
                f"Malformed status line: {status_line!r}", request=request
            )
        try:
            status_code = int(parts[1])
        except ValueError as exc:
            raise httpx.RemoteProtocolError(
                f"Non-numeric status code: {parts[1]!r}", request=request
            ) from exc
        reason_phrase = parts[2] if len(parts) >= 3 else b""

        headers_dict: dict[str, str] = {}
        for line in header_lines[1:]:
            if b":" in line:
                name, _, value = line.partition(b":")
                headers_dict[name.decode("latin-1").strip()] = value.decode(
                    "latin-1"
                ).strip()

        return httpx.Response(
            status_code=status_code,
            headers=headers_dict,
            content=body,
            request=request,
            extensions={"reason_phrase": reason_phrase},
        )


async def fetch_url_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch a URL's body as bytes with SSRF protection on every hop.

    The URL and every 3xx ``Location`` header are validated against
    :func:`is_ssrf_target` before the request is opened. The TCP
    connection is pinned to the IP the guard resolved for the current
    hop, neutralising DNS-rebinding TOCTOU. Up to ``_MAX_REDIRECTS``
    redirect hops are followed; anything more raises
    :class:`httpx.TooManyRedirects`.
    """
    current_url = url

    for _ in range(_MAX_REDIRECTS + 1):
        check = await is_ssrf_target(current_url)
        if not check.allowed:
            raise SSRFBlockedError(current_url, check.reason)
        if check.resolved_ip is None:
            # Sanity guard: allowed=True must always carry a resolved IP.
            raise SSRFBlockedError(current_url, "missing-resolved-ip")

        transport = _PinnedIPTransport(resolved_ip=check.resolved_ip, timeout=timeout)
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
                # 3xx with no Location — treat as final response
                break
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content = response.content
        if isinstance(content, bytes):
            return content
        return bytes(content) if content else b""

    raise httpx.TooManyRedirects(f"Exceeded {_MAX_REDIRECTS} redirects for {url}")


# Tuple import shim to silence linters
_: Any = ()
