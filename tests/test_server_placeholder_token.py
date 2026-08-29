"""Sprint 5 / M-10 audit fix: placeholder ``OMNISCRIBE_AUTH_TOKEN`` rejection.

The audit found that the server's startup guard (C-1) checked only
that a token was *set* on a non-loopback bind. A common operator
mistake is to copy ``.env.example`` and forget to replace the
``change-me-in-prod`` placeholder — which produces a fully exposed
non-loopback server with a publicly-known bearer token. The fix
adds a second guard that rejects placeholder values on non-loopback
binds unless the operator opts in via ``--allow-placeholder-token``.

These tests patch ``load_settings`` and ``uvicorn.run`` so the
env-derived token is deterministic and the test never actually
starts a real uvicorn worker (which would block forever).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from omniscribe.config import RuntimeSettings
from omniscribe.server import main


def _settings_with_token(token: str) -> RuntimeSettings:
    """Build a minimal RuntimeSettings with the auth_token field set."""
    base = RuntimeSettings.model_construct()
    return base.model_copy(update={"auth_token": token})


def _noop_uvicorn_run(*args: object, **kwargs: object) -> None:
    """Replace ``uvicorn.run`` so the test doesn't actually start a server."""


def test_M10_placeholder_token_on_non_loopback_raises_systemexit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--host 0.0.0.0`` + placeholder token must raise ``SystemExit``."""
    sentinel = _settings_with_token("change-me-in-prod")
    fake_uvicorn = MagicMock()
    fake_uvicorn.run = _noop_uvicorn_run
    with (
        patch("omniscribe.server.load_settings", return_value=sentinel),
        patch(
            "omniscribe.server._load_optional_module",
            return_value=fake_uvicorn,
        ),
    ):
        with pytest.raises(SystemExit) as excinfo:
            main(["--host", "0.0.0.0", "--port", "8000"])
    assert "placeholder" in str(excinfo.value).lower()


def test_M10_placeholder_token_with_opt_out_flag_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--allow-placeholder-token`` bypasses the guard.

    The guard must not block startup when the operator explicitly
    accepts the risk. We assert that the SystemExit is NOT raised
    by the placeholder check (the function will return cleanly
    because uvicorn.run is patched to a no-op).
    """
    sentinel = _settings_with_token("placeholder")
    fake_uvicorn = MagicMock()
    fake_uvicorn.run = _noop_uvicorn_run
    with (
        patch("omniscribe.server.load_settings", return_value=sentinel),
        patch(
            "omniscribe.server._load_optional_module",
            return_value=fake_uvicorn,
        ),
    ):
        # The function should complete without raising. If it does
        # raise, the message must not be the placeholder guard.
        main(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--allow-placeholder-token",
            ]
        )


def test_M10_placeholder_token_on_loopback_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loopback bind + placeholder token must not raise the guard."""
    sentinel = _settings_with_token("change-me-in-prod")
    fake_uvicorn = MagicMock()
    fake_uvicorn.run = _noop_uvicorn_run
    with (
        patch("omniscribe.server.load_settings", return_value=sentinel),
        patch(
            "omniscribe.server._load_optional_module",
            return_value=fake_uvicorn,
        ),
    ):
        main(["--host", "127.0.0.1", "--port", "8000"])


def test_M10_real_token_on_non_loopback_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real, non-placeholder token must not raise the guard."""
    sentinel = _settings_with_token("x" * 64)
    fake_uvicorn = MagicMock()
    fake_uvicorn.run = _noop_uvicorn_run
    with (
        patch("omniscribe.server.load_settings", return_value=sentinel),
        patch(
            "omniscribe.server._load_optional_module",
            return_value=fake_uvicorn,
        ),
    ):
        main(["--host", "0.0.0.0", "--port", "8000"])
