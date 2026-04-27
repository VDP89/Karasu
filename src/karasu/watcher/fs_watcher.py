"""watchdog-based filesystem observer.

Turns inotify-style events into Karasu ``file_change`` events on the
bus. Ignore patterns are matched against the path relative to the
watch root.
"""

from __future__ import annotations

import fnmatch
import logging
import time
from pathlib import Path
from typing import Callable, Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from karasu.eventbus import Event, JsonlEventBus

OnEvent = Callable[[Event], None]

_log = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "FilesystemWatcher") -> None:
        self._watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher._dispatch(event)


class FilesystemWatcher:
    """Watch ``root`` and append a ``file_change`` event per change."""

    _CHANGE_TYPES = {
        "created": "created",
        "modified": "modified",
        "deleted": "deleted",
        "moved": "modified",
    }

    def __init__(
        self,
        root: str | Path,
        bus: JsonlEventBus,
        ignore: Iterable[str] = (),
        on_event: OnEvent | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.ignore = tuple(ignore)
        self.on_event = on_event
        self._observer = Observer()

    def _is_ignored(self, rel_path: str) -> bool:
        for pattern in self.ignore:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if pattern.endswith("/") and rel_path.startswith(pattern):
                return True
            if "/" not in pattern and any(
                fnmatch.fnmatch(part, pattern) for part in rel_path.split("/")
            ):
                return True
        return False

    def _dispatch(self, event: FileSystemEvent) -> Event | None:
        try:
            rel = str(Path(event.src_path).resolve().relative_to(self.root))
        except ValueError:
            return None
        if self._is_ignored(rel):
            return None
        change_type = self._CHANGE_TYPES.get(event.event_type, event.event_type)
        appended = self.bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": rel, "change_type": change_type},
            )
        )
        if self.on_event is not None:
            # The callback runs on the watchdog observer thread; an uncaught
            # exception would silently kill it and stop event delivery.
            try:
                self.on_event(appended)
            except Exception:
                _log.exception("on_event callback failed for %s", rel)
        return appended

    def start(self) -> None:
        self._observer.schedule(_Handler(self), str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def run_forever(self, poll_interval: float = 1.0) -> None:
        self.start()
        try:
            while True:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stop()
