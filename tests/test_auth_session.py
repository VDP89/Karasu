"""Session token + CSRF tests — UI-13 §3-C + §3-F + pin
§11.6.18 constant-time discipline."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from karasu.ui._auth import (
    AuthCredentials,
    AuthSessionError,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    DEFAULT_SESSION_TTL_SECONDS,
    SESSION_CLOCK_SKEW_SECONDS,
    SESSION_COOKIE_NAME,
    issue_csrf_token,
    issue_session_token,
    load_credentials,
    origin_matches,
    verify_csrf,
    verify_session_token,
    write_credentials,
)


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@pytest.fixture
def creds(tmp_path: Path) -> AuthCredentials:
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="hunter2")
    return load_credentials(path)


# ---------------------------------------------------------------------------
# Session token shape + constants
# ---------------------------------------------------------------------------


def test_constants_match_brief() -> None:
    assert SESSION_COOKIE_NAME == "karasu_session"
    assert CSRF_COOKIE_NAME == "karasu_csrf"
    assert CSRF_HEADER_NAME == "X-Karasu-CSRF"
    assert DEFAULT_SESSION_TTL_SECONDS == 14 * 24 * 60 * 60
    assert SESSION_CLOCK_SKEW_SECONDS == 60


def test_issue_session_token_shape(creds: AuthCredentials) -> None:
    token = issue_session_token(creds=creds, now=1_700_000_000)
    payload = json.loads(_b64u_decode(token).decode("utf-8"))
    assert set(payload.keys()) == {"user", "exp", "gen", "nonce", "sig"}
    assert payload["user"] == "victor"
    assert payload["exp"] == 1_700_000_000 + DEFAULT_SESSION_TTL_SECONDS
    assert payload["gen"] == 0
    assert len(payload["nonce"]) >= 16


def test_issue_session_token_unique_per_call(
    creds: AuthCredentials,
) -> None:
    a = issue_session_token(creds=creds, now=1_700_000_000)
    b = issue_session_token(creds=creds, now=1_700_000_000)
    assert a != b  # different nonces


# ---------------------------------------------------------------------------
# Session verification
# ---------------------------------------------------------------------------


def test_verify_session_token_round_trip(creds: AuthCredentials) -> None:
    token = issue_session_token(creds=creds, now=1_700_000_000)
    payload = verify_session_token(
        token, creds=creds, now=1_700_000_001
    )
    assert payload["user"] == "victor"


def test_verify_rejects_tampered_signature(
    creds: AuthCredentials,
) -> None:
    token = issue_session_token(creds=creds)
    tampered_bytes = bytearray(_b64u_decode(token))
    tampered_bytes[-5] ^= 0x01
    bad = base64.urlsafe_b64encode(bytes(tampered_bytes)).rstrip(b"=").decode()
    with pytest.raises(AuthSessionError):
        verify_session_token(bad, creds=creds)


def test_verify_rejects_tampered_user(creds: AuthCredentials) -> None:
    token = issue_session_token(creds=creds)
    payload = json.loads(_b64u_decode(token))
    payload["user"] = "attacker"
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    bad = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(AuthSessionError, match="signature mismatch"):
        verify_session_token(bad, creds=creds)


def test_verify_rejects_expired_token(creds: AuthCredentials) -> None:
    token = issue_session_token(
        creds=creds, now=1_700_000_000, ttl_seconds=10
    )
    with pytest.raises(AuthSessionError, match="expired"):
        verify_session_token(
            token, creds=creds, now=1_700_000_000 + 10 + 61
        )


def test_verify_clock_skew_margin(creds: AuthCredentials) -> None:
    """60s margin allows tokens 60s past exp to verify."""
    token = issue_session_token(
        creds=creds, now=1_700_000_000, ttl_seconds=10
    )
    # 30 s past exp — within the 60 s margin.
    payload = verify_session_token(
        token, creds=creds, now=1_700_000_000 + 10 + 30
    )
    assert payload["user"] == "victor"


def test_verify_rejects_gen_mismatch(tmp_path: Path) -> None:
    """credentials_generation rotation invalidates all
    sessions atomically (§3-C + macro pin 8). Uses
    rotate_signing_secret=False so the test isolates the
    gen-mismatch branch (a normal rotation would also rotate
    the secret and trip signature mismatch first; both paths
    invalidate sessions, but the test pins each independently
    — the full-rotation case is covered by the round-trip
    plus the signature-mismatch test)."""
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="hunter2")
    old_creds = load_credentials(path)
    token = issue_session_token(creds=old_creds)

    # Bump gen WITHOUT rotating signing secret to isolate
    # the gen-mismatch branch.
    write_credentials(
        path,
        username="victor",
        password="new_password",
        rotate_signing_secret=False,
    )
    new_creds = load_credentials(path)
    assert new_creds.credentials_generation == 1
    assert new_creds.session_signing_secret == old_creds.session_signing_secret

    with pytest.raises(AuthSessionError, match="generation"):
        verify_session_token(token, creds=new_creds)


def test_verify_rejects_signature_mismatch_on_secret_rotation(
    tmp_path: Path,
) -> None:
    """The default credentials rotation (rotate_signing_secret=True)
    rotates the secret along with bumping gen. Verification
    fails at the SIGNATURE check (which precedes the gen
    check), so the message is "signature mismatch". Both
    paths invalidate sessions; this test pins the
    "secret rotated" branch verbatim."""
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="hunter2")
    old_creds = load_credentials(path)
    token = issue_session_token(creds=old_creds)

    # Default rotation → both secret and gen change.
    write_credentials(path, username="victor", password="new_password")
    new_creds = load_credentials(path)
    assert new_creds.credentials_generation == 1
    assert new_creds.session_signing_secret != old_creds.session_signing_secret

    with pytest.raises(AuthSessionError, match="signature mismatch"):
        verify_session_token(token, creds=new_creds)


def test_verify_rejects_unparseable_token(creds: AuthCredentials) -> None:
    with pytest.raises(AuthSessionError):
        verify_session_token("not a token", creds=creds)


def test_verify_rejects_missing_field(creds: AuthCredentials) -> None:
    payload = {"user": "v", "exp": 9999999999, "gen": 0}  # missing nonce + sig
    raw = json.dumps(payload).encode("utf-8")
    bad = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(AuthSessionError, match="missing field"):
        verify_session_token(bad, creds=creds)


# ---------------------------------------------------------------------------
# CSRF — signed double-submit cookie
# ---------------------------------------------------------------------------


def test_csrf_token_shape(creds: AuthCredentials) -> None:
    token = issue_csrf_token(
        creds=creds, username="victor", gen=0
    )
    assert "." in token
    nonce, sig = token.rsplit(".", 1)
    assert len(nonce) >= 16
    assert len(sig) >= 32  # b64u of 32-byte HMAC


def test_csrf_unique_per_call(creds: AuthCredentials) -> None:
    a = issue_csrf_token(creds=creds, username="victor", gen=0)
    b = issue_csrf_token(creds=creds, username="victor", gen=0)
    assert a != b


def test_csrf_verify_round_trip(creds: AuthCredentials) -> None:
    token = issue_csrf_token(creds=creds, username="victor", gen=0)
    assert verify_csrf(
        cookie_value=token,
        header_value=token,
        creds=creds,
        username="victor",
        gen=0,
    ) is True


def test_csrf_rejects_cookie_header_mismatch(
    creds: AuthCredentials,
) -> None:
    a = issue_csrf_token(creds=creds, username="victor", gen=0)
    b = issue_csrf_token(creds=creds, username="victor", gen=0)
    assert verify_csrf(
        cookie_value=a,
        header_value=b,
        creds=creds,
        username="victor",
        gen=0,
    ) is False


def test_csrf_rejects_tampered_signature(creds: AuthCredentials) -> None:
    token = issue_csrf_token(creds=creds, username="victor", gen=0)
    nonce, sig = token.rsplit(".", 1)
    tampered = nonce + "." + sig[:-2] + "AA"  # corrupt last 2 b64 chars
    assert verify_csrf(
        cookie_value=tampered,
        header_value=tampered,
        creds=creds,
        username="victor",
        gen=0,
    ) is False


def test_csrf_rejects_wrong_username(creds: AuthCredentials) -> None:
    """Token bound to username — switching username on
    verify rejects."""
    token = issue_csrf_token(creds=creds, username="victor", gen=0)
    assert verify_csrf(
        cookie_value=token,
        header_value=token,
        creds=creds,
        username="attacker",
        gen=0,
    ) is False


def test_csrf_rejects_wrong_gen(creds: AuthCredentials) -> None:
    """Token bound to gen — credentials rotation invalidates
    the CSRF token along with the session."""
    token = issue_csrf_token(creds=creds, username="victor", gen=0)
    assert verify_csrf(
        cookie_value=token,
        header_value=token,
        creds=creds,
        username="victor",
        gen=1,
    ) is False


def test_csrf_rejects_empty_values(creds: AuthCredentials) -> None:
    assert verify_csrf(
        cookie_value=None,
        header_value="x.y",
        creds=creds,
        username="v",
        gen=0,
    ) is False
    assert verify_csrf(
        cookie_value="x.y",
        header_value=None,
        creds=creds,
        username="v",
        gen=0,
    ) is False
    assert verify_csrf(
        cookie_value="",
        header_value="",
        creds=creds,
        username="v",
        gen=0,
    ) is False


def test_csrf_rejects_malformed_value(creds: AuthCredentials) -> None:
    bad = "no-dot-separator"
    assert verify_csrf(
        cookie_value=bad,
        header_value=bad,
        creds=creds,
        username="v",
        gen=0,
    ) is False


# ---------------------------------------------------------------------------
# Origin / Referer matching (§3-F)
# ---------------------------------------------------------------------------

EXPECTED = ("https://karasu.example.com",)


def test_origin_match_origin_exact() -> None:
    assert origin_matches(
        request_origin="https://karasu.example.com",
        request_referer=None,
        expected_origins=EXPECTED,
        deployed=True,
    ) is True


def test_origin_match_origin_wrong() -> None:
    assert origin_matches(
        request_origin="https://attacker.test",
        request_referer=None,
        expected_origins=EXPECTED,
        deployed=True,
    ) is False


def test_origin_referer_fallback_match() -> None:
    assert origin_matches(
        request_origin=None,
        request_referer="https://karasu.example.com/",
        expected_origins=EXPECTED,
        deployed=True,
    ) is True


def test_origin_referer_fallback_with_path() -> None:
    assert origin_matches(
        request_origin=None,
        request_referer="https://karasu.example.com/some/page",
        expected_origins=EXPECTED,
        deployed=True,
    ) is True


def test_origin_deployed_rejects_both_absent() -> None:
    """Pin §11.6.8: deployed posture rejects absent
    Origin AND absent Referer."""
    assert origin_matches(
        request_origin=None,
        request_referer=None,
        expected_origins=EXPECTED,
        deployed=True,
    ) is False


def test_origin_dev_accepts_both_absent() -> None:
    """Pin §11.6.8 dev fallback: localhost / --no-auth
    posture accepts both absent."""
    assert origin_matches(
        request_origin=None,
        request_referer=None,
        expected_origins=EXPECTED,
        deployed=False,
    ) is True


def test_origin_referer_wrong_origin() -> None:
    assert origin_matches(
        request_origin=None,
        request_referer="https://attacker.test/karasu",
        expected_origins=EXPECTED,
        deployed=True,
    ) is False


# Brief amendment 2026-05-16 (§3-F dev fallback): dev posture
# with empty expected_origins MUST be permissive even when the
# browser sends Origin. Phase-4 dogfood Bug "Could not sign in"
# repro was a fresh `karasu ui` (no karasu.yaml, no expected
# origins) where every browser POST carried Origin and was
# rejected 403 by the empty-allowlist check.


def test_origin_dev_no_origins_accepts_browser_origin() -> None:
    """Dev posture + no configured origins + browser-sent Origin
    → True. The original bug: this returned False because
    "Origin in ()" was the first branch and short-circuited the
    dev fallback."""
    assert origin_matches(
        request_origin="http://127.0.0.1:8787",
        request_referer=None,
        expected_origins=(),
        deployed=False,
    ) is True


def test_origin_dev_no_origins_accepts_browser_referer() -> None:
    """Dev posture + no configured origins + Referer-only request
    → True. Same fix as the Origin case, covers the Referer
    fallback path."""
    assert origin_matches(
        request_origin=None,
        request_referer="http://127.0.0.1:8787/",
        expected_origins=(),
        deployed=False,
    ) is True


def test_origin_dev_with_origins_still_strict() -> None:
    """Dev posture + EXPLICITLY configured origins → strict.
    A dev operator who configured `auth.expected_origins`
    opted into the allowlist and should not be silently bypassed.
    (deployed=False here because deployed is derived from origins
    being non-empty in cmd_ui, but the function itself takes the
    deployed flag separately — guarding both axes.)"""
    assert origin_matches(
        request_origin="http://attacker.test",
        request_referer=None,
        expected_origins=("http://127.0.0.1:8787",),
        deployed=False,
    ) is False


def test_origin_deployed_no_origins_still_rejects_browser_origin() -> None:
    """Deployed posture + (defensively) empty origins MUST still
    reject. Production setups always have origins configured, so
    this branch is unreachable through cmd_ui, but the function
    is exported and other callers must get strict semantics
    whenever deployed=True."""
    assert origin_matches(
        request_origin="http://127.0.0.1:8787",
        request_referer=None,
        expected_origins=(),
        deployed=True,
    ) is False
