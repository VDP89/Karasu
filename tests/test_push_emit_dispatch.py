"""HTTP delivery + 410/404 prune + transport privacy tests.

Brief §3-E + §3-H + §3-I + pin §11.6.13 + §11.6.16.

The HTTP layer is mocked: tests inject a ``recording_post``
that captures (url, body, headers, timeout) and returns
canned :class:`HttpResponse` values. Real ``urllib`` only
exercises in :func:`test_urllib_post_adapts_httperror`.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
from base64 import urlsafe_b64decode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from karasu.eventbus import Event
from karasu.push_emit._dispatch import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_TTL_SECONDS,
    DispatcherConfig,
    HttpResponse,
    PushDispatcher,
)
from karasu.push_emit._keys import generate_vapid_keypair
from karasu.push_emit._signing import load_private_key
from karasu.ui.push_store import (
    append_subscription,
    compute_endpoint_hash,
    seed_vapid,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class RecordedRequest:
    url: str
    body: bytes
    headers: Mapping[str, str]
    timeout: float


@dataclass
class StoredResponse:
    """A canned response with optional headers; tests configure
    one or more then attach to the recorder."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)


class HttpRecorder:
    """Captures requests + replays scripted responses.

    Configure with ``replies = [HttpResponse(...), ...]`` or
    ``raise_with`` to make the post raise.
    """

    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self.replies: list[HttpResponse] = []
        self.raise_with: BaseException | None = None

    def __call__(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> HttpResponse:
        self.requests.append(
            RecordedRequest(url=url, body=body, headers=dict(headers), timeout=timeout)
        )
        if self.raise_with is not None:
            raise self.raise_with
        if not self.replies:
            return HttpResponse(status=201)
        return self.replies.pop(0)


@pytest.fixture
def http() -> HttpRecorder:
    return HttpRecorder()


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "karasu-push.json"


@pytest.fixture
def vapid_keys() -> tuple[str, str]:
    """Persistent keypair across the whole test (signing
    works on reused private key)."""
    return generate_vapid_keypair()


@pytest.fixture
def seeded_store(
    store_path: Path, vapid_keys: tuple[str, str]
) -> tuple[Path, str]:
    """Store with a VAPID seed + ONE subscription. Returns
    (path, subscription endpoint)."""
    public, private = vapid_keys
    seed_vapid(store_path, public=public, private=private)
    endpoint = "https://fcm.googleapis.com/fcm/send/SAMPLE_ABC"
    append_subscription(
        store_path,
        subscription={
            "endpoint": endpoint,
            "keys": {
                "p256dh": _sample_p256dh(),
                "auth": _sample_auth(),
            },
        },
        categories=["attention", "errors"],
    )
    return store_path, endpoint


def _sample_p256dh() -> str:
    """Generate a fresh UA p256dh from a throwaway keypair."""
    from cryptography.hazmat.primitives.asymmetric import ec

    pk = ec.generate_private_key(ec.SECP256R1())
    nums = pk.public_key().public_numbers()
    raw = (
        b"\x04"
        + nums.x.to_bytes(32, "big")
        + nums.y.to_bytes(32, "big")
    )
    from base64 import urlsafe_b64encode

    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sample_auth() -> str:
    import os
    from base64 import urlsafe_b64encode

    return urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")


@pytest.fixture
def dispatcher(
    seeded_store: tuple[Path, str],
    vapid_keys: tuple[str, str],
    http: HttpRecorder,
) -> PushDispatcher:
    path, _ = seeded_store
    public, private = vapid_keys
    config = DispatcherConfig(
        store_path=path,
        private_key=load_private_key(private),
        public_key_b64u=public,
        subject="mailto:operator@localhost.invalid",
    )
    return PushDispatcher(config, http_post=http)


def _ev(event_id: str = "ev-1") -> Event:
    return Event(
        type="agent_response", source="adapter", id=event_id
    )


# ---------------------------------------------------------------------------
# Happy path: 201 → success, no store mutation
# ---------------------------------------------------------------------------


def test_happy_path_201_dispatches_one_post(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=201)]

    dispatcher.dispatch(_ev(), eh, "attention")

    assert len(http.requests) == 1
    request = http.requests[0]
    # Pin §11.6.16: raw endpoint materialises ONLY as
    # outbound REQUEST TARGET URL.
    assert request.url == endpoint
    assert request.headers["Content-Encoding"] == "aes128gcm"
    assert request.headers["TTL"] == str(DEFAULT_TTL_SECONDS)
    assert request.headers["Topic"] == "attention"
    auth = request.headers["Authorization"]
    assert auth.startswith("vapid t=")
    assert ", k=" in auth


