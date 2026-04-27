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
