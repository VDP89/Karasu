"""Auth primitives for UI-13 (remote operator surface).

Brief: docs/ui/ui-13-design-brief.md (PR #108, merged
ad003db 2026-05-08).

Covers:

  * Credentials store (karasu-auth.json) load + verify + bootstrap
    + fail-closed startup contract (§3-B).
  * Session signed-cookie sign + verify with constant-time
    HMAC compare + 60s clock-skew margin (§3-C + §3.5 +
    pin §11.6.18 constant-time discipline).
  * CSRF signed double-submit cookie shape:
    `nonce.HMAC-SHA256(secret, "csrf:"+nonce+"|user:"+user+
    "|gen:"+gen)` + strict Origin/Referer check (§3-F).
  * Trusted-client-IP three-layer derivation (§3-G + pin
    §11.6.9): proxy overwrite (deploy-runbook.md responsibility),
    right-to-left trusted-hop walk, untrusted-peer guard.
  * Rate-limit (per-derived-IP + per-credentials, in-memory
    restart-cleared, with localhost bypass post-derivation).
  * Auth middleware + anonymous path perimeter (§3-D).

Pin §11.6.19 carry-forward: this module uses ONLY stdlib
(`hashlib`, `hmac`, `secrets`, `socket`, `urllib`, `json`,
`base64`, `time`, `re`). The cryptography import scope from
UI-12 §11.6.13 is NOT extended.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# scrypt parameters (brief §3-B binding)
# ---------------------------------------------------------------------------

SCRYPT_N = 16384       # 2^14, ≈250ms on commodity 2024 VPS
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_LEN = 16
SCRYPT_KEY_LEN = 32

# brief §3-C session signing secret length
SESSION_SECRET_LEN = 32

# brief §3-G localhost addresses. Two sets:
#   _LOCALHOST_IPS — IP literals only. Used by
#     `is_loopback_ip` for rate-limit + derive_client_ip
#     bypass checks (where the input is always a parsed IP,
#     never a hostname).
#   _LOCALHOST_HOSTNAMES — names that resolve loopback by
#     convention. Used by `is_loopback_bind` alongside the
#     IP set.
_LOCALHOST_V4_PREFIX = "127."
_LOCALHOST_IPS = frozenset({"127.0.0.1", "::1"})
_LOCALHOST_HOSTNAMES = frozenset({"localhost"})

# Hash format prefix per §3-B
_SCRYPT_PREFIX = "scrypt$"

# Sentinel returned by derive_client_ip when peer is untrusted
# but presents a forwarded chain (untrusted-peer guard, §3-G
# Codex round 3 P1 binding).
UNTRUSTED_FORWARDED = object()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuthCredentialsError(Exception):
    """Raised when karasu-auth.json is absent / malformed /
    wrong-mode / partial. Mirrors UI-12c PushStoreError shape;
    the cmd_ui startup catches and exits 2 with a generic
    stderr message per §3-B fail-closed contract."""


class AuthSessionError(Exception):
    """Raised on session cookie parse / verify failures. The
    middleware catches and treats the request as
    unauthenticated; the exception type is logged at DEBUG
    only (no payload material)."""


# ---------------------------------------------------------------------------
# Credentials store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthCredentials:
    """Loaded credentials. The object is frozen so callers
    cannot accidentally mutate the in-memory copy; rotation
    requires a fresh load via :func:`load_credentials`."""

    username: str
    password_hash: str          # "scrypt$N=..$r=..$p=..$<salt_b64u>$<hash_b64u>"
    session_signing_secret: bytes  # 32 raw bytes
    credentials_generation: int


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def load_credentials(path: Path) -> AuthCredentials:
    """Load + validate the auth credentials file.

    Per §3-B fail-closed startup contract:
      * absent file              → AuthCredentialsError
      * mode looser than 0600    → AuthCredentialsError (POSIX;
                                    Windows advisory-only with
                                    a loud-stderr warning per
                                    UI-12b shape)
      * malformed JSON           → AuthCredentialsError
      * non-object root          → AuthCredentialsError
      * missing / wrong-shape
        username / password_hash /
        session_signing_secret /
        credentials_generation   → AuthCredentialsError

    Error messages are GENERIC — no field names, no path
    fragments. The caller logs a single fixed line and exits.
    """
    if not path.exists():
        raise AuthCredentialsError("credentials file is absent")
    _enforce_mode_0600(path)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthCredentialsError("credentials file unreadable") from exc
    except UnicodeDecodeError as exc:
        raise AuthCredentialsError("credentials file not utf-8") from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuthCredentialsError("credentials file malformed json") from exc

    if not isinstance(raw, dict):
        raise AuthCredentialsError("credentials root must be json object")

    username = raw.get("username")
    if not isinstance(username, str) or not username:
        raise AuthCredentialsError("username missing or empty")

    password_hash = raw.get("password_hash")
    if not isinstance(password_hash, str) or not password_hash.startswith(
        _SCRYPT_PREFIX
    ):
        raise AuthCredentialsError("password_hash malformed")
    # Codex P1 round 1 audit binding 2026-05-08: validate the
    # canonical scrypt shape at startup so a corrupted /
    # operator-edited file with N=2^30 cannot DoS the
    # listener through a single login attempt. Brief §3-B
    # fail-closed: refuse to bind if the hash drifts from the
    # pinned (N=16384, r=8, p=1, 16-byte salt, 32-byte key).
    _validate_password_hash_shape(password_hash)

    secret_b64 = raw.get("session_signing_secret")
    if not isinstance(secret_b64, str) or not secret_b64:
        raise AuthCredentialsError("session_signing_secret missing")
    try:
        secret = _b64u_decode(secret_b64)
    except Exception:  # noqa: BLE001
        raise AuthCredentialsError("session_signing_secret not b64u")
    if len(secret) < SESSION_SECRET_LEN:
        raise AuthCredentialsError("session_signing_secret too short")

    gen = raw.get("credentials_generation")
    if not isinstance(gen, int) or gen < 0:
        raise AuthCredentialsError("credentials_generation invalid")

    return AuthCredentials(
        username=username,
        password_hash=password_hash,
        session_signing_secret=secret,
        credentials_generation=gen,
    )


def _enforce_mode_0600(path: Path) -> None:
    """POSIX: refuse mode looser than 0600. Windows:
    advisory loud-stderr warning per UI-12b push_store
    shape (Codex P2 round 1 audit binding 2026-05-08).
    Startup still proceeds because Windows file-mode
    semantics do not map cleanly to POSIX 0600; the
    operator is responsible for NTFS ACLs restricting the
    auth file to the karasu service account.
    """
    if sys.platform.startswith("win"):  # pragma: no cover - Windows
        sys.stderr.write(
            "WARNING karasu.ui.auth: Windows posture detected; "
            "file mode enforcement is advisory only. Verify "
            "NTFS ACLs restrict the credentials file to the "
            "karasu service account. See docs/deploy-runbook.md.\n"
        )
        return
    try:
        observed = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:  # pragma: no cover
        raise AuthCredentialsError("credentials file mode unreadable") from exc
    if observed & ~0o600:
        raise AuthCredentialsError("credentials file mode looser than 0600")


def _validate_password_hash_shape(stored: str) -> None:
    """Codex P1 round 1 audit binding 2026-05-08: parse the
    canonical scrypt format and validate every pinned
    parameter at startup.

    Format: ``scrypt$N=<n>$r=<r>$p=<p>$<salt_b64u>$<hash_b64u>``

    Raises ``AuthCredentialsError`` on:
      * wrong number of ``$``-separated parts
      * unparseable N / r / p ints
      * (N, r, p) drift from the pinned (16384, 8, 1)
      * salt b64u decode failure or wrong length (≠ 16)
      * hash b64u decode failure or wrong length (≠ 32)

    Error messages are GENERIC per pin §3-B (no field name,
    no hex bytes, no path fragments)."""
    body = stored[len(_SCRYPT_PREFIX):]
    parts = body.split("$")
    if len(parts) != 5:
        raise AuthCredentialsError("password_hash parts count")
    n_part, r_part, p_part, salt_b64, hash_b64 = parts
    try:
        n = int(n_part.split("=", 1)[1])
        r = int(r_part.split("=", 1)[1])
        p = int(p_part.split("=", 1)[1])
    except (IndexError, ValueError) as exc:
        raise AuthCredentialsError("password_hash parameters") from exc
    if (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
        raise AuthCredentialsError("password_hash parameters drift")
    try:
        salt = _b64u_decode(salt_b64)
        derived = _b64u_decode(hash_b64)
    except Exception as exc:  # noqa: BLE001
        raise AuthCredentialsError("password_hash b64u decode") from exc
    if len(salt) != SCRYPT_SALT_LEN:
        raise AuthCredentialsError("password_hash salt length")
    if len(derived) != SCRYPT_KEY_LEN:
        raise AuthCredentialsError("password_hash key length")


def hash_password(password: str) -> str:
    """Return the canonical scrypt hash string for a password.

    Format: ``scrypt$N=<n>$r=<r>$p=<p>$<salt_b64u>$<hash_b64u>``

    Salt is fresh ``os.urandom(16)``. Parameters pinned per
    brief §3-B (N=16384, r=8, p=1).
    """
    salt = os.urandom(SCRYPT_SALT_LEN)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LEN,
    )
    return (
        f"{_SCRYPT_PREFIX}N={SCRYPT_N}$r={SCRYPT_R}$p={SCRYPT_P}"
        f"${_b64u_encode(salt)}${_b64u_encode(derived)}"
    )


def verify_password(stored: str, password: str) -> bool:
    """Constant-time verify ``password`` against ``stored``.

    Returns False on any parse failure (treats malformed
    hashes as "wrong password" to avoid leaking the
    distinction). Constant-time comparison via
    :func:`hmac.compare_digest` per pin §11.6.18.

    The dummy-scrypt-on-no-username branch in the login flow
    calls this with a known-bad stored hash so the response
    time is comparable to a real wrong-password (timing parity
    per §3-G + §11.6.7).
    """
    if not stored.startswith(_SCRYPT_PREFIX):
        return False
    try:
        body = stored[len(_SCRYPT_PREFIX):]
        n_part, r_part, p_part, salt_b64, hash_b64 = body.split("$")
        n = int(n_part.split("=")[1])
        r = int(r_part.split("=")[1])
        p = int(p_part.split("=")[1])
        salt = _b64u_decode(salt_b64)
        expected = _b64u_decode(hash_b64)
    except Exception:  # noqa: BLE001
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


# Dummy hash used by the login flow's no-username branch
# for timing parity (§3-G binding). Lazy-initialised on the
# first call to ``dummy_password_verify`` so module import
# does not pay the scrypt cost (≈250ms) — this matters for
# the test suite (every `from karasu.ui._auth import ...`
# would otherwise pay it) and for `karasu ui` startup.
_DUMMY_HASH: str | None = None
_DUMMY_HASH_LOCK = threading.Lock()


def dummy_password_verify() -> None:
    """Run a scrypt verification against a known-bad hash so
    the response time of a no-username login miss matches the
    real verify_password path. Called by the login handler
    when the username does not exist.

    Lazy initialisation: the first call computes
    ``_DUMMY_HASH`` (one extra scrypt cost on first miss);
    subsequent calls only verify. Both paths still pay one
    scrypt cost, so timing parity holds against
    ``verify_password`` (which is also one scrypt)."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        with _DUMMY_HASH_LOCK:
            if _DUMMY_HASH is None:
                _DUMMY_HASH = hash_password(
                    "__karasu_unused_dummy_password__"
                )
    verify_password(_DUMMY_HASH, "wrong")


