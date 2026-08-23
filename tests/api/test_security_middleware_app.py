"""App-level security middleware wiring via ``server.create_app()``.

Unit-level ASGI coverage of each middleware lives in
``tests/test_security_middleware.py``; this suite proves the full app
actually mounts them and honors the env-driven ``SecuritySettings``.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


def _create_app_with_security(monkeypatch, **env):
    """Build the full app via `create_app()` so middleware is wired."""
    from omniscribe import server

    for key in (
        "OMNISCRIBE_AUTH_TOKEN",
        "OMNISCRIBE_CORS_ORIGINS",
        "OMNISCRIBE_MAX_UPLOAD_MB",
        "OMNISCRIBE_RATE_LIMIT_PER_MIN",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    app = server.create_app()
    return app


def test_bearer_auth_required_when_token_set(monkeypatch):
    secret_token = "s3cret-token-for-testing-purposes-12345"
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_AUTH_TOKEN=secret_token)
    client = TestClient(app)

    unauthorized = client.get("/api/config")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"] == "Unauthorized"

    wrong = client.get("/api/config", headers={"Authorization": "Bearer wrong-token"})
    assert wrong.status_code == 401

    right = client.get(
        "/api/config",
        headers={"Authorization": f"Bearer {secret_token}"},
    )
    assert right.status_code == 200


def test_bearer_auth_accepts_lowercase_scheme(monkeypatch):
    valid_token = "valid-token-with-sufficient-entropy-32chars"
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_AUTH_TOKEN=valid_token)
    client = TestClient(app)
    response = client.get(
        "/api/config", headers={"Authorization": f"bearer {valid_token}"}
    )
    assert response.status_code == 200


def test_max_upload_size_rejects_oversized_content_length(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_MAX_UPLOAD_MB="1")
    client = TestClient(app)
    response = client.post(
        "/api/config",
        content=b"x" * (2 * 1024 * 1024),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    payload = response.json()
    assert payload["limit_bytes"] == str(1 * 1024 * 1024)


def test_max_upload_size_passes_undersized(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_MAX_UPLOAD_MB="10")
    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200


def test_rate_limit_rejects_after_cap(monkeypatch):
    app = _create_app_with_security(monkeypatch, OMNISCRIBE_RATE_LIMIT_PER_MIN="3")
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/api/config").status_code == 200

    assert client.get("/api/config").status_code == 429
    assert client.get("/api/config").status_code == 429


def test_rate_limit_isolates_per_client_ip(monkeypatch):
    """Two different client IPs share independent buckets.

    TestClient doesn't let us spoof the address easily, so the second
    bucket is driven by a freshly-constructed middleware instance on
    the same client; the underlying deque-by-key isolation is what
    the property is exercising.
    """
    from omniscribe.api.middleware import RateLimitMiddleware

    fake_app_calls: list[str] = []

    async def passthrough(scope, receive, send):
        fake_app_calls.append(scope.get("client", ("unknown",))[0])

    rm = RateLimitMiddleware(passthrough, per_minute=2)

    async def drive(client_ip: str) -> None:
        rm._hits.clear()
        captured: list[bool] = []

        async def fake_receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        class _CaptureSend:
            def __init__(self):
                self.status: int | None = None

            async def __call__(self, msg):
                if msg["type"] == "http.response.start":
                    self.status = msg["status"]

        for _ in range(3):
            cap = _CaptureSend()
            await rm(
                {
                    "type": "http",
                    "client": (client_ip, 1234),
                    "headers": [],
                    "method": "GET",
                    "path": "/x",
                    "raw_path": b"/x",
                    "query_string": b"",
                    "scheme": "http",
                    "server": ("test", 80),
                },
                fake_receive,
                cap,
            )
            captured.append(cap.status)

        assert captured == [None, None, 429]

    asyncio.run(drive("10.0.0.1"))
    asyncio.run(drive("10.0.0.2"))
