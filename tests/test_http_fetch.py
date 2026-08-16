"""Coverage for :mod:`omniscribe.api.services.http_fetch`.

The fetcher is used by the glossary import URL endpoint (lazy import).
The new contract is:

1. The URL (and every 3xx ``Location`` hop) is validated against
   :func:`omniscribe.utils.security.is_ssrf_target` before the
   connection is opened.
2. The TCP connection is pinned to the IP the SSRF guard resolved —
   a DNS rebinding attack that flips the record between check and
   connect cannot redirect the request.
3. Only ``httpx`` is used; the previous ``urllib`` fallback was
   removed because it followed redirects and accepted ``file://``
   natively.

Every test in this file uses real loopback HTTP servers — no network,
no production dependency.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from collections.abc import Iterator
from unittest import mock

import httpx
import pytest

from omniscribe.api.services import http_fetch
from omniscribe.api.services.http_fetch import SSRFBlockedError
from omniscribe.utils.security import SSRFCheckResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# Most tests need ALLOW_SSRF_LOCAL=true because they spin up real
# loopback servers. Tests that explicitly verify the guard *blocks* a
# loopback / link-local target (the redirect-to-metadata-IP test)
# override the env back to "false" so the guard actually blocks it.
@pytest.fixture(autouse=True)
def _allow_ssrf_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to ``ALLOW_SSRF_LOCAL=true`` for loopback test servers.

    Tests that need the production-like "block everything local"
    behaviour override the env to ``"false"`` with their own
    ``monkeypatch.setenv`` call, which takes precedence for that test.
    """
    monkeypatch.setenv("ALLOW_SSRF_LOCAL", "true")


@pytest.fixture
def localhost_url() -> Iterator[str]:
    """Spin a temporary HTTP server on a random port serving a known body."""
    body = b"hello url fetch"

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # http.server demands this exact method name
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):  # silence stderr noise
            return

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as srv:
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/sample.txt"
        finally:
            srv.shutdown()
            thread.join(timeout=2)


# ---------------------------------------------------------------------------
# Happy-path coverage of the httpx branch
# ---------------------------------------------------------------------------


async def test_fetch_url_bytes_via_httpx_happy_path(localhost_url: str) -> None:
    """The httpx branch returns the body verbatim."""
    body = await http_fetch.fetch_url_bytes(localhost_url)
    assert body == b"hello url fetch"


async def test_fetch_url_bytes_returns_empty_for_empty_body(localhost_url: str) -> None:
    """Empty response bodies (204/304, zero-byte resources) return ``b""``.

    ``bytes(content) if content else b""`` short-circuits when the
    response carries no payload. Patches the whole ``AsyncClient``
    constructor so the test doesn't depend on a real empty-body server.
    """
    empty_response = mock.Mock(
        content=b"",
        is_redirect=False,
        aclose=mock.AsyncMock(),
    )
    empty_response.raise_for_status = mock.Mock(return_value=None)
    empty_response.headers = {}
    fake_client = mock.Mock()
    fake_client.get = mock.AsyncMock(return_value=empty_response)
    fake_client.aclose = mock.AsyncMock(return_value=None)
    with mock.patch.object(httpx, "AsyncClient", return_value=fake_client):
        body = await http_fetch.fetch_url_bytes(localhost_url)
    assert body == b""


# ---------------------------------------------------------------------------
# SSRF C1: redirect to a blocked target is rejected (no metadata endpoint walk)
# ---------------------------------------------------------------------------


def _make_redirect_handler(*, follow_target: str | None) -> type:
    """Build an HTTP handler that 302-redirects to ``follow_target`` if set."""

    class _RedirectingHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # http.server demands this exact method name
            if follow_target is not None and self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", follow_target)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            body = b"unreachable"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):  # silence stderr noise
            return

    return _RedirectingHandler


def _start_server(
    handler_cls: type,
) -> tuple[socketserver.TCPServer, int, threading.Thread]:
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, port, thread


@pytest.fixture
def redirect_to_metadata_ip() -> Iterator[str]:
    """Spin a server that replies 302 → ``http://169.254.169.254/``."""
    cls = _make_redirect_handler(follow_target="http://169.254.169.254/")
    srv, port, thread = _start_server(cls)
    try:
        yield f"http://127.0.0.1:{port}/redirect"
    finally:
        srv.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def redirect_to_file_scheme() -> Iterator[str]:
    """Spin a server that replies 302 → ``file:///etc/passwd``."""
    cls = _make_redirect_handler(follow_target="file:///etc/passwd")
    srv, port, thread = _start_server(cls)
    try:
        yield f"http://127.0.0.1:{port}/redirect"
    finally:
        srv.shutdown()
        thread.join(timeout=2)


