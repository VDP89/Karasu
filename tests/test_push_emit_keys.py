"""VAPID keypair generation + bootstrap tests.

Brief §3-I + pin §11.6.13 + Codex P1 round 1 binding.

The bootstrap path is tested in ISOLATION here — the
integration with the LoopController happens in
``test_push_emit_dispatch.py``. Each case below pins one
behavioral branch of :func:`bootstrap_if_missing` so a future
chunk that touches the bootstrap cannot regress the contract
unnoticed.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from karasu.push_emit._keys import (
    PRIVATE_B64U_LEN,
    PUBLIC_B64U_LEN,
    bootstrap_if_missing,
    generate_vapid_keypair,
)
from karasu.ui.push_store import PushStoreError, _read_or_empty_store


# ---------------------------------------------------------------------------
# generate_vapid_keypair — shape contract
# ---------------------------------------------------------------------------


def test_generate_returns_pair_of_strings() -> None:
    public, private = generate_vapid_keypair()
    assert isinstance(public, str)
    assert isinstance(private, str)


def test_generate_b64url_lengths_pinned() -> None:
    """Brief §3-F: public is 87 chars (65-byte uncompressed
    point b64u-no-pad — ceil(65*4/3) = 87; the brief's "86"
    descriptive comment is a typo); private is 43 chars
    (32-byte scalar b64u-no-pad). Byte lengths are the binding
    contract; the b64u counts are derived."""
    public, private = generate_vapid_keypair()
    assert len(public) == PUBLIC_B64U_LEN == 87
    assert len(private) == PRIVATE_B64U_LEN == 43


def test_generate_b64url_decodes_to_correct_byte_lengths() -> None:
    public, private = generate_vapid_keypair()

    pub_bytes = base64.urlsafe_b64decode(public + "==")
    priv_bytes = base64.urlsafe_b64decode(private + "==")

    assert len(pub_bytes) == 65
    assert pub_bytes[0] == 0x04  # uncompressed point marker
    assert len(priv_bytes) == 32


def test_generate_no_padding_in_b64url() -> None:
    public, private = generate_vapid_keypair()
    assert "=" not in public
    assert "=" not in private


def test_generate_keys_are_distinct_per_call() -> None:
    """Fresh entropy per call — guards against a deterministic
    seed leaking into the keypair."""
    pub1, priv1 = generate_vapid_keypair()
    pub2, priv2 = generate_vapid_keypair()

    assert pub1 != pub2
    assert priv1 != priv2


# ---------------------------------------------------------------------------
# bootstrap_if_missing — idempotency matrix
# ---------------------------------------------------------------------------


def test_bootstrap_creates_store_when_missing(tmp_path: Path) -> None:
    """Store absent → bootstrap creates it + writes a fresh
    keypair. Returns True (generated)."""
    store_path = tmp_path / "store.json"

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    assert store_path.exists()
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert "vapid" in raw
    assert isinstance(raw["vapid"]["public"], str)
    assert isinstance(raw["vapid"]["private"], str)
    assert len(raw["vapid"]["public"]) == PUBLIC_B64U_LEN
    assert len(raw["vapid"]["private"]) == PRIVATE_B64U_LEN


def test_bootstrap_adds_vapid_to_existing_store(tmp_path: Path) -> None:
    """Store exists with subscriptions but no vapid section →
    bootstrap adds vapid, leaves subscriptions untouched."""
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps(
            {
                "subscriptions": [
                    {
                        "endpoint": "https://example.test/push/abc",
                        "endpoint_hash": "abcdef",
                        "keys": {"p256dh": "p", "auth": "a"},
                        "categories": ["attention"],
                        "created_at": "2026-05-06T00:00:00Z",
                        "updated_at": "2026-05-06T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    raw = _read_or_empty_store(store_path)
    assert "vapid" in raw
    assert raw["subscriptions"][0]["endpoint"] == "https://example.test/push/abc"


def test_bootstrap_idempotent_when_complete(tmp_path: Path) -> None:
    """Store has both keys → bootstrap is a no-op. Returns
    False (no generation). The existing keypair is byte-for-byte
    preserved."""
    store_path = tmp_path / "store.json"
    bootstrap_if_missing(store_path)

    raw_before = _read_or_empty_store(store_path)
    pub_before = raw_before["vapid"]["public"]
    priv_before = raw_before["vapid"]["private"]

    generated = bootstrap_if_missing(store_path)

    assert generated is False
    raw_after = _read_or_empty_store(store_path)
    assert raw_after["vapid"]["public"] == pub_before
    assert raw_after["vapid"]["private"] == priv_before


def test_bootstrap_regenerates_on_partial_vapid_only_public(
    tmp_path: Path,
) -> None:
    """Brief §3-I keys test surface: partial vapid (only
    public) → REGENERATE both. Operator's manual seed is
    "complete or considered corrupt"."""
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps({"vapid": {"public": "ONLY_PUBLIC"}}),
        encoding="utf-8",
    )

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    raw = _read_or_empty_store(store_path)
    assert raw["vapid"]["public"] != "ONLY_PUBLIC"  # regenerated
    assert len(raw["vapid"]["public"]) == PUBLIC_B64U_LEN
    assert len(raw["vapid"]["private"]) == PRIVATE_B64U_LEN


def test_bootstrap_regenerates_on_partial_vapid_only_private(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps({"vapid": {"private": "ONLY_PRIVATE"}}),
        encoding="utf-8",
    )

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    raw = _read_or_empty_store(store_path)
    assert raw["vapid"]["private"] != "ONLY_PRIVATE"
    assert len(raw["vapid"]["public"]) == PUBLIC_B64U_LEN


def test_bootstrap_regenerates_on_empty_strings(tmp_path: Path) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps({"vapid": {"public": "", "private": ""}}),
        encoding="utf-8",
    )

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    raw = _read_or_empty_store(store_path)
    assert raw["vapid"]["public"] != ""
    assert raw["vapid"]["private"] != ""


def test_bootstrap_regenerates_on_wrong_types(tmp_path: Path) -> None:
    """``vapid`` present but the values are not strings →
    regenerate (untrusted shape)."""
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps({"vapid": {"public": 123, "private": ["array"]}}),
        encoding="utf-8",
    )

    generated = bootstrap_if_missing(store_path)

    assert generated is True
    raw = _read_or_empty_store(store_path)
    assert isinstance(raw["vapid"]["public"], str)


# ---------------------------------------------------------------------------
# bootstrap_if_missing — error propagation
# ---------------------------------------------------------------------------


def test_bootstrap_propagates_malformed_store_error(tmp_path: Path) -> None:
    """Brief §3-I keys test surface: malformed store
    (PushStoreError from _read_or_empty_store) propagates to
    the caller. The karasu watch controller logs generically
    and exits — that's a controller-level concern, not the
    bootstrap's."""
    store_path = tmp_path / "store.json"
    store_path.write_text("not json {", encoding="utf-8")

    with pytest.raises(PushStoreError):
        bootstrap_if_missing(store_path)


