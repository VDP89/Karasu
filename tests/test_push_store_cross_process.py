"""Cross-process no-lost-update test for the push_store
writer (UI-12c §3-G + forward-carry pin (d)).

The brief mandates that ``karasu ui`` (UI-12b POST handlers)
and ``karasu watch`` (UI-12c auto-VAPID-seed + 410/404 prune)
serialise their writes against ``karasu-push.json`` via the
filesystem lockfile added in UI-12c §3-G. This test spawns
real :mod:`multiprocessing` workers and verifies no
subscriptions are lost when N processes write concurrently.

Skipped silently on platforms / runners that cannot spawn
child processes (the brief mentions some restricted CI
environments).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sys
from pathlib import Path

import pytest

from karasu.ui.push_store import _read_or_empty_store


# Worker target — must be top-level (pickleable) for
# multiprocessing to spawn it across process boundaries.
def _worker_append_subscriptions(
    store_path_str: str,
    worker_id: int,
    n_subs: int,
) -> None:
    """Append ``n_subs`` distinct subscriptions to the store
    via the public writer API. Each subscription's endpoint
    is keyed on (worker_id, sub_index) so we can later count
    every entry without confusing one worker's writes with
    another's."""
    # Re-import inside the worker — multiprocessing on Windows
    # spawns a fresh interpreter that doesn't inherit the
    # parent's imports.
    from pathlib import Path as P

    from karasu.ui.push_store import append_subscription

    store_path = P(store_path_str)
    for i in range(n_subs):
        endpoint = (
            f"https://example.test/push/worker-{worker_id}-sub-{i}"
        )
        append_subscription(
            store_path,
            subscription={
                "endpoint": endpoint,
                "keys": {"p256dh": "p", "auth": "a"},
            },
            categories=["attention"],
        )


def _multiprocessing_available() -> bool:
    """Check whether the runner can spawn workers.

    Some restricted CI environments (notably containerised
    runners with PR_SET_NO_NEW_PRIVS or similar) reject
    process creation. Guard with a smoke spawn before
    committing to the real test."""
    try:
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(target=_smoke_target)
        proc.start()
        proc.join(timeout=5.0)
        return proc.exitcode == 0
    except Exception:
        return False


def _smoke_target() -> None:
    pass


@pytest.mark.skipif(
    not _multiprocessing_available(),
    reason="runner cannot spawn child processes",
)
def test_two_processes_no_lost_update(tmp_path: Path) -> None:
    """Two workers × 8 subscriptions each = 16 final entries.
    Without the cross-process file lock, the second writer's
    rename would clobber the first's subscriptions list under
    a contended schedule."""
    store_path = tmp_path / "karasu-push.json"
    n_workers = 2
    n_per_worker = 8

    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(
            target=_worker_append_subscriptions,
            args=(str(store_path), worker_id, n_per_worker),
        )
        for worker_id in range(n_workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30.0)
        assert p.exitcode == 0, (
            f"worker exited with {p.exitcode}"
        )

    raw = _read_or_empty_store(store_path)
    subs = raw.get("subscriptions") or []
    assert len(subs) == n_workers * n_per_worker

    # Each worker's writes are all present.
    endpoints = {entry["endpoint"] for entry in subs}
    expected = {
        f"https://example.test/push/worker-{w}-sub-{i}"
        for w in range(n_workers)
        for i in range(n_per_worker)
    }
    assert endpoints == expected


@pytest.mark.skipif(
    not _multiprocessing_available(),
    reason="runner cannot spawn child processes",
)
@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason=(
        "Windows multiprocessing spawn cost makes a 4×16 "
        "stress test slow; the 2×8 case above already proves "
        "the cross-process lock works."
    ),
)
def test_four_processes_stress_no_lost_update(tmp_path: Path) -> None:
    """Brief §3-G stress shape: 4 processes × 16 subscriptions
    each = 64 final entries. Skipped on Windows (slow spawn)
    but exercised on POSIX CI."""
    store_path = tmp_path / "karasu-push.json"
    n_workers = 4
    n_per_worker = 16

    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(
            target=_worker_append_subscriptions,
            args=(str(store_path), worker_id, n_per_worker),
        )
        for worker_id in range(n_workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60.0)
        assert p.exitcode == 0

    raw = _read_or_empty_store(store_path)
    subs = raw.get("subscriptions") or []
    assert len(subs) == n_workers * n_per_worker


# ---------------------------------------------------------------------------
# In-process test still passes (UI-12b regression check)
# ---------------------------------------------------------------------------


def test_existing_threaded_writer_still_serialises(tmp_path: Path) -> None:
    """The UI-12b 16-thread no-lost-update test (in
    test_ui_push_store.py) covers the in-process path. This
    is a quick smoke that a single-thread sequential write
    still works — the cross-process lock layered over the
    in-process Lock did not break the simple case."""
    from karasu.ui.push_store import append_subscription

    store_path = tmp_path / "karasu-push.json"
    for i in range(5):
        append_subscription(
            store_path,
            subscription={
                "endpoint": f"https://example.test/push/{i}",
                "keys": {"p256dh": "p", "auth": "a"},
            },
            categories=["attention"],
        )

    raw = _read_or_empty_store(store_path)
    assert len(raw["subscriptions"]) == 5
