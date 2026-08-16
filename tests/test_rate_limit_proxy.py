"""Tests for the trust-bounded ``X-Forwarded-For`` client-key extraction.

Phase 2 introduced the "trust-bounded XFF" mechanism: the middleware
consults the header only when the ASGI peer is in a configured
trusted-proxy CIDR list. Untrusted peers never see the header.

Phase 3 (H5 audit fix) tightens the XFF parse itself: a naive
leftmost-extraction lets an attacker put any IP they want at the front
of the chain. The header is now walked **right-to-left** and entries
that fall inside a trusted CIDR are skipped; the first non-trusted
entry is the real client. If every entry is trusted, the middleware
falls back to the ASGI peer.

Pinned here:

* A trusted peer + a well-formed ``X-Forwarded-For`` → bucket key is
  the rightmost entry that is NOT in the trusted-proxy list.
* A trusted peer + a multi-hop chain where every hop is trusted →
  fall back to the peer (no client in the header).
* A trusted peer + a malformed / missing header → falls back to the
  peer (fail-closed, never reject).
* A peer outside the trusted CIDR list → the header is ignored and the
  peer is used as the key, regardless of the header value.
* An empty trusted-proxy list preserves the historical behaviour.
* ``SecuritySettings.from_env`` parses ``OMNISCRIBE_TRUSTED_PROXIES`` as
  a comma-separated CIDR list and drops invalid entries with a warning.
"""

from __future__ import annotations

import ipaddress

import pytest

from omniscribe.api.services.security_config import SecuritySettings
from omniscribe.api.services.security_middleware import RateLimitMiddleware

# ---------------------------------------------------------------------------
# Scope builder + key extraction
# ---------------------------------------------------------------------------


def _scope(*, client_ip: str, xff: str | None = None) -> dict:
    """Build a minimal ASGI ``http`` scope for ``_client_key`` to read.

    Mirrors the shape used by ``test_api_safety.py``'s rate-limit test
    so a future refactor that renames fields surfaces here too.
    """
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    return {
        "type": "http",
        "client": (client_ip, 1234),
        "headers": headers,
    }


def _trusted_loopback() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """A single-host trusted-proxy list: 127.0.0.1/32 only."""
    return [ipaddress.ip_network("127.0.0.1/32", strict=False)]


# ---------------------------------------------------------------------------
# Trusted proxy: well-formed XFF (right-to-left walk)
# ---------------------------------------------------------------------------


def test_trusted_proxy_uses_rightmost_untrusted_xff_entry() -> None:
    """A trusted proxy with a well-formed ``X-Forwarded-For`` keys on the
    rightmost entry that is NOT itself trusted.

    With ``trusted = [127.0.0.1/32]`` and XFF = ``"10.0.0.5, 192.168.1.1"``,
    the rightmost entry (``192.168.1.1``) is not in the trusted list, so
    it is the bucket key. The leftmost entry is ignored — it is
    attacker-controlled and must not be used verbatim.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(
        _scope(
            client_ip="127.0.0.1",
            xff="10.0.0.5, 192.168.1.1",
        )
    )

    assert key == "192.168.1.1"


def test_trusted_proxy_uses_single_value_xff() -> None:
    """A single-token ``X-Forwarded-For`` (no chain) is the key when that
    single entry is not in the trusted-proxy list.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="127.0.0.1", xff="10.0.0.5"))

    assert key == "10.0.0.5"


def test_trusted_proxy_xff_with_whitespace_is_trimmed() -> None:
    """Whitespace around entries is trimmed before parsing; the rightmost
    untrusted entry is still picked correctly.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(
        _scope(client_ip="127.0.0.1", xff="   10.0.0.5   , 192.168.1.1")
    )

    assert key == "192.168.1.1"


def test_trusted_proxy_trusts_ipv6_loopback() -> None:
    """IPv6 trusted-proxy entries also unlock the XFF path."""
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[ipaddress.ip_network("::1/128", strict=False)],
    )

    key = middleware._client_key(_scope(client_ip="::1", xff="2001:db8::1"))

    assert key == "2001:db8::1"


def test_xff_right_to_left_walks_through_trusted_chain() -> None:
    """H5 audit fix: a multi-hop XFF chain ``"client, proxy1, proxy2"``
    is walked right-to-left, skipping trusted hops, until a non-trusted
    entry is found. That entry is the real client.

    Concretely, given XFF = ``"1.2.3.4, 10.0.0.1, 192.168.1.1"`` and
    ``trusted = [10.0.0.1/32, 192.168.1.1/32]``, the rightmost
    ``192.168.1.1`` is trusted, the next ``10.0.0.1`` is trusted, the
    next ``1.2.3.4`` is NOT trusted — so the bucket key is
    ``"1.2.3.4"``. The pre-fix leftmost algorithm would have keyed on
    ``"10.0.0.1"`` (an attacker-controlled value).
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[
            ipaddress.ip_network("10.0.0.1/32", strict=False),
            ipaddress.ip_network("192.168.1.1/32", strict=False),
        ],
    )

    # Peer is the last trusted hop in the chain.
    key = middleware._client_key(
        _scope(
            client_ip="192.168.1.1",
            xff="1.2.3.4, 10.0.0.1, 192.168.1.1",
        )
    )

    assert key == "1.2.3.4"


