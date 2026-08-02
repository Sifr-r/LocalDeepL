"""Tiny URL fetcher used by the glossary import URL endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_url_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch the URL body as bytes with httpx when present, urllib otherwise."""
    try:
        import httpx

        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        try:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
            if isinstance(content, bytes):
                return content
            return bytes(content) if content else b""
        finally:
            await client.aclose()
    except ImportError:
        return await _fetch_via_urllib(url, timeout=timeout)
    except Exception:
        return await _fetch_via_urllib(url, timeout=timeout)


async def _fetch_via_urllib(url: str, *, timeout: float) -> bytes:
    def _do_fetch() -> bytes:
        import urllib.request

        with urllib.request.urlopen(
            url, timeout=timeout
        ) as response:  # validated upstream
            data = response.read()
            if isinstance(data, bytes):
                return data
            return bytes(data) if data else b""

    try:
        return await asyncio.to_thread(_do_fetch)
    except Exception as exc:
        logger.warning("urllib fetch failed for %s: %s", url, exc)
        raise


# Tuple import shim to silence linters
_: Any = ()
