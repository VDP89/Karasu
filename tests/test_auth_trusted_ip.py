"""Trusted-client-IP derivation tests — UI-13 §3-G three-layer
defence (Codex rounds 1+2+3 P1 bindings 2026-05-07) + pin
§11.6.9.

Covers:
  * parse_forwarded_chain — RFC 7239 Forwarded + XFF fallback +
    malformed entry skip + IPv6/IPv4-with-port stripping.
  * derive_client_ip — Layer B right-to-left trusted-hop walk +
    Layer C untrusted-peer guard + UNTRUSTED_FORWARDED sentinel
    + None on all-trusted chain.
  * is_loopback_ip — IP literals only, "localhost" rejected.
  * is_loopback_bind — IP + "localhost" hostname accepted; mixed
    or non-loopback resolution rejected.

Test surface lines map 1:1 onto the binding bullets in
docs/ui/ui-13-design-brief.md §3-G "Test surface (binding)"
plus the Codex round 3 P1 regression cases."""

from __future__ import annotations

import socket
from unittest import mock

import pytest

from karasu.ui._auth import (
    UNTRUSTED_FORWARDED,
    derive_client_ip,
    is_loopback_bind,
    is_loopback_ip,
    parse_forwarded_chain,
)


# ---------------------------------------------------------------------------
# parse_forwarded_chain — RFC 7239 Forwarded + XFF fallback
# ---------------------------------------------------------------------------


def test_parse_forwarded_simple_for() -> None:
    assert parse_forwarded_chain(
        forwarded_header='for=203.0.113.7',
        xff_header=None,
    ) == ["203.0.113.7"]


def test_parse_forwarded_quoted_for() -> None:
    assert parse_forwarded_chain(
        forwarded_header='for="203.0.113.7"',
        xff_header=None,
    ) == ["203.0.113.7"]


def test_parse_forwarded_multi_hop() -> None:
    assert parse_forwarded_chain(
        forwarded_header='for=203.0.113.7, for=127.0.0.1',
        xff_header=None,
    ) == ["203.0.113.7", "127.0.0.1"]


def test_parse_forwarded_with_proto_and_host() -> None:
    """Real-world Forwarded entries carry proto/host alongside
    for=. Only the for= field contributes to the chain."""
    assert parse_forwarded_chain(
        forwarded_header='for=203.0.113.7;proto=https;host=karasu.example',
        xff_header=None,
    ) == ["203.0.113.7"]


def test_parse_forwarded_ipv6_bracketed_with_port() -> None:
    assert parse_forwarded_chain(
        forwarded_header='for="[::1]:8080"',
        xff_header=None,
    ) == ["::1"]


def test_parse_forwarded_ipv4_with_port() -> None:
    assert parse_forwarded_chain(
        forwarded_header='for=192.0.2.5:443',
        xff_header=None,
    ) == ["192.0.2.5"]


def test_parse_forwarded_skips_malformed_entry() -> None:
    """Entry without for= field contributes nothing, but valid
    siblings are preserved."""
    assert parse_forwarded_chain(
        forwarded_header='proto=https, for=203.0.113.7',
        xff_header=None,
    ) == ["203.0.113.7"]


def test_parse_forwarded_takes_precedence_over_xff() -> None:
    """When both headers are present, Forwarded wins."""
    assert parse_forwarded_chain(
        forwarded_header='for=203.0.113.7',
        xff_header='198.51.100.99',
    ) == ["203.0.113.7"]


def test_parse_xff_fallback() -> None:
    assert parse_forwarded_chain(
        forwarded_header=None,
        xff_header='203.0.113.7, 127.0.0.1',
    ) == ["203.0.113.7", "127.0.0.1"]


def test_parse_xff_strips_whitespace() -> None:
    assert parse_forwarded_chain(
        forwarded_header=None,
        xff_header='203.0.113.7 ,  127.0.0.1   ',
    ) == ["203.0.113.7", "127.0.0.1"]


def test_parse_xff_drops_empty_segments() -> None:
    assert parse_forwarded_chain(
        forwarded_header=None,
        xff_header=', , 203.0.113.7,,',
    ) == ["203.0.113.7"]


def test_parse_both_absent_returns_empty() -> None:
    assert parse_forwarded_chain(
        forwarded_header=None,
        xff_header=None,
    ) == []


def test_parse_forwarded_empty_string_is_empty_chain() -> None:
    assert parse_forwarded_chain(
        forwarded_header="",
        xff_header=None,
    ) == []


# ---------------------------------------------------------------------------
# derive_client_ip — Layer B right-to-left walk
# ---------------------------------------------------------------------------