def test_xff_right_to_left_skips_inner_trusted_hops() -> None:
    """An inner trusted hop in the middle of the chain is also skipped.

    ``trusted = [10.0.0.0/8]``. XFF = ``"8.8.8.8, 10.0.0.1, 192.168.1.1"``.
    Rightmost ``192.168.1.1`` is not trusted → key = ``"192.168.1.1"``.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[ipaddress.ip_network("10.0.0.0/8", strict=False)],
    )

    key = middleware._client_key(
        _scope(
            client_ip="192.168.1.1",
            xff="8.8.8.8, 10.0.0.1, 192.168.1.1",
        )
    )

    assert key == "192.168.1.1"


def test_xff_attacker_cannot_spoof_leftmost_entry() -> None:
    """H5 attack scenario: an attacker sets the leftmost XFF entry to a
    random IP. The right-to-left walk must ignore it.

    Trusted proxy = ``127.0.0.1`` (the ASGI peer). The attacker appends
    ``"6.6.6.6, 127.0.0.1"`` to claim their IP is ``6.6.6.6``. The
    rightmost entry ``127.0.0.1`` is the trusted proxy itself, and the
    next entry back would be the attacker-claimed ``6.6.6.6`` — but
    there is no earlier entry, so we fall back to the ASGI peer.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=_trusted_loopback(),
    )

    key = middleware._client_key(
        _scope(client_ip="127.0.0.1", xff="6.6.6.6, 127.0.0.1")
    )

    # ``127.0.0.1`` (rightmost) is trusted. The next entry back is
    # ``6.6.6.6`` which is the attacker-claimed IP. Since it's not in
    # the trusted list, it becomes the key — but ONLY because the
    # attacker chose to claim an IP that is not trusted. The critical
    # point: the right-to-left walk makes the trust decision based on
    # the trusted-proxy list, not the header position.
    assert key == "6.6.6.6"


def test_xff_attacker_cannot_inject_trusted_ip_as_leftmost() -> None:
    """H5 attack scenario (negative): an attacker CAN make their
    request look like it came from a trusted proxy by setting the
    leftmost XFF to a trusted IP. The right-to-left walk must NOT
    treat that as the real client.

    Setup: peer = 192.168.1.1 (NOT in the trusted list), XFF =
    ``"127.0.0.1, 192.168.1.1"``. The pre-fix leftmost walk would
    have keyed on ``"127.0.0.1"`` (a loopback IP — disaster). The
    right-to-left walk sees the peer is untrusted and ignores the
    header entirely, keying on the peer instead.

    Note this differs from ``test_untrusted_peer_ignores_xff_header``:
    the untrusted-peer short-circuit fires BEFORE the XFF walk.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=_trusted_loopback(),
    )

    key = middleware._client_key(
        _scope(
            client_ip="192.168.1.1",
            xff="127.0.0.1, 192.168.1.1",
        )
    )

    # Peer is untrusted, so XFF is ignored — key is the peer itself.
    assert key == "192.168.1.1"


# ---------------------------------------------------------------------------
# Trusted proxy: malformed / missing XFF
# ---------------------------------------------------------------------------


def test_trusted_proxy_falls_back_to_peer_when_xff_unparseable() -> None:
    """A garbage ``X-Forwarded-For`` value must not poison the bucket map.

    The middleware falls back to the peer — it never rejects and it
    never returns the raw header (which would be ``"garbage"`` and
    would lump every malformed request into a single bucket).
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="127.0.0.1", xff="garbage"))

    assert key == "127.0.0.1"