def test_happy_path_does_not_mutate_store(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    before = path.read_bytes()

    dispatcher.dispatch(_ev(), eh, "attention")

    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# 410 / 404 → prune (no bus event)
# ---------------------------------------------------------------------------


def test_410_prunes_subscription(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=410)]

    dispatcher.dispatch(_ev(), eh, "attention")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("subscriptions") == []


def test_404_treated_as_410(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=404)]

    dispatcher.dispatch(_ev(), eh, "attention")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("subscriptions") == []


def test_410_log_carries_endpoint_hash_only(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=410)]

    with caplog.at_level(logging.DEBUG, logger="karasu.push_emit._dispatch"):
        dispatcher.dispatch(_ev(), eh, "attention")

    for record in caplog.records:
        msg = record.getMessage()
        assert endpoint not in msg
        assert "fcm.googleapis.com" not in msg


# ---------------------------------------------------------------------------
# 5xx → no prune
# ---------------------------------------------------------------------------


def test_500_does_not_prune(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=503)]

    dispatcher.dispatch(_ev(), eh, "attention")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["subscriptions"]) == 1


# ---------------------------------------------------------------------------
# 429 → backoff (Retry-After honored or default 60s)
# ---------------------------------------------------------------------------


def test_429_backoff_honors_retry_after(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [
        HttpResponse(status=429, headers={"retry-after": "30"}),
        HttpResponse(status=201),  # second call would dispatch
    ]

    dispatcher.dispatch(_ev("first"), eh, "attention")
    # Second dispatch within backoff window — should be skipped.
    dispatcher.dispatch(_ev("second"), eh, "attention")

    # Only ONE request reached the push service.
    assert len(http.requests) == 1


def test_429_default_60s_backoff_when_no_retry_after(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=429)]

    dispatcher.dispatch(_ev(), eh, "attention")

    # Backoff recorded — second dispatch within window skipped.
    http.replies = [HttpResponse(status=201)]
    dispatcher.dispatch(_ev("next"), eh, "attention")
    assert len(http.requests) == 1


def test_429_does_not_prune(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=429)]

    dispatcher.dispatch(_ev(), eh, "attention")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["subscriptions"]) == 1


# ---------------------------------------------------------------------------
# Transport exception privacy (Codex P1 round 1 + P2 round 2)
# ---------------------------------------------------------------------------


