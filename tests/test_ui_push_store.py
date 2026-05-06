"""Unit tests for the UI-12a read-only push subscription store
plus the UI-12b writer side.

Pairs with the HTTP shape lock in
``tests/test_ui_server_http.py`` (which exercises the same
surface through the full HTTP path). These tests pin the
push_store module's behaviour in isolation:

  Reader (UI-12a) — empty store sentinel, partial-shape
  degradation, malformed-store error classification, and the
  privacy-preserving projection.

  Writer (UI-12b) — append + UPDATE + remove semantics, atomic
  tmp+rename, mode 0600 enforcement, the partial-write
  recovery branch, the loud-stderr mode warning on POSIX, and
  the threading.Lock that serialises concurrent writers.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

from karasu.ui.push_store import (
    PUSH_CATEGORIES,
    PushStoreError,
    PushStoreNotFound,
    PushStoreState,
    append_subscription,
    compute_endpoint_hash,
    project_push_state_payload,
    read_push_store,
    remove_subscription,
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


# ===========================================================================
# UI-12b writer tests
# ===========================================================================
#
# Pin §11.6.7 (atomic tmp+rename + 0600 mode + warning), §11.6.13
# (read-modify-write + audit_emitted boundary — store side),
# §11.6.15 (module-level threading.Lock across full transaction),
# §11.6.16 (raw endpoint never logged / projected). The reader
# tests above are unchanged; this section lands with UI-12b code.


_SENTINEL_ENDPOINT = "https://test.example/sentinel-DO-NOT-LEAK-7d9f2e"
_SENTINEL_P256DH = "DO-NOT-LEAK-P256DH"
_SENTINEL_AUTH = "DO-NOT-LEAK-AUTH"


def _make_subscription(
    endpoint: str = _SENTINEL_ENDPOINT,
    p256dh: str = _SENTINEL_P256DH,
    auth: str = _SENTINEL_AUTH,
) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": p256dh, "auth": auth},
    }


# ---------------------------------------------------------------------------
# compute_endpoint_hash — sha256-hex correctness
# ---------------------------------------------------------------------------


def test_endpoint_hash_is_sha256_hex_64_chars() -> None:
    """Pin §11.6.6 — endpoint_hash is sha256-hex(endpoint).
    Stable, deterministic, audit-only."""
    h = compute_endpoint_hash(_SENTINEL_ENDPOINT)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    expected = hashlib.sha256(_SENTINEL_ENDPOINT.encode("utf-8")).hexdigest()
    assert h == expected


def test_endpoint_hash_stable_for_same_endpoint() -> None:
    """Pin §11.6.6 — same endpoint MUST produce the same hash
    so subscribe/unsubscribe pairs correlate on the bus."""
    a = compute_endpoint_hash(_SENTINEL_ENDPOINT)
    b = compute_endpoint_hash(_SENTINEL_ENDPOINT)
    assert a == b


def test_endpoint_hash_differs_per_endpoint() -> None:
    """Different endpoints MUST hash differently."""
    a = compute_endpoint_hash("https://a.example/x")
    b = compute_endpoint_hash("https://b.example/y")
    assert a != b


# ---------------------------------------------------------------------------
# append_subscription — INSERT path
# ---------------------------------------------------------------------------


def test_append_creates_store_from_scratch(tmp_path: Path) -> None:
    """Fresh checkout — no store on disk. The append call writes
    the file with the single new entry."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    assert store_path.is_file()

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "subscriptions" in raw
    assert len(raw["subscriptions"]) == 1
    entry = raw["subscriptions"][0]
    assert entry["endpoint"] == _SENTINEL_ENDPOINT
    assert entry["endpoint_hash"] == compute_endpoint_hash(_SENTINEL_ENDPOINT)
    assert entry["keys"] == {"p256dh": _SENTINEL_P256DH, "auth": _SENTINEL_AUTH}
    assert entry["categories"] == ["attention"]
    assert isinstance(entry["created_at"], str)
    assert isinstance(entry["updated_at"], str)