def write_credentials(
    path: Path,
    *,
    username: str,
    password: str,
    rotate_signing_secret: bool = True,
) -> None:
    """Bootstrap or rotate credentials.

    Writes ``karasu-auth.json`` mode 0600 atomically (tmp +
    rename, mirror of UI-12b push_store discipline). If a file
    already exists, ``credentials_generation`` is bumped by 1
    so every existing session cookie is invalidated (gen
    mismatch path in §3-C). If the file is absent, gen starts
    at 0.

    ``rotate_signing_secret``: when True (the default on
    rotation), a fresh session signing secret is generated.
    Set to False ONLY for migrations that must preserve
    existing sessions across a credential change (rare;
    chunk-level decision; default ALWAYS rotates so the
    operator-pin "ops-side credential rotation invalidates
    ALL existing sessions" carries through unconditionally
    per §3-C + macro pin 8).
    """
    # Read the existing gen if present.
    existing_gen = -1
    existing_secret: bytes | None = None
    if path.exists():
        try:
            current = load_credentials(path)
            existing_gen = current.credentials_generation
            existing_secret = current.session_signing_secret
        except AuthCredentialsError:
            existing_gen = -1
            existing_secret = None

    new_secret = (
        os.urandom(SESSION_SECRET_LEN)
        if rotate_signing_secret or existing_secret is None
        else existing_secret
    )

    payload = {
        "username": username,
        "password_hash": hash_password(password),
        "session_signing_secret": _b64u_encode(new_secret),
        "credentials_generation": existing_gen + 1,
        "created_at": _utc_iso8601(),
        "rotated_at": _utc_iso8601(),
    }
    _atomic_write_0600(path, payload)


