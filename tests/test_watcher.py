import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karasu.eventbus import JsonlEventBus
from karasu.watcher import FilesystemWatcher


def _fake_event(path: str, event_type: str = "modified"):
    fake = MagicMock()
    fake.is_directory = False
    fake.src_path = path
    fake.event_type = event_type
    return fake


def test_dispatch_writes_event(tmp_path: Path, bus: JsonlEventBus) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus)
    target = tmp_path / "a.py"
    target.write_text("")
    watcher._dispatch(_fake_event(str(target), "modified"))
    events = list(bus.read())
    assert len(events) == 1
    assert events[0].type == "file_change"
    assert events[0].data == {"path": "a.py", "change_type": "modified"}


def test_dispatch_normalizes_nested_path_to_forward_slash(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    """Regression for issue #14 finding F2.

    On Windows, ``Path.relative_to`` returns backslash-separated paths
    (``subdir\\nested.py``); ``_is_ignored`` then silently misses
    forward-slash globs like ``.karasu/``. Karasu's canonical path form
    on the bus is forward-slash, on every OS.
    """
    watcher = FilesystemWatcher(root=tmp_path, bus=bus)
    nested = tmp_path / "subdir" / "nested.py"
    nested.parent.mkdir()
    nested.write_text("")
    watcher._dispatch(_fake_event(str(nested), "modified"))
    events = list(bus.read())
    assert len(events) == 1
    # Forward-slash regardless of host OS.
    assert events[0].data["path"] == "subdir/nested.py"
    assert "\\" not in events[0].data["path"]


# ----------------------------------------------------------------------
# Debounce — issue #14 finding F4.
# ----------------------------------------------------------------------


def test_debounce_default_off_passes_every_event(tmp_path: Path, bus: JsonlEventBus) -> None:
    """Default constructor leaves debounce off — preserves direct-test contract."""
    watcher = FilesystemWatcher(root=tmp_path, bus=bus)
    target = tmp_path / "a.py"
    target.write_text("")
    for _ in range(3):
        watcher._dispatch(_fake_event(str(target), "modified"))
    assert len(list(bus.read())) == 3


def test_debounce_drops_repeat_within_window(tmp_path: Path, bus: JsonlEventBus) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, debounce_ms=200)
    target = tmp_path / "a.py"
    target.write_text("")
    for _ in range(3):
        watcher._dispatch(_fake_event(str(target), "modified"))
    events = list(bus.read())
    assert len(events) == 1
    assert events[0].data == {"path": "a.py", "change_type": "modified"}


def test_debounce_does_not_collapse_distinct_change_types(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    """A created followed by a modified inside the window must both pass.

    The burst from a single editor save is many ``modified`` events;
    losing a ``created`` because a ``modified`` followed it within 200 ms
    would silently swallow the existence of the file.
    """
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, debounce_ms=200)
    target = tmp_path / "a.py"
    target.write_text("")
    watcher._dispatch(_fake_event(str(target), "created"))
    watcher._dispatch(_fake_event(str(target), "modified"))
    events = list(bus.read())
    assert [e.data["change_type"] for e in events] == ["created", "modified"]


def test_debounce_does_not_collapse_distinct_paths(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, debounce_ms=200)
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("")
    b.write_text("")
    watcher._dispatch(_fake_event(str(a), "modified"))
    watcher._dispatch(_fake_event(str(b), "modified"))
    events = list(bus.read())
    assert sorted(e.data["path"] for e in events) == ["a.py", "b.py"]


def test_debounce_releases_after_window_elapses(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    """A repeat past the window passes. Uses a tiny window for speed."""
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, debounce_ms=20)
    target = tmp_path / "a.py"
    target.write_text("")
    watcher._dispatch(_fake_event(str(target), "modified"))
    time.sleep(0.05)  # 50 ms — well past the 20 ms window
    watcher._dispatch(_fake_event(str(target), "modified"))
    events = list(bus.read())
    assert len(events) == 2