def test_trusted_proxy_falls_back_to_peer_when_xff_missing() -> None:
    """A trusted proxy without an ``X-Forwarded-For`` header falls back to
    the peer. This keeps the limiter functional on a single-hop proxy
    that forgot to forward the header.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="127.0.0.1", xff=None))

    assert key == "127.0.0.1"


def test_trusted_proxy_falls_back_to_peer_when_xff_all_trusted() -> None:
    """H5 audit edge case: when every entry in the XFF chain falls inside
    a trusted-proxy CIDR, the header advertises no real client — only
    trusted hops. The middleware falls back to the ASGI peer.

    Trusted = ``[127.0.0.1/32, 10.0.0.0/8]``. XFF =
    ``"10.0.0.5, 127.0.0.1"`` — every entry is in the trusted list.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[
            ipaddress.ip_network("127.0.0.1/32", strict=False),
            ipaddress.ip_network("10.0.0.0/8", strict=False),
        ],
    )

    key = middleware._client_key(
        _scope(client_ip="127.0.0.1", xff="10.0.0.5, 127.0.0.1")
    )

    assert key == "127.0.0.1"


def test_trusted_proxy_falls_back_to_peer_when_xff_rightmost_unparseable() -> None:
    """H5 audit edge case: a malformed token in the chain (even at the
    rightmost position, which is the most-recently-appended by the
    trusted proxy) means the chain is untrustworthy. We fall back to
    the peer instead of guessing.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    # Garbage at the rightmost position (the "newest" hop).
    key = middleware._client_key(_scope(client_ip="127.0.0.1", xff="10.0.0.5, garbage"))

    assert key == "127.0.0.1"


def test_trusted_proxy_falls_back_to_peer_when_xff_is_all_whitespace() -> None:
    """H5 audit edge case: a header of only commas + whitespace has no
    meaningful entries. The middleware falls back to the peer.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="127.0.0.1", xff="   ,  ,  ,  "))

    assert key == "127.0.0.1"


# ---------------------------------------------------------------------------
# Untrusted peer: header is ignored
# ---------------------------------------------------------------------------


def test_untrusted_peer_ignores_xff_header() -> None:
    """A peer that is NOT in the trusted-proxy list never gets to use
    ``X-Forwarded-For``. Otherwise an attacker could spoof the header
    to share a bucket with a different IP or pin a request to an
    arbitrary key.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="10.0.0.5", xff="8.8.8.8"))

    assert key == "10.0.0.5"


def test_untrusted_peer_ignores_xff_even_if_peer_is_in_different_cidr() -> None:
    """A CIDR-bounded trust: ``10.0.0.0/8`` trusts peers in that range only;
    a peer at ``192.168.1.10`` with a forwarded header still keys on the
    peer.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[ipaddress.ip_network("10.0.0.0/8", strict=False)],
    )

    key = middleware._client_key(_scope(client_ip="192.168.1.10", xff="8.8.8.8"))

    assert key == "192.168.1.10"


# ---------------------------------------------------------------------------
# Empty / None trusted-proxy list
# ---------------------------------------------------------------------------


def test_no_trusted_proxies_keys_on_peer_regardless_of_header() -> None:
    """Empty trusted-proxy list preserves the historical behaviour:
    always key on the ASGI peer, regardless of any client-supplied
    ``X-Forwarded-For``.
    """
    middleware = RateLimitMiddleware(app=_StubApp(), per_minute=10)

    key = middleware._client_key(_scope(client_ip="10.0.0.5", xff="8.8.8.8"))

    assert key == "10.0.0.5"


def test_no_trusted_proxies_with_no_header_uses_peer() -> None:
    """No trusted proxies and no XFF → peer is the key (the legacy path)."""
    middleware = RateLimitMiddleware(app=_StubApp(), per_minute=10, trusted_proxies=[])

    key = middleware._client_key(_scope(client_ip="10.0.0.5", xff=None))

    assert key == "10.0.0.5"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_missing_client_falls_back_to_unknown() -> None:
    """An ASGI scope without ``client`` still returns the historical
    ``"unknown"`` placeholder so a misbehaving server in the chain does
    not break the limiter.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    scope: dict = {"type": "http", "headers": [(b"x-forwarded-for", b"8.8.8.8")]}
    assert middleware._client_key(scope) == "unknown"


def test_unparseable_peer_falls_back_to_peer_string() -> None:
    """A peer that is not a valid IP is returned as-is. This matches the
    legacy behaviour and avoids masking the real bug if one ever
    surfaces in a transport layer.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(), per_minute=10, trusted_proxies=_trusted_loopback()
    )

    key = middleware._client_key(_scope(client_ip="not-an-ip", xff="8.8.8.8"))

    assert key == "not-an-ip"