def _atomic_write_0600(path: Path, payload: dict[str, Any]) -> None:
    """Atomic tmp+rename write with mode 0600. Mirrors the
    UI-12b push_store writer shape verbatim — same EXCL flag,
    fsync, replace, and tmp cleanup discipline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists():
        raise AuthCredentialsError("credentials .tmp exists; recovery needed")
    flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL
    if hasattr(os, "O_BINARY"):  # pragma: no cover - Windows
        flags |= os.O_BINARY
    fd = os.open(str(tmp), flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as fh:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode(
                "utf-8"
            )
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:  # pragma: no cover
                pass
    except BaseException:
        try:
            tmp.unlink()
        except OSError:  # pragma: no cover
            pass
        raise
    os.replace(str(tmp), str(path))


def _utc_iso8601() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


# ---------------------------------------------------------------------------
# Sessions (signed cookie)
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME = "karasu_session"
DEFAULT_SESSION_TTL_SECONDS = 14 * 24 * 60 * 60   # 14 days
MIN_SESSION_TTL_SECONDS = 1 * 24 * 60 * 60        # 1 day
MAX_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60       # 30 days
SESSION_CLOCK_SKEW_SECONDS = 60                   # 60 s margin


def issue_session_token(
    *,
    creds: AuthCredentials,
    now: float | None = None,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> str:
    """Produce the session cookie value for ``creds`` at
    ``now`` (default :func:`time.time`)."""
    if now is None:
        now = time.time()
    nonce = _b64u_encode(os.urandom(16))
    exp = int(now) + int(ttl_seconds)
    payload = {
        "user": creds.username,
        "exp": exp,
        "gen": creds.credentials_generation,
        "nonce": nonce,
    }
    sig = _session_sig(creds.session_signing_secret, payload)
    payload["sig"] = sig
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return _b64u_encode(raw)


def _session_sig(secret: bytes, payload: dict[str, Any]) -> str:
    msg = (
        f"{payload['user']}|{payload['exp']}|{payload['gen']}|{payload['nonce']}"
    ).encode("utf-8")
    return _b64u_encode(hmac.new(secret, msg, hashlib.sha256).digest())


def verify_session_token(
    token: str,
    *,
    creds: AuthCredentials,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify ``token`` against ``creds``. Returns the
    decoded payload on success; raises AuthSessionError on
    any failure (parse, HMAC mismatch, gen mismatch,
    expired).

    All comparisons constant-time per pin §11.6.18.
    """
    if now is None:
        now = time.time()
    try:
        raw = _b64u_decode(token)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthSessionError("session token unparseable") from exc

    for key in ("user", "exp", "gen", "nonce", "sig"):
        if key not in payload:
            raise AuthSessionError("session token missing field")

    expected_sig = _session_sig(
        creds.session_signing_secret,
        {
            "user": payload["user"],
            "exp": payload["exp"],
            "gen": payload["gen"],
            "nonce": payload["nonce"],
        },
    )
    if not hmac.compare_digest(expected_sig, payload["sig"]):
        raise AuthSessionError("session signature mismatch")

    if payload["gen"] != creds.credentials_generation:
        raise AuthSessionError("session generation mismatch")

    if not isinstance(payload["exp"], int):
        raise AuthSessionError("session exp not int")
    if payload["exp"] + SESSION_CLOCK_SKEW_SECONDS < int(now):
        raise AuthSessionError("session expired")

    if payload["user"] != creds.username:
        # Defence-in-depth: gen mismatch should already cover
        # username drift since rotating creds bumps gen, but
        # check explicitly so a future bug that leaks an
        # alternate username cannot ride a stale cookie.
        raise AuthSessionError("session username mismatch")

    return payload


