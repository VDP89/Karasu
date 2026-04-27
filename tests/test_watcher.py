import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

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


def test_ignore_pattern_skips_event(tmp_path: Path, bus: JsonlEventBus) -> None:
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, ignore=("__pycache__",))
    nested = tmp_path / "__pycache__" / "x.pyc"
    nested.parent.mkdir()
    nested.write_text("")
    assert watcher._dispatch(_fake_event(str(nested))) is None
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


def test_full_queue_drops_callback_with_warning(tmp_path: Path, bus: JsonlEventBus, caplog) -> None:
    proceed = threading.Event()
    seen: list = []

    def slow(event):
        proceed.wait(timeout=2)
        seen.append(event)

    # Tiny queue to make overflow easy to trigger.
    watcher = FilesystemWatcher(root=tmp_path, bus=bus, on_event=slow, queue_size=1)
    target = tmp_path / "a.py"
    target.write_text("")

    watcher.start_pipeline()
    try:
        # First event: worker picks it up, blocks on `proceed`.
        watcher._dispatch(_fake_event(str(target)))
        # Wait until the worker has actually pulled the first event so
        # the queue is empty again before we fill it.
        deadline = time.monotonic() + 1.0
        while watcher._queue.unfinished_tasks < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        # Second event: lands in the (empty, size=1) queue.
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
