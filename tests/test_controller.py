"""Tests for LoopController (Phase 3 chunk 3a).

The controller is a refactor wrapper. Existing watcher tests continue
to exercise the controller indirectly because ``FilesystemWatcher``
now delegates queue + worker management to it. These tests cover the
controller in isolation and prove parity with the direct-call path.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import pytest

from karasu.controller import LoopController
from karasu.eventbus import Event, JsonlEventBus
from karasu.watcher import FilesystemWatcher


def _event(path: str, change_type: str = "modified") -> Event:
    return Event(
        type="file_change",
        source="watcher",
        data={"path": path, "change_type": change_type},
    )


# ---------------------------------------------------------------------------
# Synchronous fallback — submit before start
# ---------------------------------------------------------------------------


def test_submit_invokes_callback_synchronously_when_not_started() -> None:
    seen: list[str] = []
    controller = LoopController(lambda e: seen.append(e.data["path"]))

    controller.submit(_event("a.py"))
    controller.submit(_event("b.py"))

    # No worker started — callback runs inline on the submitter's thread.
    assert seen == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# Lifecycle — start / stop
# ---------------------------------------------------------------------------


def test_start_spawns_a_single_worker_thread() -> None:
    controller = LoopController(lambda e: None)
    controller.start()
    try:
        assert controller._worker is not None
        assert controller._worker.is_alive()
        assert controller._worker.daemon is True
        assert controller._queue is not None
    finally:
        controller.stop()


def test_stop_joins_worker_cleanly() -> None:
    controller = LoopController(lambda e: None)
    controller.start()
    worker = controller._worker
    assert worker is not None

    controller.stop(timeout=2.0)

    assert not worker.is_alive()
    assert controller._worker is None
    assert controller._queue is None
    assert controller._stopping is None


def test_stop_is_idempotent_when_never_started() -> None:
    controller = LoopController(lambda e: None)
    # Should not raise.
    controller.stop()


# ---------------------------------------------------------------------------
# Submission — order preservation
# ---------------------------------------------------------------------------


def test_submit_processes_events_in_order_through_worker() -> None:
    seen: list[str] = []
    controller = LoopController(lambda e: seen.append(e.data["path"]))
    controller.start()
    try:
        for i in range(10):
            controller.submit(_event(f"f{i}.py"))
        assert controller._queue is not None
        controller._queue.join()
    finally:
        controller.stop()

    assert seen == [f"f{i}.py" for i in range(10)]


# ---------------------------------------------------------------------------
# Bounded queue — overflow drops with warning
# ---------------------------------------------------------------------------


def test_full_queue_drops_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    started = threading.Event()
    proceed = threading.Event()
    seen: list[str] = []

    def slow(event: Event) -> None:
        started.set()
        proceed.wait(timeout=5.0)
        seen.append(event.data["path"])

    controller = LoopController(slow, queue_size=1)
    controller.start()
    try:
        controller.submit(_event("first.py"))
        assert started.wait(timeout=1.0), "worker never picked up the first event"
        # Queue is now empty; second event lands in the (size=1) queue.
        controller.submit(_event("second.py"))
        # Third event: queue is full, must be dropped with a warning.
        with caplog.at_level("WARNING", logger="karasu.controller.loop"):
            controller.submit(_event("third.py"))

        assert any("queue full" in r.message for r in caplog.records)
        proceed.set()
        assert controller._queue is not None
        controller._queue.join()

        assert seen == ["first.py", "second.py"]
    finally:
        proceed.set()
        controller.stop()


# ---------------------------------------------------------------------------
# Crash containment — callback exceptions don't kill the worker
# ---------------------------------------------------------------------------


def test_callback_exception_is_swallowed_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    def boom(event: Event) -> None:
        calls.append(1)
        raise RuntimeError("boom")

    controller = LoopController(boom)
    controller.start()
    try:
        with caplog.at_level("ERROR", logger="karasu.controller.loop"):
            controller.submit(_event("a.py"))
            controller.submit(_event("b.py"))
            assert controller._queue is not None
            controller._queue.join()
    finally:
        controller.stop()

    assert calls == [1, 1]
    assert any("controller callback failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Restart safety — refuse while old worker still alive, recover after
# ---------------------------------------------------------------------------


def test_start_refuses_restart_while_old_worker_alive() -> None:
    unblock = threading.Event()

    def hang(event: Event) -> None:
        unblock.wait(timeout=10.0)

    controller = LoopController(hang)
    controller.start()
    try:
        controller.submit(_event("a.py"))
        deadline = time.monotonic() + 1.0
        assert controller._queue is not None
        while controller._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        controller.stop(timeout=0.2)
        old = controller._worker
        assert old is not None and old.is_alive()

        with pytest.raises(RuntimeError, match="still alive"):
            controller.start()
    finally:
        unblock.set()
        if controller._worker is not None:
            controller._worker.join(timeout=2.0)


def test_start_recovers_after_old_worker_exits() -> None:
    unblock = threading.Event()

    def hang(event: Event) -> None:
        unblock.wait(timeout=10.0)

    controller = LoopController(hang)
    controller.start()
    controller.submit(_event("a.py"))
    deadline = time.monotonic() + 1.0
    assert controller._queue is not None
    while controller._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    controller.stop(timeout=0.2)
    old = controller._worker
    assert old is not None and old.is_alive()

    unblock.set()
    old.join(timeout=2.0)
    assert not old.is_alive()

    controller.callback = lambda e: None
    controller.start()
    try:
        assert controller._worker is not None
        assert controller._worker is not old
        assert controller._worker.is_alive()
    finally:
        controller.stop()


def test_stop_timeout_abandons_hang_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unblock = threading.Event()

    def hang(event: Event) -> None:
        unblock.wait(timeout=10.0)

    controller = LoopController(hang)
    controller.start()
    try:
        controller.submit(_event("a.py"))
        deadline = time.monotonic() + 1.0
        assert controller._queue is not None
        while controller._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        start = time.monotonic()
        with caplog.at_level("WARNING", logger="karasu.controller.loop"):
            controller.stop(timeout=0.3)
        elapsed = time.monotonic() - start

        assert elapsed < 1.5
        assert any("did not exit" in r.message for r in caplog.records)
    finally:
        unblock.set()


# ---------------------------------------------------------------------------
# Parity — controller-mediated dispatch matches direct callback invocation
# ---------------------------------------------------------------------------


class _FakeFsEvent:
    def __init__(self, path: str, event_type: str = "modified") -> None:
        self.src_path = path
        self.event_type = event_type
        self.is_directory = False


def test_watcher_through_controller_matches_direct_pipeline_calls(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    """Parity: events flowing through the controller produce the same
    callback sequence as direct synchronous invocation.

    The pipeline is the production callback. We use a list-append
    spy in its place so we can compare order and count without
    pulling the dispatcher / classifier into this test.
    """
    direct_seen: list[str] = []
    via_controller_seen: list[str] = []

    direct_callback = lambda e: direct_seen.append(e.data["path"])  # noqa: E731
    via_controller_callback = lambda e: via_controller_seen.append(e.data["path"])  # noqa: E731

    # Path 1 — synchronous, same callback the watcher would invoke
    # if there were no worker thread at all.
    direct_bus = JsonlEventBus(tmp_path / "direct.jsonl")
    files = [tmp_path / f"f{i}.py" for i in range(8)]
    for f in files:
        f.write_text("")
    for f in files:
        ev = direct_bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": f.name, "change_type": "modified"},
            )
        )
        direct_callback(ev)

    # Path 2 — through the watcher + controller pipeline.
    controller_bus = JsonlEventBus(tmp_path / "controller.jsonl")
    controller = LoopController(via_controller_callback)
    watcher = FilesystemWatcher(
        root=tmp_path,
        bus=controller_bus,
        controller=controller,
    )
    watcher.start_pipeline()
    try:
        for f in files:
            watcher._dispatch(_FakeFsEvent(str(f)))
        assert controller._queue is not None
        controller._queue.join()
    finally:
        watcher.stop_pipeline()

    # Same paths, same order — the controller does not reorder or
    # drop events under nominal load.
    assert direct_seen == via_controller_seen
    # Bus events written by the watcher match the synchronous path
    # in count and (path, change_type) shape.
    direct_events = [
        (e.type, e.data.get("path"), e.data.get("change_type"))
        for e in direct_bus.read()
    ]
    controller_events = [
        (e.type, e.data.get("path"), e.data.get("change_type"))
        for e in controller_bus.read()
    ]
    assert direct_events == controller_events


# ---------------------------------------------------------------------------
# Phase 3 chunk 3b — bus subscription + reaction
# ---------------------------------------------------------------------------


def _seed_chain(
    bus: JsonlEventBus, path: str = "sample.py"
) -> tuple[Event, Event]:
    """Append a file_change → agent_response chain. Returns (file_change, agent_response)."""
    file_change = bus.append(
        Event(
            type="file_change",
            source="watcher",
            data={"path": path, "change_type": "modified"},
        )
    )
    agent_response = bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"correlates": file_change.id, "path": path},
            dispatch={"agent": "claude_code", "status": "completed"},
            response={"content": "ok", "requires_human": False},
        )
    )
    return file_change, agent_response


def test_on_bus_event_ignores_non_human_decision(bus: JsonlEventBus) -> None:
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    # No reaction expected for these — the controller's submit
    # callback should not fire.
    controller.on_bus_event(
        Event(type="file_change", source="watcher", data={"path": "x.py"}),
        bus,
    )
    controller.on_bus_event(
        Event(type="agent_response", source="adapter", data={"path": "x.py"}),
        bus,
    )
    assert seen == []


def test_on_bus_event_skips_redacted_human_decision(bus: JsonlEventBus) -> None:
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    for redacted_text in (
        "/correct (unauthorized)",
        "/scar (unauthorized)",
        "/correct (unknown command)",
    ):
        controller.on_bus_event(
            Event(
                type="human_decision",
                source="interface",
                data={"user": 1, "text": redacted_text},
            ),
            bus,
        )

    # Surface already rejected the write; controller does not react.
    assert seen == []


def test_on_bus_event_skips_unknown_command(bus: JsonlEventBus) -> None:
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/teleport now"},
        ),
        bus,
    )
    assert seen == []


def test_react_correct_resubmits_file_change(bus: JsonlEventBus) -> None:
    file_change, agent_response = _seed_chain(bus)
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={
                "user": 1,
                "text": f"/correct {agent_response.id[:8]} priority=high",
            },
        ),
        bus,
    )

    assert len(seen) == 1
    resubmitted = seen[0]
    assert resubmitted.type == "file_change"
    assert resubmitted.source == "controller"
    assert resubmitted.data["path"] == file_change.data["path"]
    assert resubmitted.data["controller_resubmit"] is True
    assert resubmitted.data["resubmit_origin"] == file_change.id
    # The resubmit was also written to the bus.
    bus_events = [e for e in bus.read() if e.id == resubmitted.id]
    assert len(bus_events) == 1


def test_react_correct_with_unknown_prefix_does_not_resubmit(
    bus: JsonlEventBus,
) -> None:
    _seed_chain(bus)
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/correct ffffffff priority=high"},
        ),
        bus,
    )
    assert seen == []


def test_react_correct_with_empty_args_does_not_resubmit(
    bus: JsonlEventBus,
) -> None:
    _seed_chain(bus)
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/correct"},
        ),
        bus,
    )
    assert seen == []


def test_react_scar_resubmits_latest_file_change(bus: JsonlEventBus) -> None:
    _seed_chain(bus, path="old.py")
    new_file_change, _ = _seed_chain(bus, path="new.py")
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/scar priority=high"},
        ),
        bus,
    )

    assert len(seen) == 1
    assert seen[0].data["path"] == "new.py"
    assert seen[0].data["resubmit_origin"] == new_file_change.id


def test_react_scar_with_no_agent_response_does_not_resubmit(
    bus: JsonlEventBus,
) -> None:
    bus.append(
        Event(type="file_change", source="watcher", data={"path": "x.py"})
    )
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/scar priority=high"},
        ),
        bus,
    )
    assert seen == []


def test_resubmit_cap_enforced(bus: JsonlEventBus) -> None:
    file_change, agent_response = _seed_chain(bus)
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    decision = Event(
        type="human_decision",
        source="interface",
        data={"user": 1, "text": f"/correct {agent_response.id[:8]} p=h"},
    )
    # Fire the same /correct CHAIN_CAP + 2 times. Only the first
    # CHAIN_CAP should produce a resubmit; the rest are bounded.
    # Spam at depth 1 (same response /scar'd N times) all increments
    # the same chain counter, so the observable behaviour matches the
    # pre-issue-#47 per-originating-id cap.
    for _ in range(LoopController.CHAIN_CAP + 2):
        controller.on_bus_event(decision, bus)

    assert len(seen) == LoopController.CHAIN_CAP
    for resubmit in seen:
        assert resubmit.data["resubmit_origin"] == file_change.id
        assert resubmit.data["controller_chain_depth"] == 1


def test_resubmit_skipped_when_correlates_missing(bus: JsonlEventBus) -> None:
    # agent_response written without ``correlates`` — no way to find
    # the originating file_change, controller logs and skips.
    bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"path": "orphan.py"},
        )
    )
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)
    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/scar priority=high"},
        ),
        bus,
    )
    assert seen == []


def test_resubmit_skipped_when_file_change_purged(bus: JsonlEventBus) -> None:
    # agent_response references a file_change id that no longer
    # exists on the bus (e.g. log rotation deleted it). Skip cleanly.
    bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"correlates": "missing-id", "path": "x.py"},
        )
    )
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)
    controller.on_bus_event(
        Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": "/scar priority=high"},
        ),
        bus,
    )
    assert seen == []


def test_start_with_bus_spawns_subscription_thread(
    bus: JsonlEventBus,
) -> None:
    controller = LoopController(lambda e: None, bus=bus)
    controller.start()
    try:
        assert controller._worker is not None
        assert controller._worker.is_alive()
        assert controller._bus_thread is not None
        assert controller._bus_thread.is_alive()
        assert controller._bus_thread.daemon is True
    finally:
        controller.stop()


def test_start_without_bus_does_not_spawn_subscription_thread() -> None:
    controller = LoopController(lambda e: None)
    controller.start()
    try:
        assert controller._bus_thread is None
    finally:
        controller.stop()


def test_stop_joins_bus_subscription_cleanly(bus: JsonlEventBus) -> None:
    controller = LoopController(lambda e: None, bus=bus)
    controller.start()
    bus_thread = controller._bus_thread
    assert bus_thread is not None
    controller.stop(timeout=2.0)
    assert not bus_thread.is_alive()
    assert controller._bus_thread is None
    assert controller._bus_reader is None


def test_end_to_end_bus_reaction(bus: JsonlEventBus) -> None:
    """Full chunk-3b path through the running subscription thread.

    Seed a chain, start the controller (spawns worker + bus thread),
    append a /correct human_decision to the bus, wait for the bus
    thread to pick it up and submit the resubmit to the worker, then
    confirm the worker callback ran.
    """
    file_change, agent_response = _seed_chain(bus)
    seen: list[Event] = []

    controller = LoopController(seen.append, bus=bus)
    # Speed up the test — default poll interval is 0.5s, override.
    controller._BUS_POLL_INTERVAL = 0.05  # type: ignore[misc]
    controller.start()
    try:
        bus.append(
            Event(
                type="human_decision",
                source="interface",
                data={
                    "user": 1,
                    "text": f"/correct {agent_response.id[:8]} priority=high",
                },
            )
        )
        # Wait for the bus thread to react and the worker to drain.
        deadline = time.monotonic() + 3.0
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller._queue is not None
        controller._queue.join()
    finally:
        controller.stop(timeout=2.0)

    assert len(seen) == 1
    assert seen[0].data["resubmit_origin"] == file_change.id
    assert seen[0].data["controller_resubmit"] is True


# ---------------------------------------------------------------------------
# Issue #47 — chain cap with origin-aware tracking
#
# Failure modes (see docs/phase-3-cap-design.md):
#   F-CAP-1  missing parent during walk → treat current as root.
#   F-CAP-2  untrusted lineage on non-controller events → trust
#            controller_chain_depth / controller_resubmit /
#            resubmit_origin ONLY when source="controller".
#   F-CAP-3  in-memory dict growth → bounded eviction.
#   F-CAP-5  cyclic / forged / pathologically deep lineage →
#            visited_set + MAX_CHAIN_WALK_DEPTH.
# ---------------------------------------------------------------------------


def _controller_resubmit_event(
    bus: JsonlEventBus,
    *,
    parent_id: str,
    depth: int,
    path: str = "sample.py",
) -> Event:
    """Append a synthetic controller-emitted resubmit event.

    Useful for white-box tests that need to walk a multi-hop
    chain without driving the full /scar reaction path.
    """
    return bus.append(
        Event(
            type="file_change",
            source="controller",
            data={
                "path": path,
                "change_type": "modified",
                "controller_resubmit": True,
                "resubmit_origin": parent_id,
                "controller_chain_depth": depth,
            },
        )
    )


def test_chain_root_returns_self_for_watcher_event(
    bus: JsonlEventBus,
) -> None:
    """A non-controller event is the root of its own chain by
    definition; F-CAP-2 stops the walk there."""
    file_change, _ = _seed_chain(bus)
    controller = LoopController(lambda e: None, bus=bus)

    assert controller._chain_root(file_change, bus) == file_change.id


def test_chain_root_walks_multi_hop_controller_lineage(
    bus: JsonlEventBus,
) -> None:
    """A 3-hop controller chain walks back to the watcher root."""
    root, _ = _seed_chain(bus)
    hop1 = _controller_resubmit_event(bus, parent_id=root.id, depth=1)
    hop2 = _controller_resubmit_event(bus, parent_id=hop1.id, depth=2)
    hop3 = _controller_resubmit_event(bus, parent_id=hop2.id, depth=3)
    controller = LoopController(lambda e: None, bus=bus)

    assert controller._chain_root(hop3, bus) == root.id


def test_chain_root_treats_missing_parent_as_root_f_cap_1(
    bus: JsonlEventBus,
) -> None:
    """F-CAP-1: parent_id present but not on the bus (log-rotated
    away or partial replay) → walk treats the current cursor as
    root rather than crashing."""
    orphan = bus.append(
        Event(
            type="file_change",
            source="controller",
            data={
                "path": "x.py",
                "controller_resubmit": True,
                "resubmit_origin": "no-such-id-on-bus",
                "controller_chain_depth": 1,
            },
        )
    )
    controller = LoopController(lambda e: None, bus=bus)

    assert controller._chain_root(orphan, bus) == orphan.id


def test_chain_root_ignores_lineage_on_non_controller_source_f_cap_2(
    bus: JsonlEventBus,
) -> None:
    """F-CAP-2: a watcher / webhook / external producer carrying
    controller_resubmit=True / resubmit_origin / chain_depth on
    its data MUST be treated as a root — not walked through."""
    forged = bus.append(
        Event(
            type="file_change",
            source="github_webhook",
            data={
                "path": "x.py",
                "controller_resubmit": True,
                "resubmit_origin": "any-id",
                "controller_chain_depth": 99,
            },
        )
    )
    controller = LoopController(lambda e: None, bus=bus)

    assert controller._chain_root(forged, bus) == forged.id


def test_chain_root_breaks_cycle_f_cap_5(bus: JsonlEventBus) -> None:
    """F-CAP-5: two controller events with resubmit_origin pointing
    at each other → visited_set returns on the second visit."""
    placeholder = bus.append(
        Event(
            type="file_change",
            source="controller",
            data={
                "path": "x.py",
                "controller_resubmit": True,
                "resubmit_origin": "tbd",
                "controller_chain_depth": 1,
            },
        )
    )
    cycle_partner = bus.append(
        Event(
            type="file_change",
            source="controller",
            data={
                "path": "x.py",
                "controller_resubmit": True,
                "resubmit_origin": placeholder.id,
                "controller_chain_depth": 2,
            },
        )
    )
    # Patch placeholder.data to point back at cycle_partner.
    placeholder.data["resubmit_origin"] = cycle_partner.id
    # Fake bus.read by replacing the relevant event in-place. The
    # JsonlEventBus is append-only; for this test we patch the
    # controller's _find_file_change to return our two-event ring.
    controller = LoopController(lambda e: None, bus=bus)
    ring = {placeholder.id: placeholder, cycle_partner.id: cycle_partner}
    controller._find_file_change = (  # type: ignore[assignment]
        staticmethod(lambda _bus, eid: ring.get(eid))
    )

    # Walk must terminate; result is one of the two ids.
    root = controller._chain_root(cycle_partner, bus)
    assert root in {placeholder.id, cycle_partner.id}


def test_chain_root_breaks_pathologically_deep_acyclic_lineage_f_cap_5(
    bus: JsonlEventBus,
) -> None:
    """F-CAP-5: an acyclic chain longer than MAX_CHAIN_WALK_DEPTH
    must terminate via the ceiling, not via cycle detection."""
    cap = LoopController.MAX_CHAIN_WALK_DEPTH
    root, _ = _seed_chain(bus)
    deepest = root
    chain = [root]
    for depth in range(1, cap + 5):  # 5 past the ceiling
        deepest = _controller_resubmit_event(
            bus, parent_id=deepest.id, depth=depth
        )
        chain.append(deepest)

    controller = LoopController(lambda e: None, bus=bus)

    # Walking from the deepest cursor should NOT spin forever and
    # should NOT reach the actual root — it should stop at the
    # ceiling.
    result = controller._chain_root(deepest, bus)
    assert result != root.id
    # The result is the cursor reached after MAX_CHAIN_WALK_DEPTH
    # parent hops from `deepest`.
    assert result == chain[-1 - cap].id


def test_resubmit_persists_chain_depth_on_bus(bus: JsonlEventBus) -> None:
    """The resubmit emits ``controller_chain_depth`` on the bus so
    analyze can audit chain depth post-hoc."""
    file_change, agent_response = _seed_chain(bus)
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    decision = Event(
        type="human_decision",
        source="interface",
        data={
            "user": 1,
            "text": f"/correct {agent_response.id[:8]} priority=high",
        },
    )
    controller.on_bus_event(decision, bus)

    assert len(seen) == 1
    resubmit = seen[0]
    assert resubmit.data["controller_chain_depth"] == 1
    # Persisted on the bus, not just on the in-flight event.
    bus_events = [e for e in bus.read() if e.type == "file_change"]
    assert any(
        e.data.get("controller_chain_depth") == 1 for e in bus_events
    )


def test_resubmit_depth_resets_to_one_when_parent_is_non_controller_f_cap_2(
    bus: JsonlEventBus,
) -> None:
    """F-CAP-2: even if a forged github_webhook event carries
    controller_chain_depth=99, the resubmit emitted from a /correct
    that picks it up MUST start at depth=1 (this is the first hop
    on a chain rooted at that forged event)."""
    forged_path_event = bus.append(
        Event(
            type="file_change",
            source="github_webhook",
            data={
                "path": "x.py",
                "change_type": "review_comment",
                "controller_chain_depth": 99,
            },
        )
    )
    response = bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"correlates": forged_path_event.id, "path": "x.py"},
            dispatch={"agent": "claude_code", "status": "completed"},
            response={"content": "ok", "requires_human": False},
        )
    )
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    decision = Event(
        type="human_decision",
        source="interface",
        data={"user": 1, "text": f"/correct {response.id[:8]} priority=h"},
    )
    controller.on_bus_event(decision, bus)

    assert len(seen) == 1
    assert seen[0].data["controller_chain_depth"] == 1


def test_independent_chains_do_not_share_a_cap(bus: JsonlEventBus) -> None:
    """chain[A] at cap must not block chain[B]. Each genuine
    correction starts a fresh chain rooted at a distinct
    file_change."""
    file_a, response_a = _seed_chain(bus, path="a.py")
    file_b, response_b = _seed_chain(bus, path="b.py")
    seen: list[Event] = []
    controller = LoopController(seen.append, bus=bus)

    decision_a = Event(
        type="human_decision",
        source="interface",
        data={"user": 1, "text": f"/correct {response_a.id[:8]} p=h"},
    )
    decision_b = Event(
        type="human_decision",
        source="interface",
        data={"user": 1, "text": f"/correct {response_b.id[:8]} p=h"},
    )
    # Cap chain[a].
    for _ in range(LoopController.CHAIN_CAP + 1):
        controller.on_bus_event(decision_a, bus)
    # chain[b] is independent and must still admit a resubmit.
    controller.on_bus_event(decision_b, bus)

    chain_a = [e for e in seen if e.data["resubmit_origin"] == file_a.id]
    chain_b = [e for e in seen if e.data["resubmit_origin"] == file_b.id]
    assert len(chain_a) == LoopController.CHAIN_CAP
    assert len(chain_b) == 1


def test_chain_counts_evicts_oldest_when_ceiling_reached_f_cap_3(
    bus: JsonlEventBus,
) -> None:
    """F-CAP-3: when _chain_counts exceeds the ceiling, the
    insertion-order oldest entry is evicted."""
    controller = LoopController(lambda e: None, bus=bus)
    # Tighten the ceiling for the test so we don't have to fill 1024.
    controller.CHAIN_COUNTS_MAX_SIZE = 3
    # Drive the dict directly through _chain_counts to keep the
    # test focused on the eviction policy. This mirrors what
    # _resubmit_for does after the cap check.
    seeds = [
        _seed_chain(bus, path=f"f{i}.py")[0] for i in range(4)
    ]
    seen: list[Event] = []
    controller.callback = seen.append

    for idx, seed in enumerate(seeds):
        # Fabricate an agent_response → /correct path for each seed
        # so _resubmit_for runs end-to-end.
        response = bus.append(
            Event(
                type="agent_response",
                source="adapter",
                data={"correlates": seed.id, "path": f"f{idx}.py"},
                dispatch={"agent": "claude_code", "status": "completed"},
                response={"content": "ok", "requires_human": False},
            )
        )
        decision = Event(
            type="human_decision",
            source="interface",
            data={"user": 1, "text": f"/correct {response.id[:8]} p=h"},
        )
        controller.on_bus_event(decision, bus)

    # Four distinct chains were touched but the ceiling is 3 → the
    # first chain (seeds[0]) must have been evicted.
    assert seeds[0].id not in controller._chain_counts
    assert len(controller._chain_counts) == 3
    # The other three are present.
    for seed in seeds[1:]:
        assert seed.id in controller._chain_counts


def test_restart_resets_in_memory_chain_counts(bus: JsonlEventBus) -> None:
    """Restart semantics: _chain_counts is in-memory and per-process.
    A fresh LoopController instance starts with empty counts, so a
    chain that was at cap pre-restart admits one more resubmit
    post-restart. The persisted controller_chain_depth on bus
    events is unaffected (still auditable by analyze)."""
    file_change, agent_response = _seed_chain(bus)
    seen_pre: list[Event] = []
    controller_pre = LoopController(seen_pre.append, bus=bus)

    decision = Event(
        type="human_decision",
        source="interface",
        data={"user": 1, "text": f"/correct {agent_response.id[:8]} p=h"},
    )
    # Drive chain[file_change] all the way to cap.
    for _ in range(LoopController.CHAIN_CAP + 1):
        controller_pre.on_bus_event(decision, bus)
    assert len(seen_pre) == LoopController.CHAIN_CAP

    # Simulate a restart: discard the controller and build a new one.
    seen_post: list[Event] = []
    controller_post = LoopController(seen_post.append, bus=bus)
    assert controller_post._chain_counts == {}

    # The post-restart controller admits a fresh resubmit on the
    # same chain (live counter reset). Persisted depth on bus is
    # what analyze uses across restarts.
    controller_post.on_bus_event(decision, bus)
    assert len(seen_post) == 1
    assert seen_post[0].data["resubmit_origin"] == file_change.id