async def test_redirect_to_metadata_ip_is_blocked(
    redirect_to_metadata_ip: str,
) -> None:
    """A 302 → ``http://169.254.169.254/`` must raise :class:`SSRFBlockedError`.

    Regression for the T2 / M2 audit gap: the previous code relied on a
    urllib fallback that followed 3xx natively and accepted ``file://``
    schemes. Both reach this router today and are validated before
    connect.

    Mocks the SSRF guard to allow the original localhost hop (so the
    server can return the redirect) and block the IMDS IP — the
    production-like posture where IMDS is unreachable regardless of
    whether local development is enabled.
    """
    localhost = redirect_to_metadata_ip.split("/redirect")[0]  # http://127.0.0.1:port
    imds_url = "http://169.254.169.254/"

    def _fake_ssrf(url: str) -> SSRFCheckResult:
        if url == imds_url:
            return SSRFCheckResult(False, None, "literal-blocked-ip")
        # Anything else: allow and pin to the literal host.
        # We don't actually need the IP for the localhost server (the
        # URL parser already produced the right host:port) but the
        # contract requires a non-None resolved_ip when allowed=True.
        from urllib.parse import urlparse

        host = urlparse(url).hostname or "127.0.0.1"
        return SSRFCheckResult(True, host)

    with mock.patch(
        "omniscribe.api.services.http_fetch.is_ssrf_target",
        new=mock.AsyncMock(side_effect=_fake_ssrf),
    ):
        with pytest.raises(SSRFBlockedError) as excinfo:
            await http_fetch.fetch_url_bytes(redirect_to_metadata_ip)

    # The blocking reason should name the failure mode (literal-blocked-ip
    # is the catch-all for the IMDS IP — both is_blocked_ip and the
    # metadata-endpoint shortcut would match it; the former wins
    # because we hit the literal-IP branch first).
    assert "169.254.169.254" not in (excinfo.value.reason or "")
    assert excinfo.value.url == imds_url
    # The localhost server must not be implicated in the failure.
    assert localhost not in excinfo.value.url


async def test_redirect_to_file_scheme_is_blocked(redirect_to_file_scheme: str) -> None:
    """A 302 → ``file:///etc/passwd`` must raise :class:`SSRFBlockedError`.

    The SSRF guard rejects any non-http(s) scheme up front, so the
    fetcher must surface that as ``SSRFBlockedError`` rather than
    silently following the redirect into the local filesystem.
    """
    with pytest.raises(SSRFBlockedError) as excinfo:
        await http_fetch.fetch_url_bytes(redirect_to_file_scheme)
    assert excinfo.value.url == "file:///etc/passwd"
    assert excinfo.value.reason == "unsupported-scheme"


# ---------------------------------------------------------------------------
# SSRF C2: TOCTOU defense — the transport connects to the validated IP
# ---------------------------------------------------------------------------


async def test_redirect_to_safe_loopback_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 302 → 127.0.0.1 must still be followed (negative control).

    Confirms the SSRF-aware redirect handler isn't an outright refusal:
    a redirect to another loopback URL still works when
    ``ALLOW_SSRF_LOCAL`` is on. Pins the contract as "validate the
    target" rather than "reject all 3xx".
    """
    monkeypatch.setenv("ALLOW_SSRF_LOCAL", "true")

    # Final body server
    final_cls = _make_redirect_handler(follow_target=None)

    class _FinalHandler(final_cls):  # type: ignore[misc, valid-type]
        def do_GET(self):  # type: ignore[override]
            self.send_response(200)
            body = b"final"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    final_srv = socketserver.TCPServer(("127.0.0.1", 0), _FinalHandler)
    final_port = final_srv.server_address[1]
    final_thread = threading.Thread(target=final_srv.serve_forever, daemon=True)
    final_thread.start()

    # Redirecting server
    redirect_cls = _make_redirect_handler(
        follow_target=f"http://127.0.0.1:{final_port}/anything"
    )
    redirect_srv = socketserver.TCPServer(("127.0.0.1", 0), redirect_cls)
    redirect_port = redirect_srv.server_address[1]
    redirect_thread = threading.Thread(target=redirect_srv.serve_forever, daemon=True)
    redirect_thread.start()

    try:
        body = await http_fetch.fetch_url_bytes(
            f"http://127.0.0.1:{redirect_port}/redirect"
        )
    finally:
        redirect_srv.shutdown()
        redirect_thread.join(timeout=2)
        final_srv.shutdown()
        final_thread.join(timeout=2)
    assert body == b"final"


async def test_toctou_dns_rebinding_is_neutralised_by_ip_pinning() -> None:
    """TOCTOU defense: the transport must connect to the IP the SSRF
    guard resolved, not a different one supplied at connect time.

    Simulates the rebinding attack: at check time the SSRF guard
    returns a public IP (1.2.3.4); at connect time the attacker has
    flipped DNS so the URL would resolve to 127.0.0.1. The fetcher
    must use the validated IP — if it re-resolved, the connection
    would go to the attacker's target.
    """
    # The validated IP — what the SSRF guard would return.
    validated_ip = "203.0.113.1"
    # The rebinding target — what naive DNS would return at connect time.
    rebinding_target = "127.0.0.1"

    # We assert the transport opens the socket to validated_ip, NOT
    # to the rebinding target. asyncio.open_connection is patched to
    # record its ``host`` argument. OSError (the parent of
    # ConnectionError) is the synthetic failure we throw to skip the
    # real network roundtrip; the transport wraps it in
    # ``httpx.ConnectError`` before propagating.
    with mock.patch(
        "omniscribe.api.services.http_fetch.asyncio.open_connection",
        new=mock.AsyncMock(side_effect=ConnectionError("forced")),
    ) as connect_mock:
        # is_ssrf_target returns the validated IP. The fetcher should
        # use that to build the transport.
        with mock.patch(
            "omniscribe.api.services.http_fetch.is_ssrf_target",
            new=mock.AsyncMock(
                return_value=SSRFCheckResult(allowed=True, resolved_ip=validated_ip)
            ),
        ):
            with pytest.raises(httpx.ConnectError):
                await http_fetch.fetch_url_bytes("http://attacker.example/path")

    # The transport's open_connection call must use the validated IP.
    assert connect_mock.await_count >= 1
    for call in connect_mock.await_args_list:
        # open_connection(host=..., port=..., ssl=..., server_hostname=...)
        kwargs = call.kwargs
        args = call.args
        host = kwargs.get("host", args[0] if args else None)
        assert host == validated_ip, (
            f"open_connection got host={host!r} (rebinding target was "
            f"{rebinding_target!r}); transport must use the validated IP"
        )
        assert host != rebinding_target
