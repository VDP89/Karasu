"""VAPID keypair generation + first-start bootstrap.

Brief §3-F + pin §11.6.13 + forward-carry pin (b).

UI-12c is the FIRST proactive outbound HTTP surface in Karasu.
The Web Push services (FCM / APNs / Mozilla autopush) require a
VAPID keypair (RFC 8292) as the application-server identity.
This module:

  1. Generates fresh ECDSA P-256 keypairs via :mod:`cryptography`.
  2. Writes them to the push store under the same atomic-write
     discipline UI-12b shipped (mode 0600 + tmp+rename + the
     in-process Lock + the cross-process flock from UI-12c §3-G).
  3. Bootstraps on first ``karasu watch`` start when the store
     has no ``vapid`` section, leaves an existing keypair
     untouched on subsequent starts (pin §10.4 — rotation is
     operator-driven, never automatic).

This is one of the THREE files allowed to import
``cryptography`` (alongside :mod:`._signing` and
:mod:`._encryption`). The binding is enforced by
``tests/test_push_emit_import_scope.py``.

Pin §11.6.16 binding: NEVER log key material. The success log
line is a flat ``"generated VAPID keypair"`` string — no
lengths, no fragments, no audit metadata that could fingerprint
the keys.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

from karasu.ui.push_store import (
    _read_or_empty_store,
    seed_vapid,
)

_log = logging.getLogger(__name__)


# Brief §3-F binding lengths:
#
#   public  uncompressed P-256 point: 0x04 || X(32) || Y(32) = 65 bytes
#                                     b64url no padding = 87 chars
#   private 32-byte raw scalar      = 43 chars
#
# Note: the brief §3-F descriptive comment cites "86 chars" for
# the public key — that is a typo (Codex did not catch it during
# the 4-round audit). The binding contract is the byte length
# (65 bytes uncompressed), not the b64url char count. The
# math: ceil(65 * 4 / 3) = 87 chars no-pad. Pinned here so the
# constant cannot drift back to the typo in a future refactor.
_PUBLIC_RAW_LEN = 65
_PRIVATE_RAW_LEN = 32
PUBLIC_B64U_LEN = 87
PRIVATE_B64U_LEN = 43


def _b64u_encode(raw: bytes) -> str:
    """Base64url-encode without trailing padding (RFC 7515 §2)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_vapid_keypair() -> tuple[str, str]:
    """Generate a fresh ECDSA P-256 keypair for VAPID signing.

    Returns ``(public_b64u, private_b64u)``:

      * ``public_b64u``  — 86-char base64url no padding;
        decodes to the 65-byte uncompressed point ``0x04 || X || Y``.
      * ``private_b64u`` — 43-char base64url no padding;
        decodes to the 32-byte raw scalar.

    The keypair is freshly random per call. Callers are expected
    to persist it via :func:`seed_vapid` — the function itself
    holds NO state.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    public_numbers = public_key.public_numbers()
    public_raw = (
        b"\x04"
        + public_numbers.x.to_bytes(32, "big")
        + public_numbers.y.to_bytes(32, "big")
    )
    assert len(public_raw) == _PUBLIC_RAW_LEN

    private_int = private_key.private_numbers().private_value
    private_raw = private_int.to_bytes(_PRIVATE_RAW_LEN, "big")

    return _b64u_encode(public_raw), _b64u_encode(private_raw)


def bootstrap_if_missing(store_path: Path) -> bool:
    """Generate + persist a VAPID keypair iff the store lacks one.

    Brief §3-F idempotency contract:

      * Store absent OR the store object has no ``vapid`` section
        → generate, write, return ``True``.
      * Store has a ``vapid`` section with both ``public`` AND
        ``private`` as non-empty strings → no-op, return ``False``.
      * Store has a partial ``vapid`` (one of the keys missing /
        wrong type / empty) → REGENERATE both keys. The
        operator's manual seed is "complete or considered
        corrupt"; no half-state is preserved (brief §3-I keys
        test surface).

    Pin §11.6.16: the success log line is the flat string
    ``"generated VAPID keypair"`` — no lengths, no fragments,
    no public-key-as-fingerprint either.

    Raises :class:`PushStoreError` from
    :func:`_read_or_empty_store` on a malformed store. The
    ``karasu watch`` controller is expected to log generically
    and exit non-zero (NOT an HTTP 500 contract — bootstrap
    runs at startup, not under request scope).
    """
    raw = _read_or_empty_store(store_path)
    if _has_complete_vapid(raw):
        return False

    public_b64, private_b64 = generate_vapid_keypair()
    seed_vapid(store_path, public=public_b64, private=private_b64)
    _log.info("generated VAPID keypair")
    return True


def _has_complete_vapid(raw: dict) -> bool:
    """Return True iff ``raw`` has ``vapid.public`` AND
    ``vapid.private`` as non-empty strings."""
    vapid = raw.get("vapid")
    if not isinstance(vapid, dict):
        return False
    public = vapid.get("public")
    private = vapid.get("private")
    return (
        isinstance(public, str)
        and bool(public)
        and isinstance(private, str)
        and bool(private)
    )