def test_ignore_pattern_skips_event(tmp_path: Path, bus: JsonlEventBus) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, ignore=("__pycache__",))
    nested = tmp_path / "__pycache__" / "x.pyc"
    nested.parent.mkdir()
    nested.write_text("")
    assert watcher._dispatch(_fake_event(str(nested))) is None
    assert list(bus.read()) == []


@pytest.mark.parametrize(
    "ignore_pattern,filename",
    [
        # F6 — the bus itself, operator-side log captures, and editor
        # tmp files must stay off the bus by default. Without this the
        # JSONL bus and ``karasu watch | tee watch.log`` patterns feed
        # back into the watcher (issue #25 dogfood).
        ("events.jsonl", "events.jsonl"),
        ("*.log", "watch.log"),
        ("*.tmp", "draft.tmp"),
    ],
)
def test_default_ignore_skips_self_generated_paths(
    tmp_path: Path, bus: JsonlEventBus, ignore_pattern: str, filename: str
) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, ignore=(ignore_pattern,))
    target = tmp_path / filename
    target.write_text("")
    assert watcher._dispatch(_fake_event(str(target), "modified")) is None
    assert list(bus.read()) == []


def test_on_event_callback_fires_after_append(tmp_path: Path, bus: JsonlEventBus) -> None:
    seen = []
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=seen.append)
    target = tmp_path / "a.py"
    target.write_text("")
    watcher._dispatch(_fake_event(str(target)))
    assert len(seen) == 1
    assert seen[0].type == "file_change"
    assert seen[0].data["path"] == "a.py"


def test_on_event_callback_skipped_when_ignored(tmp_path: Path, bus: JsonlEventBus) -> None:
    seen = []
    watcher = FilesystemWatcher(
        root=tmp_path, bus=bus, ignore=(".git",), on_event=seen.append
    )
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    inside = git_dir / "HEAD"
    inside.write_text("")
    watcher._dispatch(_fake_event(str(inside)))
    assert seen == []


def test_on_event_exception_is_swallowed(tmp_path: Path, bus: JsonlEventBus, caplog) -> None:
    calls: list[int] = []

    def boom(event):
        calls.append(1)
        raise RuntimeError("pipeline blew up")

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=boom)
    target = tmp_path / "a.py"
    target.write_text("")

    with caplog.at_level("ERROR", logger="karasu.watcher.fs_watcher"):
        first = watcher._dispatch(_fake_event(str(target)))
        second = watcher._dispatch(_fake_event(str(target)))

    assert first is not None and second is not None
    assert calls == [1, 1]
    assert any("on_event callback failed" in r.message for r in caplog.records)


def test_slow_pipeline_does_not_block_dispatch(tmp_path: Path, bus: JsonlEventBus) -> None:
    proceed = threading.Event()
    seen: list = []

    def slow(event):
        proceed.wait(timeout=2)
        seen.append(event)

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=slow)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        # Two _dispatch calls while the worker is blocked on the first
        # callback should still return immediately — the bug we're
        # guarding against is the watchdog thread stalling on a slow
        # adapter.
        start = time.monotonic()
        watcher._dispatch(_fake_event(str(target)))
        watcher._dispatch(_fake_event(str(target)))
        elapsed = time.monotonic() - start
        assert elapsed < 0.2

        proceed.set()
        watcher._queue.join()
        assert len(seen) == 2
    finally:
        watcher.stop_pipeline()


def test_worker_swallows_exceptions(tmp_path: Path, bus: JsonlEventBus, caplog) -> None:
    calls: list[int] = []

    def boom(event):
        calls.append(1)
        raise RuntimeError("worker callback exploded")

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=boom)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        with caplog.at_level("ERROR", logger="karasu.watcher.fs_watcher"):
            watcher._dispatch(_fake_event(str(target)))
            watcher._dispatch(_fake_event(str(target)))
            watcher._queue.join()
    finally:
        watcher.stop_pipeline()

    assert calls == [1, 1]
    assert any("on_event callback failed" in r.message for r in caplog.records)