# ---------------------------------------------------------------------------
# CSRF (signed double-submit)
# ---------------------------------------------------------------------------

CSRF_COOKIE_NAME = "karasu_csrf"
CSRF_HEADER_NAME = "X-Karasu-CSRF"


def issue_csrf_token(
    *, creds: AuthCredentials, username: str, gen: int
) -> str:
    """Produce the CSRF cookie value (``nonce.sig``).

    The signature binds the session signing secret + username
    + credentials generation, so credentials rotation
    invalidates every CSRF token atomically along with
    sessions (§3-F).
    """
    nonce = _b64u_encode(os.urandom(SCRYPT_SALT_LEN))
    sig = _csrf_sig(creds.session_signing_secret, nonce, username, gen)
    return f"{nonce}.{sig}"


def _csrf_sig(secret: bytes, nonce: str, username: str, gen: int) -> str:
    msg = (
        b"csrf:" + nonce.encode("ascii")
        + b"|user:" + username.encode("utf-8")
        + b"|gen:" + str(gen).encode("ascii")
    )
    return _b64u_encode(hmac.new(secret, msg, hashlib.sha256).digest())


def verify_csrf(
    *,
    cookie_value: str | None,
    header_value: str | None,
    creds: AuthCredentials,
    username: str,
    gen: int,
) -> bool:
    """Validate the double-submit CSRF token. Both cookie +
    header MUST be present and match (constant-time); the
    cookie's signature MUST verify against the current
    session signing secret + user + gen. Returns False on
    any failure."""
    if not cookie_value or not header_value:
        return False
    if not hmac.compare_digest(cookie_value, header_value):
        return False
    if "." not in cookie_value:
        return False
    try:
        nonce, sig = cookie_value.rsplit(".", 1)
    except ValueError:
        return False
    expected = _csrf_sig(creds.session_signing_secret, nonce, username, gen)
    return hmac.compare_digest(expected, sig)


