"""RFC 8291 aes128gcm Web Push payload encryption.

Brief §3-C payload encryption subsection. One of the THREE
files allowed to import :mod:`cryptography`. Pinned by
``tests/test_push_emit_import_scope.py``.

Web Push payloads are end-to-end encrypted: only the user
agent (the browser holding the matching ``p256dh`` private key
+ ``auth`` secret) can decrypt. The push service relays
ciphertext blindly. RFC 8291 layered on RFC 8188 specifies the
exact key-derivation + framing.

The brief §3-C lists 12 numbered steps with three named
HKDF intermediates (``PRK_key``, ``IKM``, ``PRK_aes``) so the
implementation maps directly to the RFC and Codex auditors can
spot deviation.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand


# Brief §3-C input length pins.
_UA_PUB_LEN = 65        # uncompressed P-256 point: 0x04 || X(32) || Y(32)
_AUTH_LEN = 16          # subscriber auth secret per RFC 8291 §2
_SALT_LEN = 16          # RFC 8188 §2.1
_RECORD_SIZE = 4096     # RFC 8188 §2.1 binary header field
_AS_PUB_LEN = 65        # application-server public key, same shape as UA pub
_GCM_TAG_LEN = 16       # AES-GCM authentication tag

# Body framing overhead per RFC 8188 §2.1:
#   salt(16) + record_size(4) + idlen(1) + keyid(65) = 86 bytes
# Plus 16-byte GCM tag, plus 1-byte 0x02 delimiter on plaintext.
# Max ciphertext fits in record_size 4096 → max plaintext is
# 4096 - 86 - 16 - 1 = 3993 bytes.
MAX_PLAINTEXT_BYTES = _RECORD_SIZE - 86 - _GCM_TAG_LEN - 1


def encrypt_payload(
    *,
    p256dh: bytes,
    auth: bytes,
    plaintext: bytes,
) -> bytes:
    """Encrypt ``plaintext`` for a Web Push subscription.

    Args:
      p256dh    65-byte uncompressed UA public point. The
                subscription's ``keys.p256dh`` decoded from
                base64url.
      auth      16-byte UA auth secret. The subscription's
                ``keys.auth`` decoded from base64url.
      plaintext UTF-8 JSON body to encrypt (the push payload
                per brief §3-H). Max
                :data:`MAX_PLAINTEXT_BYTES` bytes after the
                0x02 delimiter is appended.

    Returns:
      The full RFC 8188 binary record body ready to POST as the
      request body with ``Content-Encoding: aes128gcm`` and
      ``Content-Length`` set to ``len(body)``.

    Raises:
      ValueError if ``p256dh``, ``auth``, or the encrypted
      payload size are out of contract.
    """
    if len(p256dh) != _UA_PUB_LEN or p256dh[0] != 0x04:
        raise ValueError(
            "p256dh must be a 65-byte uncompressed point starting with 0x04"
        )
    if len(auth) != _AUTH_LEN:
        raise ValueError(f"auth must be {_AUTH_LEN} bytes; got {len(auth)}")
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise ValueError(
            f"plaintext exceeds Web Push 4096-byte record cap "
            f"(max {MAX_PLAINTEXT_BYTES} bytes; got {len(plaintext)})"
        )

    # Step 1 — generate one-time application-server keypair.
    as_priv = ec.generate_private_key(ec.SECP256R1())
    as_pub_numbers = as_priv.public_key().public_numbers()
    as_pub = (
        b"\x04"
        + as_pub_numbers.x.to_bytes(32, "big")
        + as_pub_numbers.y.to_bytes(32, "big")
    )

    # Step 2 — ECDH shared secret with the UA public key.
    ua_pub_x = int.from_bytes(p256dh[1:33], "big")
    ua_pub_y = int.from_bytes(p256dh[33:65], "big")
    ua_pub_key = ec.EllipticCurvePublicNumbers(
        ua_pub_x, ua_pub_y, ec.SECP256R1()
    ).public_key()
    ecdh_secret = as_priv.exchange(ec.ECDH(), ua_pub_key)

    # Step 3 — PRK_key = HMAC-SHA256(auth_secret, ecdh_secret).
    # RFC 8291 §3.3: a single HMAC, NOT full HKDF (no separate
    # extract step here). The auth secret is the HMAC key.
    prk_key = _hmac_sha256(key=auth, msg=ecdh_secret)

    # Step 4 — key_info per RFC 8291 §3.4.
    key_info = b"WebPush: info\x00" + p256dh + as_pub

    # Step 5 — IKM = HKDF-Expand(PRK_key, key_info, 32).
    ikm = HKDFExpand(
        algorithm=hashes.SHA256(), length=32, info=key_info
    ).derive(prk_key)

    # Step 6 — fresh per-message salt.
    salt = os.urandom(_SALT_LEN)

    # Step 7 — PRK_aes = HKDF-Extract(salt, IKM)
    # = HMAC-SHA256(salt, IKM) for SHA-256.
    prk_aes = _hmac_sha256(key=salt, msg=ikm)

    # Step 8 — content encryption key.
    cek = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=16,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(prk_aes)

    # Step 9 — content nonce.
    nonce = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=12,
        info=b"Content-Encoding: nonce\x00",
    ).derive(prk_aes)

    # Step 10 — pad with the 0x02 delimiter (RFC 8188 §2.1).
    # No additional padding: smallest ciphertext, no length leak.
    padded = plaintext + b"\x02"

    # Step 11 — AES-128-GCM seal.
    ciphertext = AESGCM(cek).encrypt(nonce, padded, None)

    if len(ciphertext) > _RECORD_SIZE - 86:
        # Defence-in-depth: the plaintext check above should
        # already have caught this, but the encrypted body
        # MUST fit in one record_size frame.
        raise ValueError(
            f"ciphertext {len(ciphertext)} bytes exceeds record "
            f"capacity ({_RECORD_SIZE - 86})"
        )

    # Step 12 — RFC 8188 §2.1 binary header + ciphertext.
    body = (
        salt
        + _RECORD_SIZE.to_bytes(4, "big")
        + (_AS_PUB_LEN).to_bytes(1, "big")
        + as_pub
        + ciphertext
    )
    return body


def _hmac_sha256(*, key: bytes, msg: bytes) -> bytes:
    """One-shot HMAC-SHA256. Wrapped because the
    ``cryptography`` HMAC API is two-step (init / update /
    finalize) and the encryption flow uses HMAC-as-extract
    in two places."""
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(msg)
    return h.finalize()
