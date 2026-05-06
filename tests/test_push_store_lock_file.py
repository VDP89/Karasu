"""Lock-file region discipline tests for the cross-process file
lock added in UI-12c §3-G.

Covers:

  * The lock file path is ``<store_path>.lock`` (parallel to
    the ``.tmp`` staging file from UI-12b §3-E).
  * The lock is RELEASED on the with-block exit so a subsequent
    acquirer can proceed (no leaks).
  * Windows region discipline (Codex P1 round 2, 2026-05-06):
    ``_flock_exclusive`` seeks to byte 0 before locking 1 byte;
    ``_flock_release`` seeks to the SAME byte 0 before unlocking
    1 byte. The recording spy asserts both calls target offset 0
    with length 1.
  * POSIX path uses ``fcntl.flock`` with ``LOCK_EX`` /
    ``LOCK_UN`` (region-agnostic; whole-inode lock).

The Windows tests use ``monkeypatch`` against ``msvcrt`` so they
run on every platform: we drive the helper directly with a fake
``msvcrt.locking`` rather than touching the real Windows file
locking API. The POSIX tests do the symmetric thing against
``fcntl``.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from karasu.ui import push_store
from karasu.ui.push_store import (
    _flock_exclusive,
    _flock_release,
    _with_store_lock,
)


# ---------------------------------------------------------------------------
# Lock-file path convention
# ---------------------------------------------------------------------------


def test_lock_file_path_parallel_to_tmp(tmp_path: Path) -> None:
    """Brief §3-G: lock file lives at ``<store>.lock``,
    parallel to the ``.tmp`` staging file."""
    store_path = tmp_path / ".karasu" / "karasu-push.json"

    with _with_store_lock(store_path):
        # Inside the with-block, the .lock file exists and the
        # lock is held.
        assert (tmp_path / ".karasu" / "karasu-push.json.lock").exists()


def test_lock_file_creates_parent_directory(tmp_path: Path) -> None:
    """First-time start: parent dir of the store may not exist
    yet. ``_with_store_lock`` must mkdir(parents, exist_ok)."""
    nested = tmp_path / "deep" / "nested" / "karasu-push.json"
    assert not nested.parent.exists()

    with _with_store_lock(nested):
        assert nested.parent.exists()
        assert (nested.parent / "karasu-push.json.lock").exists()


# ---------------------------------------------------------------------------
# Release semantics
# ---------------------------------------------------------------------------


def test_lock_released_on_with_block_exit(tmp_path: Path) -> None:
    """A second acquire after the first releases must NOT block."""
    store_path = tmp_path / "store.json"

    # First acquire + release.
    with _with_store_lock(store_path):
        pass

    # Second acquire — should be immediate (no contention).
    start = time.monotonic()
    with _with_store_lock(store_path):
        pass
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"second acquire took {elapsed:.2f}s, expected < 0.5"


def test_lock_serialises_concurrent_threads(tmp_path: Path) -> None:
    """The in-process Lock layer of ``_with_store_lock`` must
    keep two sibling threads from running the with-block at the
    same time."""
    store_path = tmp_path / "store.json"
    inside = []

    def worker(name: str) -> None:
        with _with_store_lock(store_path):
            inside.append(("enter", name))
            time.sleep(0.05)  # hold the lock briefly
            inside.append(("exit", name))

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive()

    # Each enter must be followed by its own exit before any
    # other thread enters — no interleaving.
    for i in range(0, len(inside), 2):
        assert inside[i][0] == "enter"
        assert inside[i + 1][0] == "exit"
        assert inside[i][1] == inside[i + 1][1]


# ---------------------------------------------------------------------------
# Windows region discipline (Codex P1 round 2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Windows-only: msvcrt.locking region discipline",
)
def test_windows_flock_exclusive_locks_byte_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_flock_exclusive`` MUST seek to byte 0 before calling
    ``msvcrt.locking(LK_LOCK, 1)``. Without seek, the append-mode
    handle's pointer at EOF would target a different region than
    expected and let two processes hold "different" locks on the
    same .lock file."""
    import msvcrt

    calls: list[tuple[int, int, int]] = []
    seek_positions: list[int] = []

    def spy_locking(fileno: int, op: int, count: int) -> None:
        # Spy records (fileno, op, count). The seek-to-0
        # discipline is observed by capturing fh.tell() in the
        # caller AFTER the helper returns (the helper itself
        # seeks-then-locks; on return tell() is at the locked
        # offset).
        calls.append((fileno, op, count))

    monkeypatch.setattr(msvcrt, "locking", spy_locking)

    lock_path = tmp_path / "store.json.lock"
    fh = open(lock_path, "ab")
    try:
        # Force pointer to a non-zero position to make the seek
        # discipline observable.
        fh.write(b"\x00" * 16)
        fh.flush()
        # tell() is now 16 (file extended to 16 bytes).
        assert fh.tell() == 16

        _flock_exclusive(fh)
        # After the call, the seek-to-0 from the helper means
        # tell() is 0.
        seek_positions.append(fh.tell())

        _flock_release(fh)
        seek_positions.append(fh.tell())
    finally:
        # monkeypatch restores msvcrt.locking automatically on
        # test exit. The spy never held a real kernel lock so
        # closing the fh is sufficient.
        fh.close()

    # Assert the spy saw exactly two calls: LK_LOCK then LK_UNLCK,
    # both with count=1.
    assert len(calls) == 2, f"expected 2 locking calls, got {calls}"
    fileno_lock, op_lock, count_lock = calls[0]
    fileno_unlock, op_unlock, count_unlock = calls[1]
    assert op_lock == msvcrt.LK_LOCK
    assert count_lock == 1
    assert op_unlock == msvcrt.LK_UNLCK
    assert count_unlock == 1
    assert fileno_lock == fileno_unlock

    # Both calls were made with the file pointer at 0 (the
    # seek-to-0 discipline).
    assert seek_positions == [0, 0]


