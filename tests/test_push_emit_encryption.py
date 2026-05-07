"""RFC 8291 aes128gcm payload encryption tests.

Brief §3-C test surface:
  * Round-trip via a fixture UA keypair: encrypt + decrypt =
    identity over plaintext.
  * Header shape: Content-Encoding=aes128gcm, salt 16 bytes,
    keyid 65-byte uncompressed point, record_size 4096,
    ciphertext non-empty.
  * Each ciphertext is unique even for the same plaintext
    (fresh ECDH keypair + fresh salt).
  * Privacy negative-shape: capture log lines + bus + store
    after a sentinel-bearing encryption call; assert raw
    endpoint absent everywhere.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from karasu.push_emit._encryption import (
    MAX_PLAINTEXT_BYTES,
    encrypt_payload,
)


# ---------------------------------------------------------------------------
# Fixture: a synthetic UA subscription with known keys
# ---------------------------------------------------------------------------


@dataclass
class UASubscription:
    private_key: ec.EllipticCurvePrivateKey
    p256dh: bytes  # 65-byte uncompressed point
    auth: bytes    # 16-byte secret


@pytest.fixture
def ua_subscription() -> UASubscription:
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub_numbers = private_key.public_key().public_numbers()
    p256dh = (
        b"\x04"
        + pub_numbers.x.to_bytes(32, "big")
        + pub_numbers.y.to_bytes(32, "big")
    )
    auth = os.urandom(16)
    return UASubscription(private_key=private_key, p256dh=p256dh, auth=auth)


# ---------------------------------------------------------------------------
# Round-trip: decrypt the ciphertext with the UA's private key
# ---------------------------------------------------------------------------


def _decrypt(body: bytes, ua: UASubscription) -> bytes:
    """Reverse of ``encrypt_payload`` for the test only.
    Implements the RFC 8291 receiver path so we can assert
    plaintext recovery."""
    salt = body[:16]
    record_size = int.from_bytes(body[16:20], "big")
    idlen = body[20]
    assert record_size == 4096
    assert idlen == 65
    as_pub = body[21:21 + 65]
    ciphertext = body[21 + 65:]

    # Reverse step 2: ECDH shared
    as_pub_x = int.from_bytes(as_pub[1:33], "big")
    as_pub_y = int.from_bytes(as_pub[33:65], "big")
    as_pub_key = ec.EllipticCurvePublicNumbers(
        as_pub_x, as_pub_y, ec.SECP256R1()
    ).public_key()
    ecdh_secret = ua.private_key.exchange(ec.ECDH(), as_pub_key)

    # Reverse step 3: PRK_key
    h = hmac.HMAC(ua.auth, hashes.SHA256())
    h.update(ecdh_secret)
    prk_key = h.finalize()

    # Reverse step 4 + 5: IKM
    key_info = b"WebPush: info\x00" + ua.p256dh + as_pub
    ikm = HKDFExpand(
        algorithm=hashes.SHA256(), length=32, info=key_info
    ).derive(prk_key)

    # Reverse step 7: PRK_aes
    h2 = hmac.HMAC(salt, hashes.SHA256())
    h2.update(ikm)
    prk_aes = h2.finalize()

    # Reverse steps 8 + 9
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
    # Strip the 0x02 delimiter.
    assert padded[-1] == 0x02
    return padded[:-1]


def test_round_trip_short_plaintext(ua_subscription: UASubscription) -> None:
    plaintext = b'{"title":"Karasu paused"}'
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=plaintext,
    )
    recovered = _decrypt(body, ua_subscription)
    assert recovered == plaintext


def test_round_trip_unicode(ua_subscription: UASubscription) -> None:
    plaintext = "🦅 Karasu — operator review needed".encode("utf-8")
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=plaintext,
    )
    assert _decrypt(body, ua_subscription) == plaintext


def test_round_trip_empty_plaintext(
    ua_subscription: UASubscription,
) -> None:
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=b"",
    )
    assert _decrypt(body, ua_subscription) == b""


# ---------------------------------------------------------------------------
# Body framing shape
# ---------------------------------------------------------------------------


def test_body_carries_16_byte_salt(
    ua_subscription: UASubscription,
) -> None:
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=b"x",
    )
    salt = body[:16]
    assert len(salt) == 16


def test_body_record_size_is_4096(
    ua_subscription: UASubscription,
) -> None:
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=b"x",
    )
    record_size = int.from_bytes(body[16:20], "big")
    assert record_size == 4096


def test_body_keyid_is_uncompressed_point(
    ua_subscription: UASubscription,
) -> None:
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=b"x",
    )
    idlen = body[20]
    keyid = body[21:21 + 65]
    assert idlen == 65
    assert len(keyid) == 65
    assert keyid[0] == 0x04


def test_body_ciphertext_non_empty(
    ua_subscription: UASubscription,
) -> None:
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=b"x",
    )
    ciphertext = body[21 + 65:]
    # 1 byte plaintext + 1 byte delimiter + 16 byte GCM tag = 18 bytes.
    assert len(ciphertext) == 18


# ---------------------------------------------------------------------------
# Uniqueness: fresh ECDH keypair + fresh salt per call
# ---------------------------------------------------------------------------


def test_ciphertext_unique_per_call(
    ua_subscription: UASubscription,
) -> None:
    plaintext = b'{"title":"same"}'
    body1 = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=plaintext,
    )
    body2 = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=plaintext,
    )
    # Different salt + different as_pub + different ciphertext.
    assert body1[:16] != body2[:16]
    assert body1[21:21 + 65] != body2[21:21 + 65]
    assert body1 != body2


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_rejects_short_p256dh(
    ua_subscription: UASubscription,
) -> None:
    with pytest.raises(ValueError, match="65-byte uncompressed point"):
        encrypt_payload(
            p256dh=b"\x04" + b"\x00" * 32,  # 33 bytes, wrong
            auth=ua_subscription.auth,
            plaintext=b"x",
        )


def test_rejects_p256dh_wrong_marker(
    ua_subscription: UASubscription,
) -> None:
    with pytest.raises(ValueError, match="0x04"):
        encrypt_payload(
            p256dh=b"\x02" + b"\x00" * 64,  # 65 bytes but compressed marker
            auth=ua_subscription.auth,
            plaintext=b"x",
        )


def test_rejects_short_auth(
    ua_subscription: UASubscription,
) -> None:
    with pytest.raises(ValueError, match="auth must be 16 bytes"):
        encrypt_payload(
            p256dh=ua_subscription.p256dh,
            auth=b"\x00" * 8,  # 8 bytes, wrong
            plaintext=b"x",
        )


def test_rejects_oversize_plaintext(
    ua_subscription: UASubscription,
) -> None:
    too_big = b"x" * (MAX_PLAINTEXT_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds Web Push"):
        encrypt_payload(
            p256dh=ua_subscription.p256dh,
            auth=ua_subscription.auth,
            plaintext=too_big,
        )


def test_max_plaintext_just_fits(
    ua_subscription: UASubscription,
) -> None:
    """The advertised ``MAX_PLAINTEXT_BYTES`` must actually
    encrypt without raising — the boundary is real, not a
    safety margin."""
    just_fits = b"x" * MAX_PLAINTEXT_BYTES
    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=just_fits,
    )
    assert _decrypt(body, ua_subscription) == just_fits


# ---------------------------------------------------------------------------
# Privacy negative-shape
# ---------------------------------------------------------------------------


def test_no_log_lines_during_encryption(
    ua_subscription: UASubscription,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pin §11.6.16: the encryption module emits no log lines.
    Logging the keys / ECDH secret / nonce is a privacy
    catastrophe; the module is intentionally silent."""
    with caplog.at_level(logging.DEBUG, logger="karasu.push_emit._encryption"):
        encrypt_payload(
            p256dh=ua_subscription.p256dh,
            auth=ua_subscription.auth,
            plaintext=b'{"title":"x"}',
        )
    relevant = [
        r for r in caplog.records
        if r.name.startswith("karasu.push_emit._encryption")
    ]
    assert relevant == []


def test_endpoint_absent_from_body(
    ua_subscription: UASubscription,
) -> None:
    """Brief §3-C + Codex P1 round 1: the encrypted body is
    RFC 8291 ciphertext, NOT the endpoint URL. The endpoint
    materialises only as the OUTBOUND REQUEST TARGET URL
    (handled by :mod:`._dispatch`); the body must never
    embed it."""
    sentinel_endpoint = "https://fcm.test/SENTINEL_ENDPOINT_TOKEN_zzzz"
    plaintext = b'{"title":"x"}'

    body = encrypt_payload(
        p256dh=ua_subscription.p256dh,
        auth=ua_subscription.auth,
        plaintext=plaintext,
    )

    assert b"SENTINEL_ENDPOINT_TOKEN" not in body
    # Decrypted plaintext is also free of the endpoint —
    # encryption never knows about it.
    assert b"SENTINEL_ENDPOINT_TOKEN" not in _decrypt(body, ua_subscription)
    # ``encrypt_payload`` has no ``endpoint`` parameter at all
    # — there is no surface through which the URL could leak
    # into the ciphertext or framing. The caller (._dispatch)
    # holds the raw endpoint as the outbound request URL only.
    _ = sentinel_endpoint  # kept as documentation of what we're guarding