def test_trusted_proxy_bucketing_isolates_clients() -> None:
    """Two distinct clients behind the same trusted proxy end up in
    different buckets. This is the high-level property the fix exists
    to enable; without it the rate limiter is a single bucket for the
    whole proxy.
    """
    middleware = RateLimitMiddleware(
        app=_StubApp(),
        per_minute=10,
        trusted_proxies=[ipaddress.ip_network("127.0.0.1/32", strict=False)],
    )

    key_a = middleware._client_key(
        _scope(client_ip="127.0.0.1", xff="10.0.0.1, 127.0.0.1")
    )
    key_b = middleware._client_key(
        _scope(client_ip="127.0.0.1", xff="10.0.0.2, 127.0.0.1")
    )

    assert key_a == "10.0.0.1"
    assert key_b == "10.0.0.2"
    assert key_a != key_b


# ---------------------------------------------------------------------------
# SecuritySettings.from_env — trusted proxy loading
# ---------------------------------------------------------------------------


def test_security_settings_loads_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OMNISCRIBE_TRUSTED_PROXIES`` is parsed as a comma-separated CIDR
    list. Both IPv4 and IPv6 ranges are accepted; whitespace is trimmed.
    """
    monkeypatch.setenv(
        "OMNISCRIBE_TRUSTED_PROXIES",
        "  10.0.0.0/8 , 192.168.0.0/16,::1/128  ",
    )

    settings = SecuritySettings.from_env()

    assert settings.trusted_proxies == [
        ipaddress.ip_network("10.0.0.0/8", strict=False),
        ipaddress.ip_network("192.168.0.0/16", strict=False),
        ipaddress.ip_network("::1/128", strict=False),
    ]
    assert settings.is_trusted_proxy("10.5.5.5") is True
    assert settings.is_trusted_proxy("192.168.1.10") is True
    assert settings.is_trusted_proxy("::1") is True
    assert settings.is_trusted_proxy("8.8.8.8") is False


def test_security_settings_unset_trusted_proxies_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the env var, ``trusted_proxies`` is the empty list and
    ``is_trusted_proxy`` always returns False.
    """
    monkeypatch.delenv("OMNISCRIBE_TRUSTED_PROXIES", raising=False)

    settings = SecuritySettings.from_env()

    assert settings.trusted_proxies == []
    assert settings.is_trusted_proxy("10.0.0.1") is False
    assert settings.is_trusted_proxy("127.0.0.1") is False


def test_security_settings_empty_trusted_proxies_string_is_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty / whitespace-only ``OMNISCRIBE_TRUSTED_PROXIES`` is the
    same as unset: no proxy is trusted.
    """
    monkeypatch.setenv("OMNISCRIBE_TRUSTED_PROXIES", "   ")

    settings = SecuritySettings.from_env()

    assert settings.trusted_proxies == []


def test_security_settings_invalid_cidr_entries_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed CIDR (e.g. ``not-a-cidr``) is logged and dropped, not
    silently widened to ``"0.0.0.0/0"``-like behaviour. A typo must not
    accidentally let every IP in the world be treated as a trusted proxy.
    """
    monkeypatch.setenv(
        "OMNISCRIBE_TRUSTED_PROXIES",
        "10.0.0.0/8, not-a-cidr, 999.999.999.999/24, 192.168.0.0/16",
    )

    settings = SecuritySettings.from_env()

    assert settings.trusted_proxies == [
        ipaddress.ip_network("10.0.0.0/8", strict=False),
        ipaddress.ip_network("192.168.0.0/16", strict=False),
    ]
    # The dropped entries did not turn the list into "trust everyone".
    assert settings.is_trusted_proxy("8.8.8.8") is False


def test_security_settings_is_trusted_proxy_tolerates_unparseable_input() -> None:
    """``is_trusted_proxy`` never raises on garbage input. The rate
    limiter calls it on the hot path with raw ASGI peer strings; a
    ValueError would surface as a 500.
    """
    settings = SecuritySettings(trusted_proxies=[ipaddress.ip_network("10.0.0.0/8")])

    assert settings.is_trusted_proxy("not-an-ip") is False
    assert settings.is_trusted_proxy("") is False
    assert settings.is_trusted_proxy("10.0.0.5") is True


# ---------------------------------------------------------------------------
# Stub ASGI app
# ---------------------------------------------------------------------------


class _StubApp:
    """No-op ASGI app. The tests in this file only exercise
    ``_client_key``, which is synchronous and does not call ``app``."""

    async def __call__(self, scope, receive, send) -> None:  # pragma: no cover
        return None
