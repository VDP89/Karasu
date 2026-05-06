"""VAPID JWT signing tests — RFC 8292 ES256.

Brief §3-C + pin §11.6.13.

The signature is verified against the public key end-to-end so
the test does NOT trust ``cryptography`` to round-trip; it
asserts the produced JWT is actually verifiable per RFC.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from karasu.push_emit._keys import generate_vapid_keypair
from karasu.push_emit._signing import (
    DEFAULT_EXP_SECONDS,
    audience_for,
    load_private_key,
    sign_vapid_jwt,
)


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@pytest.fixture
def vapid_pair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    public_b64, private_b64 = generate_vapid_keypair()
    return load_private_key(private_b64), public_b64


# ---------------------------------------------------------------------------
# load_private_key
# ---------------------------------------------------------------------------


def test_load_private_key_round_trip() -> None:
    _, private_b64 = generate_vapid_keypair()
    key = load_private_key(private_b64)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert key.curve.name == "secp256r1"


def test_load_private_key_rejects_wrong_length() -> None:
    # 16 bytes b64u-encoded; not a valid 32-byte scalar.
    bad = base64.urlsafe_b64encode(b"\x00" * 16).rstrip(b"=").decode()
    with pytest.raises(ValueError, match="32 bytes"):
        load_private_key(bad)


# ---------------------------------------------------------------------------
# audience_for
# ---------------------------------------------------------------------------


def test_audience_for_fcm() -> None:
    assert (
        audience_for("https://fcm.googleapis.com/fcm/send/AAA-BBB")
        == "https://fcm.googleapis.com"
    )


def test_audience_for_mozilla() -> None:
    assert (
        audience_for(
            "https://updates.push.services.mozilla.com/wpush/v1/abc"
        )
        == "https://updates.push.services.mozilla.com"
    )


def test_audience_for_includes_port_when_present() -> None:
    assert (
        audience_for("https://example.test:8443/push/abc")
        == "https://example.test:8443"
    )


def test_audience_for_rejects_relative() -> None:
    with pytest.raises(ValueError):
        audience_for("/push/abc")


# ---------------------------------------------------------------------------
# sign_vapid_jwt — JWT shape + verifiable signature
# ---------------------------------------------------------------------------


def test_jwt_has_three_b64u_parts(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    private_key, _ = vapid_pair
    jwt = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:operator@localhost.invalid",
        private_key=private_key,
    )
    parts = jwt.split(".")
    assert len(parts) == 3
    for part in parts:
        # b64u-no-pad: only b64url alphabet, no padding.
        assert "=" not in part
        _b64u_decode(part)  # should decode cleanly


def test_jwt_header_is_es256(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    private_key, _ = vapid_pair
    jwt = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:op@x.test",
        private_key=private_key,
    )
    header = json.loads(_b64u_decode(jwt.split(".")[0]))
    assert header == {"alg": "ES256", "typ": "JWT"}


def test_jwt_claims_carry_aud_exp_sub(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    private_key, _ = vapid_pair
    jwt = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:op@x.test",
        private_key=private_key,
        now=1_700_000_000,
    )
    claims = json.loads(_b64u_decode(jwt.split(".")[1]))
    assert claims == {
        "aud": "https://fcm.googleapis.com",
        "exp": 1_700_000_000 + DEFAULT_EXP_SECONDS,
        "sub": "mailto:op@x.test",
    }


def test_jwt_default_exp_is_12_hours(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    """Brief §10.3: default exp window is 12 h."""
    assert DEFAULT_EXP_SECONDS == 12 * 60 * 60


def test_signature_is_64_byte_raw_rs(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    """RFC 8292 §3: VAPID signature is raw ``r || s``,
    NOT the DER encoding ``cryptography.sign`` returns natively.
    Push services reject DER."""
    private_key, _ = vapid_pair
    jwt = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:op@x.test",
        private_key=private_key,
    )
    sig_raw = _b64u_decode(jwt.split(".")[2])
    assert len(sig_raw) == 64


def test_signature_verifies_against_public_key(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    """Round-trip via the public key — proves the JWT is
    actually signed correctly per ES256."""
    private_key, public_b64 = vapid_pair

    jwt = sign_vapid_jwt(
        audience="https://example.test",
        subject="mailto:op@x.test",
        private_key=private_key,
    )

    header_b64, claims_b64, sig_b64 = jwt.split(".")
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    sig_raw = _b64u_decode(sig_b64)

    # raw r||s → DER for cryptography.verify
    r = int.from_bytes(sig_raw[:32], "big")
    s = int.from_bytes(sig_raw[32:], "big")
    der_sig = encode_dss_signature(r, s)

    # Reconstruct public key from b64u uncompressed point
    pub_raw = _b64u_decode(public_b64)
    assert pub_raw[0] == 0x04
    x = int.from_bytes(pub_raw[1:33], "big")
    y = int.from_bytes(pub_raw[33:65], "big")
    public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
    public_key = public_numbers.public_key()

    # Should not raise.
    public_key.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA256()))


def test_jwt_two_distinct_signs_differ_in_signature(
    vapid_pair: tuple[ec.EllipticCurvePrivateKey, str]
) -> None:
    """ECDSA is randomised — two signs of the same payload
    produce DIFFERENT signatures. Header + claims stay equal
    under fixed ``now``."""
    private_key, _ = vapid_pair
    jwt1 = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:op@x.test",
        private_key=private_key,
        now=1_700_000_000,
    )
    jwt2 = sign_vapid_jwt(
        audience="https://fcm.googleapis.com",
        subject="mailto:op@x.test",
        private_key=private_key,
        now=1_700_000_000,
    )
    h1, c1, s1 = jwt1.split(".")
    h2, c2, s2 = jwt2.split(".")
    assert h1 == h2
    assert c1 == c2
    assert s1 != s2  # randomised signature