def origin_matches(
    *,
    request_origin: str | None,
    request_referer: str | None,
    expected_origins: tuple[str, ...],
    deployed: bool,
) -> bool:
    """Return True iff the request's Origin OR Referer
    matches one of ``expected_origins``.

    In deployed posture (``deployed=True``), absent Origin AND
    absent Referer is REJECTED (False). In dev posture
    (``deployed=False``), absent values pass through as the
    documented dev fallback (§3-F).
    """
    if request_origin:
        return request_origin in expected_origins
    if request_referer:
        for origin in expected_origins:
            if request_referer.startswith(origin + "/") or request_referer == origin:
                return True
        return False
    # both absent
    return not deployed


# ---------------------------------------------------------------------------
# Trusted-client-IP derivation (§3-G three-layer)
# ---------------------------------------------------------------------------


def derive_client_ip(
    *,
    peer_addr: str,
    forwarded_chain: list[str],
    trusted_proxies: frozenset[str],
) -> str | object | None:
    """Three-layer trusted-client-IP derivation.

    Returns:
      * IP string when the client is identifiable.
      * :data:`UNTRUSTED_FORWARDED` sentinel when the peer is
        NOT trusted but a forwarded chain was supplied — the
        request lacks a verifiable source (Codex round 3 P1
        binding).
      * ``None`` when every chain entry is itself trusted
        (impossible for genuine external traffic; fail-closed
        per §3-G).

    Layer A (proxy overwrite) lives in
    ``docs/deploy-runbook.md`` snippets and is OUT of this
    function's responsibility; this function is layer B
    (right-to-left walk) + layer C (untrusted-peer guard).
    """
    if peer_addr not in trusted_proxies:
        if forwarded_chain:
            return UNTRUSTED_FORWARDED
        return peer_addr
    for ip in reversed(forwarded_chain):
        if ip in trusted_proxies:
            continue
        return ip
    return None


