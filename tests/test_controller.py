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
    # Fire the same /correct RESUBMIT_CAP + 2 times. Only the first
    # RESUBMIT_CAP should produce a resubmit; the rest are bounded.
    for _ in range(LoopController.RESUBMIT_CAP + 2):
        controller.on_bus_event(decision, bus)

    assert len(seen) == LoopController.RESUBMIT_CAP
    for resubmit in seen:
        assert resubmit.data["resubmit_origin"] == file_change.id


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
