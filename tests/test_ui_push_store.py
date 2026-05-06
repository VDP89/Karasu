"""Unit tests for the UI-12a read-only push subscription store.

Pairs with the HTTP shape lock in
``tests/test_ui_server_http.py`` (which exercises the same
projection through the full HTTP path). These tests pin the
push_store module's behaviour in isolation: empty store
sentinel, partial-shape degradation, malformed-store error
classification, and the privacy-preserving projection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from karasu.ui.push_store import (
    PUSH_CATEGORIES,
    PushStoreError,
    PushStoreState,
    project_push_state_payload,
    read_push_store,
)


# ---------------------------------------------------------------------------
# read_push_store — empty / missing
# ---------------------------------------------------------------------------


def test_missing_store_returns_empty_state(tmp_path: Path) -> None:
    """First-start contract: no file on disk → empty-state
    sentinel. UI-12a's footer affordance must work against an
    absent store; an exception here would break a fresh
    checkout."""
    state = read_push_store(tmp_path / "does-not-exist.json")
    assert state.subscription_count == 0
    assert state.vapid_public_key is None
    assert state.file_present is False


def test_present_but_empty_object_store(tmp_path: Path) -> None:
    """An empty JSON object is a legitimate state — operator
    explicitly initialised the file but has not subscribed
    yet. Surface as count=0, public_key=None, file_present=True
    so the operator can distinguish "fresh checkout" from
    "explicitly-empty store" if a future surface needs to."""
    path = tmp_path / "karasu-push.json"
    path.write_text("{}", encoding="utf-8")
    state = read_push_store(path)
    assert state.subscription_count == 0
    assert state.vapid_public_key is None
    assert state.file_present is True


# ---------------------------------------------------------------------------
# read_push_store — populated
# ---------------------------------------------------------------------------


def test_populated_store_counts_subscriptions(tmp_path: Path) -> None:
    """N subscriptions in the store → state.subscription_count
    == N. The store keeps the full subscription objects;
    counting them is the projection's only public surface."""
    path = tmp_path / "karasu-push.json"
    path.write_text(
        json.dumps({
            "vapid": {"public": "pub-key", "private": "private"},
            "subscriptions": [
                {"endpoint": "https://x", "keys": {}, "categories": []},
                {"endpoint": "https://y", "keys": {}, "categories": []},
                {"endpoint": "https://z", "keys": {}, "categories": []},
            ],
        }),
        encoding="utf-8",
    )
    state = read_push_store(path)
    assert state.subscription_count == 3
    assert state.vapid_public_key == "pub-key"


def test_vapid_public_only_no_private(tmp_path: Path) -> None:
    """A store can hold the public key without the private one
    (e.g. mid-rotation). The reader surfaces the public key
    regardless; the private key is never read here."""
    path = tmp_path / "karasu-push.json"
    path.write_text(
        json.dumps({
            "vapid": {"public": "only-public-set"},
            "subscriptions": [],
        }),
        encoding="utf-8",
    )
    state = read_push_store(path)
    assert state.vapid_public_key == "only-public-set"
    assert state.subscription_count == 0


# ---------------------------------------------------------------------------
# read_push_store — degradation on partial shapes
# ---------------------------------------------------------------------------


def test_subscriptions_not_a_list_degrades_to_zero(
    tmp_path: Path,
) -> None:
    """Wrong-shape ``subscriptions`` (not a list) → count=0.
    Avoids blowing up the surface on a partial / hand-edited
    store; the operator can still see the empty footer
    affordance and re-bootstrap via UI-12b."""
    path = tmp_path / "karasu-push.json"
    path.write_text(
        json.dumps({"subscriptions": "not-a-list"}),
        encoding="utf-8",
    )
    state = read_push_store(path)
    assert state.subscription_count == 0


def test_vapid_not_an_object_degrades_to_no_public_key(
    tmp_path: Path,
) -> None:
    """``vapid`` field is not a dict → public key falls to
    None rather than raising."""
    path = tmp_path / "karasu-push.json"
    path.write_text(
        json.dumps({"vapid": "not-an-object"}),
        encoding="utf-8",
    )
    state = read_push_store(path)
    assert state.vapid_public_key is None


def test_vapid_public_empty_string_yields_none(
    tmp_path: Path,
) -> None:
    """Empty-string public key is not a usable VAPID key;
    surface as None so the client renders "no key configured"
    rather than handing the OS an empty applicationServerKey."""
    path = tmp_path / "karasu-push.json"
    path.write_text(
        json.dumps({"vapid": {"public": ""}}),
        encoding="utf-8",
    )
    state = read_push_store(path)
    assert state.vapid_public_key is None


# ---------------------------------------------------------------------------
# read_push_store — error classification
# ---------------------------------------------------------------------------


def test_malformed_json_raises_push_store_error(
    tmp_path: Path,
) -> None:
    """Garbage in the file is not the same as missing — surface
    a structured error so the HTTP layer can return 500 and the
    operator notices the corruption."""
    path = tmp_path / "karasu-push.json"
    path.write_text("not really json{}", encoding="utf-8")
    with pytest.raises(PushStoreError, match="not valid JSON"):
        read_push_store(path)