def test_transport_url_error_logs_only_hash_and_type(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    # The exception "reason" carries a sentinel string we
    # search for in caplog records — if it leaked, we'd find
    # it. urllib.error.URLError messages can include the URL
    # in real life; we use a sentinel to spot leakage.
    http.raise_with = urllib.error.URLError(
        "SENTINEL_URL_TOKEN_should_never_appear_in_logs"
    )

    with caplog.at_level(logging.DEBUG, logger="karasu.push_emit._dispatch"):
        dispatcher.dispatch(_ev(), eh, "attention")

    for record in caplog.records:
        msg = record.getMessage()
        assert "SENTINEL_URL_TOKEN" not in msg
        assert endpoint not in msg
        assert "fcm.googleapis.com" not in msg
    # Type IS logged.
    assert any(
        "URLError" in record.getMessage() for record in caplog.records
    )


def test_transport_exception_does_not_prune(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.raise_with = TimeoutError("network gone")

    dispatcher.dispatch(_ev(), eh, "attention")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["subscriptions"]) == 1


def test_invalid_endpoint_in_store_logs_only_hash_and_type(
    seeded_store: tuple[Path, str],
    vapid_keys: tuple[str, str],
    http: HttpRecorder,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Codex P1 round 1 (UI-12c code audit) + pin §11.6.16:
    a corrupted store entry whose ``endpoint`` is not a
    valid URL must NOT leak the raw URL through the
    ``ValueError`` raised by :func:`audience_for`. The
    dispatcher catches ``ValueError`` with the same hash +
    type-only privacy discipline as transport failures, and
    :mod:`._rate_limit` no longer uses ``logger.exception``
    (which would attach exc_info + traceback).

    The sentinel-bearing endpoint is injected by hand into
    the store (mirroring the threat model: hand-edited /
    attacker-supplied corruption). The dispatcher walks the
    store, finds it, calls ``audience_for`` → raises →
    caught."""
    path, _ = seeded_store
    # Inject an invalid-URL subscription with a sentinel.
    sentinel_endpoint = "SENTINEL_INVALID_URL_TOKEN_123_no_scheme"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["subscriptions"].append(
        {
            "endpoint": sentinel_endpoint,
            "endpoint_hash": "deadbeef" * 8,
            "keys": {"p256dh": _sample_p256dh(), "auth": _sample_auth()},
            "categories": ["attention"],
            "created_at": "2026-05-07T00:00:00Z",
            "updated_at": "2026-05-07T00:00:00Z",
        }
    )
    path.write_text(json.dumps(raw), encoding="utf-8")

    public, private = vapid_keys
    config = DispatcherConfig(
        store_path=path,
        private_key=load_private_key(private),
        public_key_b64u=public,
        subject="mailto:op@x.test",
    )
    disp = PushDispatcher(config, http_post=http)

    with caplog.at_level(logging.DEBUG, logger="karasu.push_emit._dispatch"):
        disp.dispatch(_ev(), "deadbeef" * 8, "attention")

    # The sentinel endpoint MUST NOT appear in any log line.
    for record in caplog.records:
        msg = record.getMessage()
        assert "SENTINEL_INVALID_URL_TOKEN" not in msg
        assert sentinel_endpoint not in msg
    # The hash IS logged (audit-only metadata).
    assert any("deadbeef" in r.getMessage() for r in caplog.records)
    # No POST attempted (audience_for raised).
    assert http.requests == []


def test_transport_exception_does_not_emit_bus_event() -> None:
    """The dispatcher itself emits no bus events — that's the
    rate-limit / classifier upstream concern. The 410/404
    prune also emits no bus event (pin §11.6.13). This test
    is structural: the dispatcher has no JsonlEventBus
    parameter, so a bus event is impossible by construction."""
    import inspect

    sig = inspect.signature(PushDispatcher.__init__)
    assert "bus" not in sig.parameters


# ---------------------------------------------------------------------------
# Subscription pruned mid-debounce
# ---------------------------------------------------------------------------


def test_dispatch_no_op_when_subscription_absent(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Operator unsubscribed during the debounce window —
    dispatcher must skip + log endpoint_hash only (no body
    encryption, no POST)."""
    path, endpoint = seeded_store
    eh = compute_endpoint_hash("https://other.test/never-subscribed")

    with caplog.at_level(logging.INFO, logger="karasu.push_emit._dispatch"):
        dispatcher.dispatch(_ev(), eh, "attention")

    assert http.requests == []
    relevant = [
        r for r in caplog.records
        if "pruned before dispatch" in r.getMessage()
    ]
    assert len(relevant) == 1


# ---------------------------------------------------------------------------
# Privacy negative-shape: body is encrypted; never the endpoint
# ---------------------------------------------------------------------------


def test_request_body_is_encrypted_ciphertext_not_endpoint(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=201)]

    dispatcher.dispatch(_ev(), eh, "attention")

    body = http.requests[0].body
    assert endpoint.encode("utf-8") not in body
    assert b"fcm.googleapis.com" not in body


def test_request_url_carries_raw_endpoint(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    """Pin §11.6.16 binding: the raw endpoint materialises ONLY
    as the outbound REQUEST TARGET URL. The test URL above
    asserts presence here (alongside body absence)."""
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)

    dispatcher.dispatch(_ev(), eh, "attention")

    assert http.requests[0].url == endpoint


# ---------------------------------------------------------------------------
# JWT cache reuse + audience binding
# ---------------------------------------------------------------------------


def test_jwt_cached_across_dispatches_to_same_origin(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    """Brief §10.3 + pin §11.6.15: JWT cached per origin.
    Two dispatches to the SAME origin reuse the JWT."""
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)
    http.replies = [HttpResponse(status=201), HttpResponse(status=201)]

    dispatcher.dispatch(_ev("a"), eh, "attention")
    dispatcher.dispatch(_ev("b"), eh, "attention")

    auth1 = http.requests[0].headers["Authorization"]
    auth2 = http.requests[1].headers["Authorization"]
    # The "t=" token (the JWT) should be byte-for-byte equal.
    assert auth1 == auth2


def test_jwt_audience_matches_endpoint_origin(
    dispatcher: PushDispatcher,
    http: HttpRecorder,
    seeded_store: tuple[Path, str],
) -> None:
    path, endpoint = seeded_store
    eh = compute_endpoint_hash(endpoint)

    dispatcher.dispatch(_ev(), eh, "attention")

    auth = http.requests[0].headers["Authorization"]
    jwt_part = auth[len("vapid t=") :].split(",")[0].strip()
    claims_b64 = jwt_part.split(".")[1]
    claims = json.loads(
        urlsafe_b64decode(claims_b64 + "=" * (-len(claims_b64) % 4))
    )
    assert claims["aud"] == "https://fcm.googleapis.com"
    assert claims["sub"] == "mailto:operator@localhost.invalid"


# ---------------------------------------------------------------------------
# §3-H payload shape (encrypted; we decrypt to verify)
# ---------------------------------------------------------------------------


def test_payload_carries_attention_title(
    seeded_store: tuple[Path, str],
    vapid_keys: tuple[str, str],
    http: HttpRecorder,
) -> None:
    """The payload body is encrypted, but we hold the UA
    private key (test fixture) so we can decrypt and verify
    the §3-H title contract."""
    # We need the UA private key to decrypt — but the
    # fixture's _sample_p256dh threw it away. Re-do with a
    # known UA keypair.
    from cryptography.hazmat.primitives.asymmetric import ec

    ua_priv = ec.generate_private_key(ec.SECP256R1())
    nums = ua_priv.public_key().public_numbers()
    p256dh_raw = (
        b"\x04"
        + nums.x.to_bytes(32, "big")
        + nums.y.to_bytes(32, "big")
    )
    from base64 import urlsafe_b64encode

    p256dh_b64 = urlsafe_b64encode(p256dh_raw).rstrip(b"=").decode("ascii")
    import os

    auth_raw = os.urandom(16)
    auth_b64 = urlsafe_b64encode(auth_raw).rstrip(b"=").decode("ascii")

    path, _old_endpoint = seeded_store
    new_endpoint = "https://fcm.googleapis.com/fcm/send/UA_TEST"
    append_subscription(
        path,
        subscription={
            "endpoint": new_endpoint,
            "keys": {"p256dh": p256dh_b64, "auth": auth_b64},
        },
        categories=["attention"],
    )

    public, private = vapid_keys
    config = DispatcherConfig(
        store_path=path,
        private_key=load_private_key(private),
        public_key_b64u=public,
        subject="mailto:op@x.test",
    )
    disp = PushDispatcher(config, http_post=http)
    http.replies = [HttpResponse(status=201)]

    eh = compute_endpoint_hash(new_endpoint)
    ev = _ev("evt-attention")
    disp.dispatch(ev, eh, "attention")

    body = http.requests[0].body
    plaintext = _decrypt_push_body(body, ua_priv, p256dh_raw, auth_raw)
    payload = json.loads(plaintext.decode("utf-8"))

    assert payload["title"] == "Karasu paused — operator review needed."
    assert payload["body"] == ""
    assert payload["icon"] == "/assets/icons/karasu-192.png"
    assert payload["badge"] == "/assets/icons/karasu-192.png"
    assert payload["tag"] == "karasu"
    assert payload["data"] == {
        "url": "/",
        "category": "attention",
        "event_id": "evt-attention",
    }
    assert payload["silent"] is False
    assert payload["requireInteraction"] is False


def _decrypt_push_body(
    body: bytes, ua_priv: Any, p256dh_raw: bytes, auth_raw: bytes
) -> bytes:
    """Receiver-side RFC 8291 reverse path. Used to verify
    payload contents without trusting the encryption module."""
    from cryptography.hazmat.primitives import hashes, hmac
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

    salt = body[:16]
    record_size = int.from_bytes(body[16:20], "big")
    idlen = body[20]
    assert record_size == 4096
    assert idlen == 65
    as_pub = body[21 : 21 + 65]
    ciphertext = body[21 + 65 :]

    as_pub_x = int.from_bytes(as_pub[1:33], "big")
    as_pub_y = int.from_bytes(as_pub[33:65], "big")
    as_pub_key = ec.EllipticCurvePublicNumbers(
        as_pub_x, as_pub_y, ec.SECP256R1()
    ).public_key()
    ecdh_secret = ua_priv.exchange(ec.ECDH(), as_pub_key)

    h = hmac.HMAC(auth_raw, hashes.SHA256())
    h.update(ecdh_secret)
    prk_key = h.finalize()

    key_info = b"WebPush: info\x00" + p256dh_raw + as_pub
    ikm = HKDFExpand(
        algorithm=hashes.SHA256(), length=32, info=key_info
    ).derive(prk_key)

    h2 = hmac.HMAC(salt, hashes.SHA256())
    h2.update(ikm)
    prk_aes = h2.finalize()

    cek = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=16,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(prk_aes)
    nonce = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=12,
        info=b"Content-Encoding: nonce\x00",
    ).derive(prk_aes)

    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded[-1] == 0x02
    return padded[:-1]


# ---------------------------------------------------------------------------
# Defaults match brief
# ---------------------------------------------------------------------------


def test_defaults_match_brief() -> None:
    assert DEFAULT_BACKOFF_SECONDS == 60.0
    assert DEFAULT_TTL_SECONDS == 60
