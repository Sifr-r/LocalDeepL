"""SSRF fail-closed guard safety tests.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

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


async def test_ssrf_fails_closed_and_requires_explicit_local_allowance():
    # Sprint 4 / M-6 audit fix: convert ``asyncio.run`` calls inside the
    # SSRF safety test to ``await`` so the test runs on the same loop
    # as the rest of the suite. Auto mode (set in pyproject.toml) drives
    # the coroutine without an explicit decorator.
    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = _public_dns
            public = await is_ssrf_target("http://api.openai.com/v1")
            assert public.allowed is True
            assert public.resolved_ip == "104.18.3.161"
            assert (await is_ssrf_target("localhost:1234/v1")).allowed is False
            assert (await is_ssrf_target("ftp://api.openai.com/v1")).allowed is False
            assert (await is_ssrf_target(None)).allowed is False

    with patch.dict(os.environ, {}, clear=True):
        with patch("omniscribe.utils.security.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.side_effect = socket.gaierror(-2, "Name or service not known")
            assert (
                await is_ssrf_target("http://does-not-resolve.example/v1")
            ).allowed is False

    with patch.dict(os.environ, {"ALLOW_SSRF_LOCAL": "true"}, clear=True):
        loopback = await is_ssrf_target("http://127.0.0.1:1234/v1")
        assert loopback.allowed is True
        assert loopback.resolved_ip == "127.0.0.1"
        assert (
            await is_ssrf_target("http://metadata.google.internal/v1")
        ).allowed is False


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


# ---------------------------------------------------------------------------
# Pedantic 1.18: module-level SSRF executor singleton
# ---------------------------------------------------------------------------


def test_check_ssrf_target_sync_uses_module_level_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``check_ssrf_target_sync`` must reuse a module-level executor
    instead of allocating a fresh ``ThreadPoolExecutor`` per call.

    The previous code's ``with ThreadPoolExecutor(max_workers=1)``
    block paid a thread-pool + worker + future setup/teardown on every
    SSRF check; on the OCR request hot path this was both wasteful and
    noisy in thread-dump output. The fix hoists a single executor to
    module scope.

    The check: count ``ThreadPoolExecutor.__init__`` invocations while
    issuing several ``check_ssrf_target_sync`` calls; the count must
    be zero (the executor was created at module import, not on demand).
    """
    from concurrent.futures import ThreadPoolExecutor

    import omniscribe.utils.security as security

    init_calls: list[tuple] = []

    real_init = ThreadPoolExecutor.__init__

    def counting_init(self, *args, **kwargs):
        init_calls.append((args, kwargs))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(ThreadPoolExecutor, "__init__", counting_init)

    # Stub ``is_ssrf_target`` so we don't need a real DNS lookup. The
    # sync wrapper still routes through the executor.
    async def _fake_ssrf(_url):
        from omniscribe.utils.security import SSRFCheckResult

        return SSRFCheckResult(True, "93.184.216.34")

    monkeypatch.setattr(security, "is_ssrf_target", _fake_ssrf)

    # The executor is reused across calls: zero new ThreadPoolExecutor
    # instantiations per call, regardless of the loop state.
    for _ in range(5):
        result = security.check_ssrf_target_sync("http://example.com")
        assert result.allowed is True
        assert result.resolved_ip == "93.184.216.34"

    assert init_calls == [], (
        f"check_ssrf_target_sync allocated {len(init_calls)} new "
        f"ThreadPoolExecutor(s); expected to reuse the module-level one"
    )

    # The module-level executor is still the one in use, and it is the
    # same object a fresh import would expose.
    assert isinstance(security._SSRF_EXECUTOR, ThreadPoolExecutor)
    assert security._SSRF_EXECUTOR._max_workers >= 1