def test_top_level_array_raises_push_store_error(
    tmp_path: Path,
) -> None:
    """A JSON array at root is unambiguously not a push store
    (no place for ``vapid`` / ``subscriptions``). Surface as
    a structured error rather than degrading silently."""
    path = tmp_path / "karasu-push.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(PushStoreError, match="not a JSON object"):
        read_push_store(path)


def test_top_level_scalar_raises_push_store_error(
    tmp_path: Path,
) -> None:
    """Same defensive shape as the agent card reader — a
    top-level scalar is not a valid store."""
    path = tmp_path / "karasu-push.json"
    path.write_text('"a string"', encoding="utf-8")
    with pytest.raises(PushStoreError, match="not a JSON object"):
        read_push_store(path)


def test_unreadable_store_raises_push_store_error(
    tmp_path: Path,
) -> None:
    """A store that exists but cannot be read (permission
    denied, the path is a directory, the device disappeared,
    etc.) must surface as ``PushStoreError`` so the
    ``/api/push`` handler folds it into the same structured
    500 contract as malformed JSON. Without the OSError catch
    the handler returns the bare exception trace, which leaks
    the absolute store path back to the wire and bypasses the
    generic ``{"error": "push store malformed"}`` body. Codex
    P2 on PR #98 round 1.

    Simulated via a directory at the store path: ``read_text``
    on a directory raises ``IsADirectoryError`` on POSIX or
    ``PermissionError`` on Windows; both are ``OSError``
    subclasses so the same code path catches them."""
    path = tmp_path / "karasu-push.json"
    path.mkdir()
    with pytest.raises(PushStoreError, match="could not be read"):
        read_push_store(path)


def test_invalid_utf8_store_raises_push_store_error(
    tmp_path: Path,
) -> None:
    """A store containing bytes that are not valid UTF-8
    (hand-edited with the wrong codepage, partial write that
    truncated mid-multi-byte-sequence, etc.) raises
    ``UnicodeDecodeError`` from ``read_text`` BEFORE
    ``json.loads`` ever sees the input. ``UnicodeDecodeError``
    is a ``ValueError`` subclass, NOT an ``OSError`` — without
    a dedicated catch it escapes the structured 500 path and
    reaches the wire as a bare exception trace, leaking the
    absolute store path. Codex P2 on PR #98 round 2.

    Simulated by writing bytes that are invalid as UTF-8: the
    ``\\xff`` lead byte is forbidden under UTF-8 anywhere."""
    path = tmp_path / "karasu-push.json"
    path.write_bytes(b"\xff\xfe\xfd not valid utf-8 here")
    with pytest.raises(PushStoreError, match="not valid UTF-8"):
        read_push_store(path)


# ---------------------------------------------------------------------------
# project_push_state_payload — privacy contract pin
# ---------------------------------------------------------------------------


def test_projection_keys_match_documented_response(
    tmp_path: Path,
) -> None:
    """Pin the response shape against drift. PUSH_RESPONSE_KEYS
    in the HTTP-level test is the GitHub-visible contract; this
    test pins the same shape one layer down so the unit-vs-HTTP
    pair must be updated together."""
    payload = project_push_state_payload(
        PushStoreState(
            subscription_count=2,
            vapid_public_key="pub",
            file_present=True,
        )
    )
    assert set(payload.keys()) == {
        "state",
        "categories",
        "subscription_count",
        "vapid_public_key",
    }
    assert payload["state"] == "supported"
    assert payload["categories"] == list(PUSH_CATEGORIES)
    assert payload["subscription_count"] == 2
    assert payload["vapid_public_key"] == "pub"


def test_categories_enum_is_documented_three(tmp_path: Path) -> None:
    """Pin the closed enum (UI-12 brief §3-G + §11.6.10).
    Future categories earn their own brief; this test catches
    a silent enum widening."""
    assert PUSH_CATEGORIES == ("attention", "errors", "corrections")


def test_projection_state_field_is_always_supported(
    tmp_path: Path,
) -> None:
    """Server-side ``state`` is always ``"supported"`` — the
    client owns the unsupported / denied branches via
    browser feature detection (UI-12 brief §10.9). Pin the
    server-side invariant so a future "helpful" addition
    cannot start guessing browser state from the server."""
    for count in (0, 1, 100):
        payload = project_push_state_payload(
            PushStoreState(
                subscription_count=count,
                vapid_public_key=None,
                file_present=True,
            )
        )
        assert payload["state"] == "supported"


def test_projection_does_not_carry_file_present(
    tmp_path: Path,
) -> None:
    """``file_present`` is an internal-only field; do not let
    it cross the HTTP boundary. The projection is the public
    surface."""
    payload = project_push_state_payload(
        PushStoreState(
            subscription_count=0,
            vapid_public_key=None,
            file_present=True,
        )
    )
    assert "file_present" not in payload