# ---------------------------------------------------------------------------
# pin §11.6.16 — no key material in logs
# ---------------------------------------------------------------------------


def test_bootstrap_log_carries_no_key_material(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Pin §11.6.16: the success log line is the flat string
    ``"generated VAPID keypair"`` — no lengths, no key fragments,
    no fingerprints. caplog asserts no key bytes leak."""
    store_path = tmp_path / "store.json"

    with caplog.at_level("DEBUG", logger="karasu.push_emit._keys"):
        bootstrap_if_missing(store_path)

    raw = _read_or_empty_store(store_path)
    public_substr = raw["vapid"]["public"][:10]
    private_substr = raw["vapid"]["private"][:10]

    for record in caplog.records:
        msg = record.getMessage()
        assert public_substr not in msg
        assert private_substr not in msg
        # No lengths either (the contract is the flat string).
        assert "87" not in msg
        assert "43" not in msg


def test_bootstrap_log_message_is_generic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store_path = tmp_path / "store.json"

    with caplog.at_level("INFO", logger="karasu.push_emit._keys"):
        bootstrap_if_missing(store_path)

    relevant = [
        r for r in caplog.records
        if "generated VAPID keypair" in r.getMessage()
    ]
    assert len(relevant) == 1


def test_bootstrap_idempotent_path_emits_no_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No-op (already-bootstrapped) path should NOT emit the
    "generated" line — it would be misleading."""
    store_path = tmp_path / "store.json"
    bootstrap_if_missing(store_path)
    caplog.clear()

    with caplog.at_level("INFO", logger="karasu.push_emit._keys"):
        bootstrap_if_missing(store_path)

    relevant = [
        r for r in caplog.records
        if "generated VAPID keypair" in r.getMessage()
    ]
    assert len(relevant) == 0