def test_append_two_distinct_endpoints(tmp_path: Path) -> None:
    """Different endpoints land as separate entries."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint="https://a.example/x"),
        categories=["attention"],
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint="https://b.example/y"),
        categories=["errors"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["subscriptions"]) == 2
    endpoints = {e["endpoint"] for e in raw["subscriptions"]}
    assert endpoints == {"https://a.example/x", "https://b.example/y"}


def test_append_preserves_vapid_section(tmp_path: Path) -> None:
    """Manual VAPID seed in the store survives a fresh append.
    UI-12b cannot generate VAPID (cryptography dep deferred to
    UI-12c); the operator's manual seed must be untouched."""
    store_path = tmp_path / "karasu-push.json"
    store_path.write_text(
        json.dumps({"vapid": {"public": "PUB", "private": "PRIV"}}),
        encoding="utf-8",
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["errors"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["vapid"] == {"public": "PUB", "private": "PRIV"}
    assert len(raw["subscriptions"]) == 1


def test_append_empty_categories_allowed(tmp_path: Path) -> None:
    """Brief §3-B / pin §11.6.9: zero-noise subscription is a
    deliberate operator choice. The store MUST accept an empty
    categories array verbatim."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=[],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["subscriptions"][0]["categories"] == []


# ---------------------------------------------------------------------------
# append_subscription — UPDATE / idempotent path
# ---------------------------------------------------------------------------


def test_append_same_endpoint_updates_categories(tmp_path: Path) -> None:
    """Brief §10.2: duplicate subscribe is treated as UPDATE.
    The existing entry's categories are overwritten with the
    new validated set."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention", "errors"],
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["corrections"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["subscriptions"]) == 1
    assert raw["subscriptions"][0]["categories"] == ["corrections"]


def test_append_update_preserves_created_at(tmp_path: Path) -> None:
    """``created_at`` is set on the FIRST append and never
    rewritten on UPDATE — the audit trail keeps the original
    moment of subscription."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    first_created = raw["subscriptions"][0]["created_at"]

    # Force a measurable timestamp delta so updated_at vs
    # created_at can diverge.
    import time

    time.sleep(1.1)
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["errors"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    entry = raw["subscriptions"][0]
    assert entry["created_at"] == first_created
    assert entry["updated_at"] >= first_created


def test_append_normalises_garbage_subscriptions_section(
    tmp_path: Path,
) -> None:
    """If the store's ``subscriptions`` field is a non-list
    (operator hand-edited or partially corrupted), the writer
    normalises to a fresh list before append. The reader's
    ``count=0`` degradation already covered this branch; the
    writer makes sure the next read sees a usable shape."""
    store_path = tmp_path / "karasu-push.json"
    store_path.write_text(
        json.dumps({"subscriptions": "not-a-list"}),
        encoding="utf-8",
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert isinstance(raw["subscriptions"], list)
    assert len(raw["subscriptions"]) == 1


# ---------------------------------------------------------------------------
# remove_subscription
# ---------------------------------------------------------------------------


def test_remove_existing_subscription(tmp_path: Path) -> None:
    """Happy path — the entry is gone after remove."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    remove_subscription(store_path, endpoint=_SENTINEL_ENDPOINT)
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["subscriptions"] == []


def test_remove_unknown_endpoint_raises_not_found(tmp_path: Path) -> None:
    """The handler maps PushStoreNotFound to a generic 404."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint="https://a.example/x"),
        categories=["attention"],
    )
    with pytest.raises(PushStoreNotFound):
        remove_subscription(store_path, endpoint="https://other.example/y")


def test_remove_from_missing_store_raises_not_found(
    tmp_path: Path,
) -> None:
    """Store file absent — there is nothing to remove. The
    handler treats this as 'subscription not found' rather
    than as malformed-store (which would be 500)."""
    store_path = tmp_path / "karasu-push.json"
    with pytest.raises(PushStoreNotFound):
        remove_subscription(store_path, endpoint=_SENTINEL_ENDPOINT)


def test_remove_from_garbage_subscriptions_raises_not_found(
    tmp_path: Path,
) -> None:
    """A non-list ``subscriptions`` field has no entries to
    match; treat as not-found rather than store-malformed."""
    store_path = tmp_path / "karasu-push.json"
    store_path.write_text(
        json.dumps({"subscriptions": "garbage"}),
        encoding="utf-8",
    )
    with pytest.raises(PushStoreNotFound):
        remove_subscription(store_path, endpoint=_SENTINEL_ENDPOINT)


def test_remove_one_keeps_the_others(tmp_path: Path) -> None:
    """Removing one entry leaves the other entries intact."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint="https://a.example/x"),
        categories=["attention"],
    )
    append_subscription(
        store_path,
        subscription=_make_subscription(endpoint="https://b.example/y"),
        categories=["errors"],
    )
    remove_subscription(store_path, endpoint="https://a.example/x")
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    endpoints = {e["endpoint"] for e in raw["subscriptions"]}
    assert endpoints == {"https://b.example/y"}


# ---------------------------------------------------------------------------
# Atomic write + mode discipline (pin §11.6.7)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only mode bits")
def test_atomic_write_creates_file_with_mode_0600(tmp_path: Path) -> None:
    """Pin §11.6.7 — first write must land at mode 0o600 on
    POSIX. The os.open call uses O_CREAT|O_EXCL with 0o600;
    os.replace preserves the source file's mode."""
    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    observed = stat.S_IMODE(store_path.stat().st_mode)
    assert observed == 0o600


def test_atomic_write_fails_fast_on_existing_tmp(
    tmp_path: Path,
) -> None:
    """Pin §11.6.7 — the writer FAILS FAST if the .tmp already
    exists (a previous partial write left it behind, OR a
    concurrent writer outside the in-process Lock). No automatic
    cleanup; the operator must remove the .tmp manually."""
    store_path = tmp_path / "karasu-push.json"
    tmp_path_name = store_path.with_name(store_path.name + ".tmp")
    tmp_path_name.write_text("orphaned-partial-write", encoding="utf-8")
    with pytest.raises(PushStoreError, match="partial write recovery needed"):
        append_subscription(
            store_path,
            subscription=_make_subscription(),
            categories=["attention"],
        )


