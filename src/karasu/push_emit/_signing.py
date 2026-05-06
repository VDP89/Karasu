"""VAPID JWT signing — RFC 8292 ES256.

Brief §3-C + pin §11.6.13. One of the THREE files allowed to
import :mod:`cryptography` (alongside :mod:`._keys` and
:mod:`._encryption`). Pinned by
``tests/test_push_emit_import_scope.py``.

The public surface:

  * :func:`load_private_key` — turn the b64url-no-pad scalar
    persisted in :mod:`karasu.ui.push_store` back into a
    cryptography :class:`ec.EllipticCurvePrivateKey`.
  * :func:`sign_vapid_jwt` — produce a fully serialised JWT
    string (``header.claims.signature``) suitable for the
    ``Authorization: vapid t=<JWT>, k=<vapid_pub_b64u>`` header.

The signature conversion from DER (what ``cryptography``
returns) to raw ``r||s`` (64 bytes) is the easily-missed step
in VAPID — push services reject DER. Pinned by
``test_signature_is_64_byte_raw_rs``.

Caching of JWTs is the caller's responsibility (brief §3-C
in-memory cache per ``(origin, exp_window)`` tuple). This
module is stateless.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


_RAW_SCALAR_LEN = 32

# Brief §10.3 binding — JWT exp window default 12 h. RFC 8292
# caps at 24 h. The caller can override per-call but the
# emitter never reaches above this default.
DEFAULT_EXP_SECONDS = 12 * 60 * 60


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def load_private_key(private_b64u: str) -> ec.EllipticCurvePrivateKey:
    """Reconstruct an ECDSA P-256 private key from its
    b64url-no-pad raw 32-byte scalar (the format
    :func:`generate_vapid_keypair` writes to the store).

    Raises :class:`ValueError` on the wrong byte length so a
    caller cannot accidentally feed a public key in here.
    """
    raw = _b64u_decode(private_b64u)
    if len(raw) != _RAW_SCALAR_LEN:
        raise ValueError(
            f"private VAPID scalar must be {_RAW_SCALAR_LEN} bytes; "
            f"got {len(raw)}"
        )
    private_int = int.from_bytes(raw, "big")
    return ec.derive_private_key(private_int, ec.SECP256R1())


def audience_for(endpoint: str) -> str:
    """Return the VAPID ``aud`` claim for a Web Push endpoint:
    the origin (scheme + host[:port]) of the endpoint URL.

    Push services are origin-bound — a JWT signed for
    ``https://fcm.googleapis.com`` cannot deliver to
    ``https://updates.push.services.mozilla.com``. The caller
    caches per audience; this helper centralises the parse.
    """
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"endpoint is not a valid URL: {endpoint!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def sign_vapid_jwt(
    *,
    audience: str,
    subject: str,
    private_key: ec.EllipticCurvePrivateKey,
    exp_seconds: int = DEFAULT_EXP_SECONDS,
    now: float | None = None,
) -> str:
    """Produce a serialised RFC 8292 VAPID JWT.

    Args:
      audience      Push service origin (``aud`` claim). Use
                    :func:`audience_for` to derive from a
                    subscription endpoint.
      subject       ``mailto:`` URI (or ``https:`` URL per
                    RFC 8292 §2.2). Defaults are the caller's
                    responsibility — empty or malformed
                    subjects are rejected by some push services
                    (notably Mozilla autopush).
      private_key   The ``cryptography`` private key from
                    :func:`load_private_key`.
      exp_seconds   Window relative to ``now``. RFC 8292 caps
                    at 24h; the brief default is 12h.
      now           Unix timestamp seconds. Defaults to
                    :func:`time.time`. Tests inject a fixed
                    value for deterministic ``exp`` claims.

    Returns:
      The ``"<header>.<claims>.<signature>"`` JWT string,
      with all three parts b64url-no-pad. The signature is
      converted from DER (what ``cryptography`` returns) to
      raw ``r||s`` (64 bytes) per RFC 8292.
    """
    if now is None:
        now = time.time()
    exp = int(now) + int(exp_seconds)

    header: dict[str, Any] = {"alg": "ES256", "typ": "JWT"}
    claims: dict[str, Any] = {"aud": audience, "exp": exp, "sub": subject}

    header_b64 = _b64u_encode(_compact_json(header))
    claims_b64 = _b64u_encode(_compact_json(claims))
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

    der_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{header_b64}.{claims_b64}.{_b64u_encode(raw_sig)}"


def _compact_json(payload: dict[str, Any]) -> bytes:
    """JSON encoder with no whitespace + sorted keys deterministic
    over Python invocations.

    JWT bodies are compared byte-for-byte at signing — any
    whitespace drift between Python releases would cascade into
    a different b64u string and a different signature.
    """
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