_DEFAULT_TRUSTED = frozenset({"127.0.0.1", "::1"})


def test_derive_dev_posture_localhost_returns_peer() -> None:
    """Brief §3-G test surface bullet 1: dev posture (no
    reverse proxy, ``auth.trusted_proxies: []``). Peer
    127.0.0.1 + no chain → return peer; the caller's
    loopback-IP rule maps that to a rate-limit bypass."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=[],
        trusted_proxies=frozenset(),
    ) == "127.0.0.1"


def test_derive_deployed_backend_direct_returns_none() -> None:
    """Deployed posture (default trusted_proxies includes
    127.0.0.1 because the proxy runs there). A request that
    hits the backend WITHOUT going through the proxy presents
    a trusted peer + empty chain → the all-trusted branch
    returns ``None``. The caller fail-closes per §3-G rule 4
    (None → no bypass, fresh slot)."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=[],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) is None


def test_derive_proxied_public_ip() -> None:
    """127.0.0.1 peer + chain ending in 192.0.2.5 → 192.0.2.5
    is the rate-limit key; NO bypass."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["192.0.2.5"],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) == "192.0.2.5"


def test_derive_proxied_localhost_browser_all_trusted() -> None:
    """127.0.0.1 peer + Forwarded for=127.0.0.1, default
    trusted_proxies includes 127.0.0.1 → reversed walk skips
    every entry as trusted; returns ``None`` (all-trusted
    chain branch). Caller fail-closes per rule 4. Brief §3-G
    test surface bullet 3 framed at the primitive level."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["127.0.0.1"],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) is None


def test_derive_remote_peer_no_chain() -> None:
    """Remote untrusted peer + no chain → peer addr keys; NO
    bypass."""
    assert derive_client_ip(
        peer_addr="198.51.100.5",
        forwarded_chain=[],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) == "198.51.100.5"


def test_derive_spoofed_chain_under_append_mode_proxy() -> None:
    """Peer 127.0.0.1, XFF "127.0.0.1, 198.51.100.5" — the
    attacker spoofs the leftmost entry. Right-to-left walk
    skips the trusted 127.0.0.1 hop and returns the real
    attacker IP recorded by the proxy. Codex round 2 P1
    regression."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["127.0.0.1", "198.51.100.5"],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) == "198.51.100.5"


def test_derive_multi_hop_trusted_chain() -> None:
    """Peer 127.0.0.1, chain "203.0.113.7, 127.0.0.2" with both
    127.0.0.1 + 127.0.0.2 trusted → walk returns the public
    client; NO bypass."""
    trusted = frozenset({"127.0.0.1", "127.0.0.2", "::1"})
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["203.0.113.7", "127.0.0.2"],
        trusted_proxies=trusted,
    ) == "203.0.113.7"


def test_derive_all_trusted_chain_returns_none() -> None:
    """Chain entirely within the trusted-proxy ring is
    impossible for genuine external traffic; fail-closed
    sentinel ``None``."""
    trusted = frozenset({"127.0.0.1", "127.0.0.2"})
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["127.0.0.2"],
        trusted_proxies=trusted,
    ) is None


# ---------------------------------------------------------------------------
# derive_client_ip — Layer C untrusted-peer guard
# ---------------------------------------------------------------------------


def test_derive_empty_trusted_localhost_peer_public_xff() -> None:
    """``auth.trusted_proxies: []`` + peer 127.0.0.1 +
    XFF "203.0.113.7" → UNTRUSTED_FORWARDED. The peer cannot
    self-promote via attacker-supplied forwarding when the
    operator wiped the trusted list. Codex round 3 P1
    regression 2026-05-07."""
    assert derive_client_ip(
        peer_addr="127.0.0.1",
        forwarded_chain=["203.0.113.7"],
        trusted_proxies=frozenset(),
    ) is UNTRUSTED_FORWARDED


def test_derive_untrusted_peer_with_xff_returns_sentinel() -> None:
    """Peer 198.51.100.5 (NOT in trusted_proxies) + XFF
    "127.0.0.1" → UNTRUSTED_FORWARDED. Cannot self-promote to
    localhost via spoofed XFF when not on the trusted-proxy
    list. Codex round 3 P1 regression 2026-05-07."""
    assert derive_client_ip(
        peer_addr="198.51.100.5",
        forwarded_chain=["127.0.0.1"],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) is UNTRUSTED_FORWARDED


def test_derive_untrusted_peer_no_chain_returns_peer() -> None:
    """Untrusted peer with NO chain → peer addr (genuine
    direct-to-app case, distinct from sentinel branch)."""
    assert derive_client_ip(
        peer_addr="198.51.100.5",
        forwarded_chain=[],
        trusted_proxies=_DEFAULT_TRUSTED,
    ) == "198.51.100.5"


def test_derive_sentinel_is_singleton() -> None:
    """UNTRUSTED_FORWARDED is identity-compared by callers
    (``is`` not ``==``); pin the sentinel as a stable object."""
    a = derive_client_ip(
        peer_addr="198.51.100.5",
        forwarded_chain=["127.0.0.1"],
        trusted_proxies=_DEFAULT_TRUSTED,
    )
    b = derive_client_ip(
        peer_addr="198.51.100.99",
        forwarded_chain=["10.0.0.1"],
        trusted_proxies=_DEFAULT_TRUSTED,
    )
    assert a is UNTRUSTED_FORWARDED
    assert b is UNTRUSTED_FORWARDED
    assert a is b


# ---------------------------------------------------------------------------
# is_loopback_ip — IP literals only
# ---------------------------------------------------------------------------


def test_loopback_ip_v4_canonical() -> None:
    assert is_loopback_ip("127.0.0.1") is True


def test_loopback_ip_v4_prefix_range() -> None:
    """The whole 127.0.0.0/8 block is loopback."""
    assert is_loopback_ip("127.0.0.5") is True
    assert is_loopback_ip("127.255.255.254") is True


def test_loopback_ip_v6() -> None:
    assert is_loopback_ip("::1") is True


def test_loopback_ip_rejects_hostname() -> None:
    """is_loopback_ip is for parsed IPs only — the
    "localhost" hostname is handled by is_loopback_bind, not
    here. Pin §3-G "A forwarded chain entry of 'localhost'
    therefore cannot trigger the bypass"."""
    assert is_loopback_ip("localhost") is False