def test_stop_pipeline_respects_timeout_when_callback_hangs(
    tmp_path: Path, bus: JsonlEventBus, caplog
) -> None:
    unblock = threading.Event()

    def hang(event):
        # Eventually returns so the daemon thread doesn't outlive the test
        # forever, but well past the stop_pipeline timeout.
        unblock.wait(timeout=10)

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=hang)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        watcher._dispatch(_fake_event(str(target)))
        # Give the worker time to pick the event up so it's actually
        # blocked in the callback before we ask it to stop.
        deadline = time.monotonic() + 1.0
        while watcher._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        start = time.monotonic()
        with caplog.at_level("WARNING", logger="karasu.watcher.fs_watcher"):
            watcher.stop_pipeline(timeout=0.3)
        elapsed = time.monotonic() - start

        assert elapsed < 1.5
        assert any("did not exit" in r.message for r in caplog.records)
    finally:
        # Release the daemon thread so it doesn't sit on `wait` for 10s.
        unblock.set()


def test_start_pipeline_refuses_restart_while_old_worker_alive(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    unblock = threading.Event()

    def hang(event):
        unblock.wait(timeout=10)

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=hang)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        watcher._dispatch(_fake_event(str(target)))
        deadline = time.monotonic() + 1.0
        while watcher._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
            time.sleep(0.01)

        watcher.stop_pipeline(timeout=0.2)
        # Old worker abandoned but still alive — restart must refuse to
        # avoid running two workers against two queues simultaneously.
        assert watcher._worker is not None
        assert watcher._worker.is_alive()
        with pytest.raises(RuntimeError, match="still alive"):
            watcher.start_pipeline()
    finally:
        unblock.set()


def test_start_pipeline_recovers_after_old_worker_exits(
    tmp_path: Path, bus: JsonlEventBus
) -> None:
    unblock = threading.Event()

    def hang(event):
        unblock.wait(timeout=10)

    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=hang)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    watcher._dispatch(_fake_event(str(target)))
    deadline = time.monotonic() + 1.0
    while watcher._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    watcher.stop_pipeline(timeout=0.2)
    old_worker = watcher._worker
    assert old_worker is not None and old_worker.is_alive()

    # Let the abandoned worker finish.
    unblock.set()
    old_worker.join(timeout=2.0)
    assert not old_worker.is_alive()

    # Now restart should succeed and produce a fresh worker.
    watcher.on_event = lambda event: None  # cheap callback for the second run
    watcher.start_pipeline()
    try:
        assert watcher._worker is not None
        assert watcher._worker is not old_worker
        assert watcher._worker.is_alive()
    finally:
        watcher.stop_pipeline()


def test_full_queue_drops_callback_with_warning(tmp_path: Path, bus: JsonlEventBus, caplog) -> None:
    started = threading.Event()
    proceed = threading.Event()
    seen: list = []

    def slow(event):
        started.set()
        proceed.wait(timeout=2)
        seen.append(event)

    # Tiny queue to make overflow easy to trigger.
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=slow, queue_size=1)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        # First event: worker picks it up and blocks inside the callback.
        watcher._dispatch(_fake_event(str(target)))
        assert started.wait(timeout=1.0), "worker never picked up the first event"
        # Queue is now empty; second event lands in the (size=1) queue.
        watcher._dispatch(_fake_event(str(target)))
        # Third event: queue is full, must be dropped with a warning.
        with caplog.at_level("WARNING", logger="karasu.watcher.fs_watcher"):
            watcher._dispatch(_fake_event(str(target)))

        assert any("queue full" in r.message for r in caplog.records)
        proceed.set()
        watcher._queue.join()
        # Two events made it through (the third was dropped).
        assert len(seen) == 2
    finally:
        watcher.stop_pipeline()
