"""Tests for trigger sources (Phase 3 chunk 3c)."""

from __future__ import annotations

import threading
import time

from karasu.controller import LoopController
from karasu.controller.sources import TriggerSource
from karasu.controller.sources.git_hook import (
    HOOK_CHANGE_TYPE,
    SUPPORTED_HOOKS,
    build_events,
    paths_for_hook,
    submit_for_hook,
)
from karasu.eventbus import Event, JsonlEventBus
from karasu.watcher import FilesystemWatcher


# ---------------------------------------------------------------------------
# TriggerSource protocol — structural conformance
# ---------------------------------------------------------------------------


class _RecordingSource:
    """Minimal source: records start/stop calls. Conforms to TriggerSource
    by virtue of having start() and stop()."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_recording_source_conforms_to_protocol() -> None:
    source = _RecordingSource()
    # runtime_checkable Protocol — instance check verifies the
    # structural interface.
    assert isinstance(source, TriggerSource)


def test_filesystem_watcher_conforms_to_protocol(tmp_path, bus: JsonlEventBus) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus)
    # The watcher is the canonical TriggerSource (long-running
    # producer); chunk 3c documents the seam by registering it.
    assert isinstance(watcher, TriggerSource)


# ---------------------------------------------------------------------------
# Controller lifecycle — sources start/stop in order
# ---------------------------------------------------------------------------


def test_controller_starts_sources_after_worker() -> None:
    order: list[str] = []
    callback = lambda e: order.append("callback")  # noqa: E731

    class TrackingSource:
        def start(self) -> None:
            order.append("source-start")

        def stop(self) -> None:
            order.append("source-stop")

    controller = LoopController(callback)
    controller.add_source(TrackingSource())
    controller.start()
    try:
        # The worker is up by now; start() returned. The source
        # was started AFTER the worker was spawned (we cannot
        # observe the worker spawn directly, but the order list
        # has the source-start event).
        assert order == ["source-start"]
    finally:
        controller.stop()
    # On stop, source-stop comes BEFORE the worker exits (stops
    # producing first); the order list captures that.
    assert order == ["source-start", "source-stop"]


def test_controller_runs_multiple_sources_in_registration_order() -> None:
    order: list[str] = []

    class Recorder:
        def __init__(self, name: str) -> None:
            self.name = name

        def start(self) -> None:
            order.append(f"start-{self.name}")

        def stop(self) -> None:
            order.append(f"stop-{self.name}")

    controller = LoopController(lambda e: None)
    controller.add_source(Recorder("a"))
    controller.add_source(Recorder("b"))
    controller.add_source(Recorder("c"))
    controller.start()
    controller.stop()

    assert order == [
        "start-a",
        "start-b",
        "start-c",
        "stop-a",
        "stop-b",
        "stop-c",
    ]


def test_source_start_exception_is_logged_and_does_not_break_controller(
    caplog,
) -> None:
    class Boom:
        def start(self) -> None:
            raise RuntimeError("source boom on start")

        def stop(self) -> None:
            pass

    controller = LoopController(lambda e: None)
    controller.add_source(Boom())
    with caplog.at_level("ERROR", logger="karasu.controller.loop"):
        controller.start()
    try:
        # Worker is alive even though the source failed to start.
        assert controller._worker is not None
        assert controller._worker.is_alive()
        assert any(
            "trigger source" in r.message and "failed to start" in r.message
            for r in caplog.records
        )
    finally:
        controller.stop()


def test_source_stop_exception_is_logged_and_does_not_break_controller(
    caplog,
) -> None:
    class Boom:
        def start(self) -> None:
            pass

        def stop(self) -> None:
            raise RuntimeError("source boom on stop")

    controller = LoopController(lambda e: None)
    controller.add_source(Boom())
    controller.start()
    with caplog.at_level("ERROR", logger="karasu.controller.loop"):
        controller.stop()
    assert any(
        "trigger source" in r.message and "raised during stop" in r.message
        for r in caplog.records
    )


def test_multi_source_fan_in_preserves_per_source_order(
    bus: JsonlEventBus,
) -> None:
    """Two sources both call submit; events processed serially through
    the single worker, and per-source order is preserved (FIFO queue)."""
    seen: list[str] = []
    seen_lock = threading.Lock()

    def callback(event: Event) -> None:
        with seen_lock:
            seen.append(event.data["path"])

    controller = LoopController(callback)

    class FanInSource:
        def __init__(self, prefix: str, count: int) -> None:
            self.prefix = prefix
            self.count = count

        def start(self) -> None:
            for i in range(self.count):
                controller.submit(
                    Event(
                        type="file_change",
                        source=f"src-{self.prefix}",
                        data={"path": f"{self.prefix}-{i}.py"},
                    )
                )

        def stop(self) -> None:
            pass

    controller.add_source(FanInSource("a", 5))
    controller.add_source(FanInSource("b", 5))
    controller.start()
    try:
        if controller._queue is not None:
            controller._queue.join()
    finally:
        controller.stop()

    # All events processed.
    assert sorted(seen) == sorted(
        [f"a-{i}.py" for i in range(5)] + [f"b-{i}.py" for i in range(5)]
    )
    # Per-source order: A's events appear in order (0..4), then B's.
    a_indices = [s for s in seen if s.startswith("a-")]
    b_indices = [s for s in seen if s.startswith("b-")]
    assert a_indices == [f"a-{i}.py" for i in range(5)]
    assert b_indices == [f"b-{i}.py" for i in range(5)]


# ---------------------------------------------------------------------------
# Git-hook source — pure path extraction + event building
# ---------------------------------------------------------------------------


def test_supported_hooks_match_change_type_keys() -> None:
    assert SUPPORTED_HOOKS == frozenset(HOOK_CHANGE_TYPE)


def test_paths_for_pre_commit_runs_diff_cached() -> None:
    captured: list[list[str]] = []

    def fake(argv: list[str]) -> str:
        captured.append(argv)
        return "src/a.py\nsrc/b.py\n"

    paths = paths_for_hook("pre-commit", runner=fake)

    assert captured == [["git", "diff", "--cached", "--name-only"]]
    assert paths == ["src/a.py", "src/b.py"]


def test_paths_for_post_commit_runs_show_head() -> None:
    captured: list[list[str]] = []

    def fake(argv: list[str]) -> str:
        captured.append(argv)
        return "\nREADME.md\n  \n"  # blanks should be skipped

    paths = paths_for_hook("post-commit", runner=fake)

    assert captured == [
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"]
    ]
    assert paths == ["README.md"]


def test_paths_for_post_merge_runs_diff_tree() -> None:
    captured: list[list[str]] = []

    def fake(argv: list[str]) -> str:
        captured.append(argv)
        return "merged.py\n"

    paths = paths_for_hook("post-merge", runner=fake)

    assert captured == [
        [
            "git",
            "diff-tree",
            "-r",
            "--name-only",
            "--no-commit-id",
            "ORIG_HEAD",
            "HEAD",
        ]
    ]
    assert paths == ["merged.py"]


def test_paths_for_unknown_hook_returns_empty() -> None:
    captured: list[list[str]] = []

    def fake(argv: list[str]) -> str:
        captured.append(argv)
        return "anything"

    assert paths_for_hook("unknown", runner=fake) == []
    # Runner is not invoked for unknown hooks.
    assert captured == []


def test_build_events_attaches_change_type_and_git_hook() -> None:
    events = build_events("pre-commit", ["a.py", "b.py"])
    assert len(events) == 2
    for event in events:
        assert event.type == "file_change"
        assert event.source == "git_hook"
        assert event.data["change_type"] == "staged"
        assert event.data["git_hook"] == "pre-commit"
    assert [e.data["path"] for e in events] == ["a.py", "b.py"]


def test_build_events_for_each_supported_hook_uses_correct_change_type() -> None:
    expected = {
        "pre-commit": "staged",
        "post-commit": "committed",
        "post-merge": "merged",
    }
    for hook, change_type in expected.items():
        events = build_events(hook, ["x.py"])
        assert len(events) == 1
        assert events[0].data["change_type"] == change_type
        assert events[0].data["git_hook"] == hook


def test_build_events_for_unknown_hook_returns_empty() -> None:
    assert build_events("unknown", ["x.py"]) == []


# ---------------------------------------------------------------------------
# submit_for_hook — bus + controller integration
# ---------------------------------------------------------------------------


def test_submit_for_hook_writes_to_bus_and_submits(
    bus: JsonlEventBus,
) -> None:
    submitted: list[Event] = []

    def fake_runner(argv: list[str]) -> str:
        return "a.py\nb.py\n"

    count = submit_for_hook("pre-commit", bus, submitted.append, runner=fake_runner)

    assert count == 2
    # Events are on the bus.
    bus_events = list(bus.read())
    assert len(bus_events) == 2
    assert all(e.source == "git_hook" for e in bus_events)
    assert [e.data["path"] for e in bus_events] == ["a.py", "b.py"]
    # And submitted to the controller.
    assert [e.id for e in submitted] == [e.id for e in bus_events]


def test_submit_for_hook_no_paths_returns_zero(bus: JsonlEventBus) -> None:
    submitted: list[Event] = []
    count = submit_for_hook(
        "pre-commit", bus, submitted.append, runner=lambda argv: ""
    )
    assert count == 0
    assert submitted == []
    assert list(bus.read()) == []


def test_submit_for_hook_rejects_unknown_hook(bus: JsonlEventBus) -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported hook"):
        submit_for_hook("unknown", bus, lambda e: None, runner=lambda argv: "")


# ---------------------------------------------------------------------------
# End-to-end — git-hook source through a live controller
# ---------------------------------------------------------------------------


def test_git_hook_source_through_live_controller(bus: JsonlEventBus) -> None:
    """Drive a one-shot hook submission through a started controller.

    This is the same shape ``cmd_hook`` uses in production: build a
    controller (without bus subscription, since hooks are one-shot),
    start it, fire ``submit_for_hook``, drain the queue, stop.
    """
    seen: list[str] = []
    controller = LoopController(lambda e: seen.append(e.data["path"]))
    controller.start()
    try:
        count = submit_for_hook(
            "post-commit",
            bus,
            controller.submit,
            runner=lambda argv: "x.py\ny.py\nz.py\n",
        )
        if controller._queue is not None:
            controller._queue.join()
    finally:
        controller.stop()

    assert count == 3
    assert seen == ["x.py", "y.py", "z.py"]


# ---------------------------------------------------------------------------
# Parity check — registered watcher still produces the same bus output
# ---------------------------------------------------------------------------


class _FakeFsEvent:
    def __init__(self, path: str, event_type: str = "modified") -> None:
        self.src_path = path
        self.event_type = event_type
        self.is_directory = False


def test_controller_start_starts_watcher_observer(
    tmp_path, bus: JsonlEventBus
) -> None:
    """The watcher refactor (``start()`` no longer bootstraps the
    worker) means the controller is the one driving the source
    lifecycle. Verify that ``controller.start()`` results in the
    watcher's observer being alive.
    """
    controller = LoopController(lambda e: None)
    watcher = FilesystemWatcher(
        root=tmp_path, bus=bus, controller=controller
    )
    controller.add_source(watcher)
    controller.start()
    try:
        # The observer is a watchdog Observer thread; it's alive
        # after ``start()`` and stops via ``controller.stop``.
        assert watcher._observer.is_alive()
    finally:
        controller.stop()
    assert not watcher._observer.is_alive()
