"""Regression test for C-1 audit fix: bind-host + auth-token startup guard.

The audit found that the rebuilt route surface is unauthenticated. Running
the server bound to a non-loopback host with no ``OMNISCRIBE_AUTH_TOKEN``
is unsafe — every ``/api/*`` route is reachable by any caller. The guard
refuses to start in that configuration.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest


@contextmanager
def _patched_uvicorn():
    class _FakeUvicorn:
        @staticmethod
        def run(*args, **kwargs):  # pragma: no cover - smoke
            return None

    with (
        patch(
            "omniscribe.server._load_optional_module",
            return_value=_FakeUvicorn,
        ),
        patch("omniscribe.server.app._load", return_value=None),
    ):
        yield


def test_C1_main_refuses_non_loopback_bind_without_auth(monkeypatch) -> None:
    """Binding to 0.0.0.0 with no auth token must raise SystemExit."""
    from omniscribe.server import main

    for var in ("OMNISCRIBE_AUTH_TOKEN", "OMNISCRIBE_OCR_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    with _patched_uvicorn():
        with pytest.raises(SystemExit, match=r"(?i)auth"):
            main(["--host", "0.0.0.0", "--port", "8001"])


def test_C1_main_allows_loopback_bind_without_auth(monkeypatch) -> None:
    """Binding to 127.0.0.1 without auth is the documented local-trusted mode."""
    from omniscribe.server import main

    for var in ("OMNISCRIBE_AUTH_TOKEN", "OMNISCRIBE_OCR_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    with _patched_uvicorn():
        # Should not raise SystemExit; will call uvicorn.run which our fake no-ops.
        main(["--host", "127.0.0.1", "--port", "8002"])


def test_C1_main_allows_loopback_v6_without_auth(monkeypatch) -> None:
    """Binding to ::1 (IPv6 loopback) without auth is allowed."""
    from omniscribe.server import main

    for var in ("OMNISCRIBE_AUTH_TOKEN", "OMNISCRIBE_OCR_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    with _patched_uvicorn():
        main(["--host", "::1", "--port", "8004"])


def test_C1_main_allows_non_loopback_with_auth(monkeypatch) -> None:
    """Binding to 0.0.0.0 with auth set is the public-internet profile."""
    from omniscribe.server import main

    for var in ("OMNISCRIBE_AUTH_TOKEN", "OMNISCRIBE_OCR_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OMNISCRIBE_AUTH_TOKEN", "x" * 64)

    with _patched_uvicorn():
        main(["--host", "0.0.0.0", "--port", "8003"])
