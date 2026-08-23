"""SSRF fail-closed guard safety tests.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio
import os
import socket
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from omniscribe.utils.security import is_blocked_host, is_ssrf_target


def _public_dns(host: str, port, *args, **kwargs):
    """Stub ``socket.getaddrinfo``: only ``api.openai.com`` resolves."""
    if host == "api.openai.com":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.3.161", 443))]
    raise socket.gaierror(-2, "Name or service not known")


def test_ssrf_fails_closed_and_requires_explicit_local_allowance():
    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = _public_dns
            assert (
                asyncio.run(is_ssrf_target("http://api.openai.com/v1")).allowed is True
            )
            assert (
                asyncio.run(is_ssrf_target("http://api.openai.com/v1")).resolved_ip
                == "104.18.3.161"
            )
            assert asyncio.run(is_ssrf_target("localhost:1234/v1")).allowed is False
            assert (
                asyncio.run(is_ssrf_target("ftp://api.openai.com/v1")).allowed is False
            )
            assert asyncio.run(is_ssrf_target(None)).allowed is False

    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = socket.gaierror(-2, "Name or service not known")
            assert (
                asyncio.run(
                    is_ssrf_target("http://does-not-resolve.example/v1")
                ).allowed
                is False
            )

    with patch.dict(os.environ, {"ALLOW_SSRF_LOCAL": "true"}, clear=True):
        assert asyncio.run(is_ssrf_target("http://127.0.0.1:1234/v1")).allowed is True
        assert (
            asyncio.run(is_ssrf_target("http://127.0.0.1:1234/v1")).resolved_ip
            == "127.0.0.1"
        )
        assert (
            asyncio.run(is_ssrf_target("http://metadata.google.internal/v1")).allowed
            is False
        )


# ---------------------------------------------------------------------------
# Merged from test_phase2_cloud_metadata_blocked.py (audit-secondary F26)
# ---------------------------------------------------------------------------


async def test_cloud_metadata_unconditionally_blocked(monkeypatch):
    """Verify 169.254.169.254 is rejected even if ALLOW_SSRF_LOCAL is true.

    The original fix: the SSRF guard used to allow the cloud metadata
    endpoint (``169.254.169.254``) when ``ALLOW_SSRF_LOCAL=true``. The
    fix makes the cloud-metadata block unconditional — it is a
    credential-leak vector on every major cloud, and the local-dev
    default should not relax it.
    """
    monkeypatch.setenv("ALLOW_SSRF_LOCAL", "true")

    res = await is_ssrf_target("http://169.254.169.254/latest/meta-data/")
    assert not res.allowed
    assert res.reason == "metadata-endpoint"

    assert is_blocked_host("169.254.169.254")
    assert is_blocked_host("metadata.google.internal")