def test_loopback_ip_rejects_public_v4() -> None:
    assert is_loopback_ip("203.0.113.7") is False
    assert is_loopback_ip("198.51.100.5") is False


def test_loopback_ip_rejects_private_non_loopback() -> None:
    assert is_loopback_ip("10.0.0.1") is False
    assert is_loopback_ip("192.168.1.1") is False
    assert is_loopback_ip("0.0.0.0") is False


def test_loopback_ip_rejects_empty_string() -> None:
    assert is_loopback_ip("") is False


# ---------------------------------------------------------------------------
# is_loopback_bind — host validation for cmd_ui --no-auth
# ---------------------------------------------------------------------------


def test_loopback_bind_accepts_localhost_hostname() -> None:
    assert is_loopback_bind("localhost") is True


def test_loopback_bind_accepts_v4_literal() -> None:
    assert is_loopback_bind("127.0.0.1") is True


def test_loopback_bind_accepts_v6_literal() -> None:
    assert is_loopback_bind("::1") is True


def test_loopback_bind_rejects_zero_zero_zero_zero() -> None:
    """0.0.0.0 is the bind-anywhere wildcard; --no-auth must
    refuse this combination at startup."""
    assert is_loopback_bind("0.0.0.0") is False


def test_loopback_bind_rejects_public_ip() -> None:
    assert is_loopback_bind("203.0.113.7") is False


def test_loopback_bind_resolves_unknown_host() -> None:
    """A hostname that getaddrinfo cannot resolve fails closed
    (gaierror branch)."""
    with mock.patch(
        "karasu.ui._auth.socket.getaddrinfo",
        side_effect=socket.gaierror,
    ):
        assert is_loopback_bind("definitely.not.real.invalid") is False


def test_loopback_bind_rejects_mixed_resolution() -> None:
    """A host that resolves to BOTH loopback and non-loopback
    addresses is rejected (deliberately conservative per
    §3-B)."""
    fake_infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.7", 0)),
    ]
    with mock.patch(
        "karasu.ui._auth.socket.getaddrinfo",
        return_value=fake_infos,
    ):
        assert is_loopback_bind("ambiguous.example") is False


def test_loopback_bind_accepts_resolved_loopback_only() -> None:
    """Custom hostname (e.g. /etc/hosts entry) that resolves
    entirely to loopback addresses is accepted."""
    fake_infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 0, 0, 0)),
    ]
    with mock.patch(
        "karasu.ui._auth.socket.getaddrinfo",
        return_value=fake_infos,
    ):
        assert is_loopback_bind("local.dev.invalid") is True


def test_loopback_bind_empty_resolution_rejected() -> None:
    """A getaddrinfo result of [] cannot be confirmed loopback
    → reject (no positive evidence the bind is safe)."""
    with mock.patch(
        "karasu.ui._auth.socket.getaddrinfo",
        return_value=[],
    ):
        assert is_loopback_bind("empty.example") is False