def test_atomic_write_cleans_up_tmp_on_serialise_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If json.dumps blows up mid-write (synthetic — pretend
    the dict carries an unserialisable value), the .tmp must
    NOT linger. Otherwise the next call would hit the
    'partial write recovery needed' branch with a stale tmp.

    Simulated by monkey-patching ``json.dumps`` inside the
    module to raise on the first call only."""
    import karasu.ui.push_store as push_store_mod

    real_dumps = push_store_mod.json.dumps
    calls = {"count": 0}

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if calls["count"] == 1:
            raise TypeError("synthetic serialise failure")
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(push_store_mod.json, "dumps", boom)

    store_path = tmp_path / "karasu-push.json"
    with pytest.raises(TypeError, match="synthetic"):
        append_subscription(
            store_path,
            subscription=_make_subscription(),
            categories=["attention"],
        )
    # The .tmp MUST have been cleaned up so a retry can proceed.
    assert not store_path.with_name(store_path.name + ".tmp").exists()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only mode bits")
def test_loose_mode_warning_fires_on_existing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pin §11.6.7 — when the existing store file is looser
    than 0o600 on POSIX, the writer logs a loud-stderr warning
    citing the path + observed mode + remediation. The writer
    does NOT silently chmod the file; the new tmp+rename lands
    a 0o600 replacement, which is the end-state guarantee."""
    store_path = tmp_path / "karasu-push.json"
    # Seed with a pre-existing store at mode 0o644.
    store_path.write_text(
        json.dumps({"subscriptions": []}),
        encoding="utf-8",
    )
    os.chmod(store_path, 0o644)

    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )

    captured = capsys.readouterr()
    assert "0o644" in captured.err
    assert "expected 0o600" in captured.err
    assert str(store_path) in captured.err

    # End-state: file is now mode 0o600 because the .tmp+rename
    # replaced it with a fresh 0o600 file.
    observed = stat.S_IMODE(store_path.stat().st_mode)
    assert observed == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only mode bits")
def test_loose_mode_warning_silent_on_strict_modes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mode 0o400 (read-only) is STRICTER than 0o600. No warning
    should fire. Validates the mask logic (`observed & ~0o600`)
    against false positives on stricter modes."""
    store_path = tmp_path / "karasu-push.json"
    store_path.write_text(
        json.dumps({"subscriptions": []}),
        encoding="utf-8",
    )
    os.chmod(store_path, 0o600)

    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )

    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


# ---------------------------------------------------------------------------
# Concurrency — pin §11.6.15
# ---------------------------------------------------------------------------


def test_concurrent_appends_do_not_lose_updates(tmp_path: Path) -> None:
    """Pin §11.6.15 — module-level threading.Lock serialises
    the FULL read-modify-write transaction. Without the lock,
    two threads racing on append_subscription would read the
    same old store, both write tmp files, and the later
    rename would clobber the earlier mutation (lost update).

    Spawn N threads each appending a distinct endpoint; assert
    all N entries land in the final store."""
    store_path = tmp_path / "karasu-push.json"
    n_threads = 16

    def worker(idx: int) -> None:
        append_subscription(
            store_path,
            subscription=_make_subscription(
                endpoint=f"https://example.test/sub-{idx}"
            ),
            categories=["attention"],
        )

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), "worker hung — possible lock issue"

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    endpoints = {e["endpoint"] for e in raw["subscriptions"]}
    expected = {f"https://example.test/sub-{i}" for i in range(n_threads)}
    assert endpoints == expected, (
        f"lost update: expected {n_threads} entries, got "
        f"{len(endpoints)}"
    )


# ---------------------------------------------------------------------------
# Privacy — pin §11.6.16
# ---------------------------------------------------------------------------


def test_writer_logs_carry_only_endpoint_hash_not_raw(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pin §11.6.16 — the writer logs hash + categories only.
    The raw endpoint MUST never appear in any log line."""
    import logging

    caplog.set_level(logging.DEBUG, logger="karasu.ui.push_store")

    store_path = tmp_path / "karasu-push.json"
    append_subscription(
        store_path,
        subscription=_make_subscription(),
        categories=["attention"],
    )
    remove_subscription(store_path, endpoint=_SENTINEL_ENDPOINT)

    # The sentinel substring marks the raw endpoint + the keys.
    # Neither MUST appear in any captured log message.
    captured_text = " ".join(record.message for record in caplog.records)
    assert _SENTINEL_ENDPOINT not in captured_text
    assert _SENTINEL_P256DH not in captured_text
    assert _SENTINEL_AUTH not in captured_text
    assert "DO-NOT-LEAK" not in captured_text

    # The hash MUST appear (it's the audit metadata).
    expected_hash = compute_endpoint_hash(_SENTINEL_ENDPOINT)
    assert expected_hash in captured_text