def parse_forwarded_chain(
    *,
    forwarded_header: str | None,
    xff_header: str | None,
) -> list[str]:
    """Parse ``Forwarded`` (RFC 7239) + ``X-Forwarded-For``
    headers into a flat ordered list of IPs.

    Forwarded takes precedence when both are present; XFF is
    only consulted as a fallback for older proxy
    configurations. Malformed entries are skipped silently
    (the caller's downstream handling treats an empty result
    as "no chain"). Returns the chain in left-to-right order
    (latest hop right-most, mirroring nginx XFF append
    semantics)."""
    if forwarded_header:
        chain: list[str] = []
        for entry in forwarded_header.split(","):
            entry = entry.strip()
            for part in entry.split(";"):
                part = part.strip().lower()
                if part.startswith("for="):
                    raw = part[4:].strip().strip('"')
                    # IPv6 with port: "[::1]:8080"
                    if raw.startswith("[") and "]" in raw:
                        raw = raw.split("]", 1)[0][1:]
                    elif ":" in raw and raw.count(":") == 1:
                        # IPv4:port
                        raw = raw.split(":", 1)[0]
                    if raw:
                        chain.append(raw)
                    break
        return chain
    if xff_header:
        return [ip.strip() for ip in xff_header.split(",") if ip.strip()]
    return []


def is_loopback_ip(addr: str) -> bool:
    """IP-literal loopback test. Used by rate-limit +
    derive_client_ip bypass checks. Does NOT accept the
    "localhost" hostname literal — only IP addresses
    (127.0.0.0/8 + ::1). A forwarded chain entry of
    "localhost" therefore cannot trigger the bypass."""
    if addr in _LOCALHOST_IPS:
        return True
    if addr.startswith(_LOCALHOST_V4_PREFIX):
        return True
    return False


# ---------------------------------------------------------------------------
# Loopback bind validation (§3-B --no-auth contract)
# ---------------------------------------------------------------------------


def is_loopback_bind(host: str) -> bool:
    """True iff ``host`` resolves entirely to loopback
    addresses. Mixed-resolution hosts return False
    (deliberately conservative per §3-B).

    Used by cmd_ui to refuse `--no-auth --host 0.0.0.0`
    combinations at startup. Accepts IP literals + the
    "localhost" hostname directly; everything else is
    resolved via ``socket.getaddrinfo`` and every result
    must be loopback.
    """
    if is_loopback_ip(host) or host in _LOCALHOST_HOSTNAMES:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        if not is_loopback_ip(addr):
            return False
    return True


# ---------------------------------------------------------------------------
# Rate-limit (§3-G + pin §11.6.10)
# ---------------------------------------------------------------------------


@dataclass
class _BucketState:
    failures: int = 0
    window_started_at: float = 0.0
    backoff_until: float = 0.0


