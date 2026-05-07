"""Credentials store tests — UI-13 §3-B + pin §11.6.16
fail-closed contract."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from karasu.ui._auth import (
    AuthCredentials,
    AuthCredentialsError,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    SESSION_SECRET_LEN,
    hash_password,
    load_credentials,
    verify_password,
    write_credentials,
)


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------


def test_hash_password_format() -> None:
    h = hash_password("victor-password")
    assert h.startswith("scrypt$")
    parts = h[len("scrypt$") :].split("$")
    assert len(parts) == 5
    n_part, r_part, p_part, salt_b64, hash_b64 = parts
    assert n_part == f"N={SCRYPT_N}"
    assert r_part == f"r={SCRYPT_R}"
    assert p_part == f"p={SCRYPT_P}"
    assert "=" not in salt_b64  # b64u-no-pad
    assert "=" not in hash_b64


def test_hash_password_unique_per_call() -> None:
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # different salts


def test_verify_password_correct() -> None:
    h = hash_password("hello world")
    assert verify_password(h, "hello world") is True


def test_verify_password_wrong() -> None:
    h = hash_password("right")
    assert verify_password(h, "wrong") is False


def test_verify_password_malformed_returns_false() -> None:
    assert verify_password("not a hash", "anything") is False
    assert verify_password("scrypt$bogus", "anything") is False
    assert verify_password("", "anything") is False


# ---------------------------------------------------------------------------
# write_credentials / load_credentials
# ---------------------------------------------------------------------------


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "karasu-auth.json"
    write_credentials(path, username="victor", password="s3cret")

    creds = load_credentials(path)
    assert isinstance(creds, AuthCredentials)
    assert creds.username == "victor"
    assert verify_password(creds.password_hash, "s3cret") is True
    assert verify_password(creds.password_hash, "wrong") is False
    assert len(creds.session_signing_secret) == SESSION_SECRET_LEN
    assert creds.credentials_generation == 0  # first write


def test_write_increments_generation_on_rotation(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="a")
    write_credentials(path, username="victor", password="b")
    write_credentials(path, username="victor", password="c")

    creds = load_credentials(path)
    assert creds.credentials_generation == 2  # 0 → 1 → 2


def test_write_rotates_signing_secret_by_default(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="a")
    s1 = load_credentials(path).session_signing_secret
    write_credentials(path, username="victor", password="b")
    s2 = load_credentials(path).session_signing_secret
    assert s1 != s2


def test_write_preserves_signing_secret_when_asked(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(path, username="victor", password="a")
    s1 = load_credentials(path).session_signing_secret
    write_credentials(
        path,
        username="victor",
        password="b",
        rotate_signing_secret=False,
    )
    s2 = load_credentials(path).session_signing_secret
    assert s1 == s2


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="POSIX file mode test",
)
def test_write_creates_mode_0600(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(path, username="v", password="p")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# Fail-closed contract — §3-B + Codex round 1 P1.6
# ---------------------------------------------------------------------------


def test_load_absent_file_raises(tmp_path: Path) -> None:
    with pytest.raises(AuthCredentialsError, match="absent"):
        load_credentials(tmp_path / "missing.json")


def test_load_malformed_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{ malformed", encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="malformed json"):
        load_credentials(path)


def test_load_non_object_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="json object"):
        load_credentials(path)


def test_load_missing_username_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    payload = json.dumps(
        {
            "password_hash": "scrypt$x",
            "session_signing_secret": "AA" * 22,
            "credentials_generation": 0,
        }
    )
    path.write_text(payload, encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="username"):
        load_credentials(path)


def test_load_malformed_password_hash_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    payload = json.dumps(
        {
            "username": "v",
            "password_hash": "bcrypt$nothing",
            "session_signing_secret": "x" * 44,
            "credentials_generation": 0,
        }
    )
    path.write_text(payload, encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="password_hash"):
        load_credentials(path)


def test_load_short_signing_secret_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    payload = json.dumps(
        {
            "username": "v",
            "password_hash": "scrypt$short",
            "session_signing_secret": "AAAA",  # 3 bytes
            "credentials_generation": 0,
        }
    )
    path.write_text(payload, encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="too short"):
        load_credentials(path)


def test_load_negative_generation_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    payload = json.dumps(
        {
            "username": "v",
            "password_hash": "scrypt$ok",
            "session_signing_secret": "A" * 44,
            "credentials_generation": -1,
        }
    )
    path.write_text(payload, encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)
    with pytest.raises(AuthCredentialsError, match="credentials_generation"):
        load_credentials(path)


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="POSIX mode-0600 enforcement test",
)
def test_load_loose_mode_raises(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(path, username="v", password="p")
    os.chmod(path, 0o644)  # world-readable
    with pytest.raises(AuthCredentialsError, match="0600"):
        load_credentials(path)


# ---------------------------------------------------------------------------
# Privacy: stored hash never leaks plaintext
# ---------------------------------------------------------------------------


def test_password_hash_does_not_contain_password(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    write_credentials(
        path,
        username="victor",
        password="SENTINEL_CLEARTEXT_PASSWORD_xxxx",
    )
    blob = path.read_text(encoding="utf-8")
    assert "SENTINEL_CLEARTEXT" not in blob