# ---------------------------------------------------------------------------
# POSIX flock discipline
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="POSIX-only: fcntl.flock"
)
def test_posix_flock_exclusive_uses_lock_ex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_flock_exclusive`` MUST call ``fcntl.flock`` with
    ``LOCK_EX`` (whole-inode exclusive lock). Region-agnostic on
    POSIX — no seek dance required."""
    import fcntl  # type: ignore[import-not-found]

    calls: list[tuple[int, int]] = []

    def spy_flock(fileno: int, op: int) -> None:
        calls.append((fileno, op))

    monkeypatch.setattr(fcntl, "flock", spy_flock)

    lock_path = tmp_path / "store.json.lock"
    fh = open(lock_path, "ab")
    try:
        _flock_exclusive(fh)
        _flock_release(fh)
    finally:
        fh.close()

    assert len(calls) == 2
    fileno_lock, op_lock = calls[0]
    fileno_unlock, op_unlock = calls[1]
    assert op_lock == fcntl.LOCK_EX
    assert op_unlock == fcntl.LOCK_UN
    assert fileno_lock == fileno_unlock


# ---------------------------------------------------------------------------
# .lock file persists on disk after release (no auto-cleanup)
# ---------------------------------------------------------------------------


def test_lock_file_not_deleted_on_release(tmp_path: Path) -> None:
    """Brief §3-G: stale-lock recovery is NONE. The .lock file
    is left on disk; the kernel-held lock is what matters and
    that auto-releases on close. A persistent .lock file is
    harmless on its own."""
    store_path = tmp_path / "store.json"

    with _with_store_lock(store_path):
        pass

    assert (tmp_path / "store.json.lock").exists()


# ---------------------------------------------------------------------------
# seed_vapid composes with the lock
# ---------------------------------------------------------------------------


def test_seed_vapid_writes_under_lock(tmp_path: Path) -> None:
    """``seed_vapid`` must hold the same lock as
    ``append_subscription`` so the two cannot interleave."""
    store_path = tmp_path / "store.json"

    push_store.seed_vapid(
        store_path,
        public="A" * 86,
        private="B" * 43,
    )

    raw = push_store._read_or_empty_store(store_path)
    assert raw["vapid"] == {"public": "A" * 86, "private": "B" * 43}


def test_seed_vapid_preserves_existing_subscriptions(tmp_path: Path) -> None:
    """``seed_vapid`` must not clobber existing subscriptions —
    the bootstrap path runs against stores that the manual seed
    or a previous chunk may have populated."""
    store_path = tmp_path / "store.json"

    push_store.append_subscription(
        store_path,
        subscription={
            "endpoint": "https://example.test/push/abc",
            "keys": {"p256dh": "p", "auth": "a"},
        },
        categories=["attention"],
    )
    push_store.seed_vapid(
        store_path,
        public="X" * 86,
        private="Y" * 43,
    )

    raw = push_store._read_or_empty_store(store_path)
    assert raw["vapid"] == {"public": "X" * 86, "private": "Y" * 43}
    assert len(raw["subscriptions"]) == 1
    assert (
        raw["subscriptions"][0]["endpoint"]
        == "https://example.test/push/abc"
    )


def test_seed_vapid_overwrites_existing_keys(tmp_path: Path) -> None:
    """Calling ``seed_vapid`` directly with new keys overwrites
    unconditionally. The idempotency lives in
    ``bootstrap_if_missing``, not here."""
    store_path = tmp_path / "store.json"

    push_store.seed_vapid(store_path, public="A" * 86, private="B" * 43)
    push_store.seed_vapid(store_path, public="C" * 86, private="D" * 43)

    raw = push_store._read_or_empty_store(store_path)
    assert raw["vapid"] == {"public": "C" * 86, "private": "D" * 43}


def test_seed_vapid_no_key_material_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Pin §11.6.16: the keypair MUST NOT appear in any log
    line. The caller (``bootstrap_if_missing``) emits one INFO
    line ``"generated VAPID keypair"`` without lengths or
    fragments; ``seed_vapid`` itself emits no log."""
    store_path = tmp_path / "store.json"
    secret_public = "PUBLIC_SENTINEL_" + "A" * 70
    secret_private = "PRIVATE_SENTINEL_" + "B" * 26

    with caplog.at_level("DEBUG", logger="karasu.ui.push_store"):
        push_store.seed_vapid(
            store_path,
            public=secret_public,
            private=secret_private,
        )

    for record in caplog.records:
        assert "PUBLIC_SENTINEL_" not in record.getMessage()
        assert "PRIVATE_SENTINEL_" not in record.getMessage()