class LoginRateLimit:
    """In-memory per-IP + per-credentials rate-limit.

    Restart-cleared by design (mirror of UI-12c
    pin §11.6.5 dedupe ring + §3-G binding). The
    LoginRateLimit instance is constructed at server startup
    + lives for the lifetime of the karasu ui process.

    Per-IP burst: 5 failures in 60 s → 429 + exponential
    backoff doubling per burst (cap 1 hour).
    Per-credentials burst: 10 failures in 5 min → 429 for
    the same backoff window.

    Localhost client_ip bypasses both buckets per §3-G; the
    bypass kicks in AFTER derive_client_ip has resolved the
    real client (NOT just on a localhost peer addr).
    """

    PER_IP_MAX_FAILURES = 5
    PER_IP_WINDOW = 60.0
    PER_CRED_MAX_FAILURES = 10
    PER_CRED_WINDOW = 5 * 60.0
    BACKOFF_INITIAL = 60.0
    BACKOFF_MAX = 60.0 * 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._per_ip: dict[str, _BucketState] = {}
        self._per_cred: dict[str, _BucketState] = {}

    def check(
        self,
        *,
        client_ip: str,
        username_attempted: str,
        now: Callable[[], float] = time.monotonic,
    ) -> bool:
        """Return True iff the request should proceed; False
        if rate-limited (caller emits 429)."""
        if is_loopback_ip(client_ip):
            return True
        t = now()
        with self._lock:
            ip_bucket = self._per_ip.setdefault(client_ip, _BucketState())
            cred_bucket = self._per_cred.setdefault(
                username_attempted, _BucketState()
            )
            for bucket in (ip_bucket, cred_bucket):
                if bucket.backoff_until and t < bucket.backoff_until:
                    return False
            return True

    def record_failure(
        self,
        *,
        client_ip: str,
        username_attempted: str,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        """Increment failure counters + maybe trip backoff."""
        if is_loopback_ip(client_ip):
            return
        t = now()
        with self._lock:
            self._tick(self._per_ip, client_ip, t,
                       self.PER_IP_MAX_FAILURES, self.PER_IP_WINDOW)
            self._tick(self._per_cred, username_attempted, t,
                       self.PER_CRED_MAX_FAILURES, self.PER_CRED_WINDOW)

    def record_success(
        self, *, client_ip: str, username: str
    ) -> None:
        """Clear both bucket counters on a successful login."""
        if is_loopback_ip(client_ip):
            return
        with self._lock:
            self._per_ip.pop(client_ip, None)
            self._per_cred.pop(username, None)

    def _tick(
        self,
        store: dict[str, _BucketState],
        key: str,
        t: float,
        max_failures: int,
        window: float,
    ) -> None:
        bucket = store.setdefault(key, _BucketState())
        if t - bucket.window_started_at > window:
            bucket.failures = 0
            bucket.window_started_at = t
        bucket.failures += 1
        if bucket.failures >= max_failures:
            # First burst → BACKOFF_INITIAL. Subsequent bursts
            # while a backoff is still in effect → double the
            # remaining window. Brief §3-G: "5 failed attempts
            # / 60 s → 429; backoff window doubles on each
            # SUBSEQUENT burst (cap at 1 hour)".
            if bucket.backoff_until > t:
                remaining = bucket.backoff_until - t
                new_window = min(self.BACKOFF_MAX, remaining * 2)
            else:
                new_window = self.BACKOFF_INITIAL
            bucket.backoff_until = t + new_window
            bucket.failures = 0
            bucket.window_started_at = t


# ---------------------------------------------------------------------------
# Anonymous path perimeter (§3-D)
# ---------------------------------------------------------------------------

# Exact-set anonymous paths (§3-D + pin §11.6.6 carry-forward).
_ANONYMOUS_GET_PATHS: frozenset[str] = frozenset({
    "/",
    "/assets/css/login.css",
    "/assets/css/tokens.css",
    "/assets/css/reset.css",
    "/assets/css/base.css",
    "/assets/icons/karasu-192.png",
    "/assets/crow/crow.svg",
    "/assets/manifest.json",
    "/assets/sw.js",
    "/auth/logout",
})

# Anonymous fonts directory (entire dir per §3-D + §3-H).
_ANONYMOUS_GET_PREFIXES: tuple[str, ...] = (
    "/assets/fonts/",
)

_ANONYMOUS_POST_PATHS: frozenset[str] = frozenset({
    "/auth/login",
})


def is_anonymous_path(method: str, path: str) -> bool:
    """Return True iff the request method + path is in the
    exact anonymous-perimeter whitelist (§3-D)."""
    if method == "GET":
        if path in _ANONYMOUS_GET_PATHS:
            return True
        for prefix in _ANONYMOUS_GET_PREFIXES:
            if path.startswith(prefix):
                return True
        return False
    if method == "POST":
        return path in _ANONYMOUS_POST_PATHS
    return False
