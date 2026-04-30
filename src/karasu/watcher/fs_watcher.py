"""watchdog-based filesystem observer.

Turns inotify-style events into Karasu ``file_change`` events on the
bus. Ignore patterns are matched against the path relative to the
watch root.

Pipeline callbacks run on a dedicated worker thread owned by
:class:`LoopController` (Phase 3 chunk 3a). The watcher hands events
off via ``controller.submit`` instead of running the pipeline
inline; a slow adapter therefore cannot stall filesystem event
capture.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from karasu.controller import LoopController
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
    DEFAULT_QUEUE_SIZE = LoopController.DEFAULT_QUEUE_SIZE

    def __init__(
        self,
        root: str | Path,
        bus: JsonlEventBus,
        ignore: Iterable[str] = (),
        on_event: OnEvent | None = None,
        controller: LoopController | None = None,
        queue_size: int | None = None,
        debounce_ms: int = 0,
    ) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.ignore = tuple(ignore)
        self.debounce_ms = max(0, int(debounce_ms))
        self._observer = Observer()
        # Controller wiring. Two paths:
        #   - ``controller`` supplied: production path. ``cmd_watch``
        #     builds the controller explicitly so it can be reused
        #     by Phase 3b reaction logic.
        #   - ``on_event`` supplied without a controller: legacy
        #     path. The watcher constructs an internal controller
        #     so existing tests and callers keep their API.
        if controller is None and on_event is not None:
            controller = LoopController(on_event, queue_size=queue_size)
        self._controller = controller
        # Per-(path, change_type) timestamp of the last dispatched event,
        # in monotonic seconds. Grows unbounded over a long-lived watcher;
        # acceptable for Phase 1 single-repo use, revisit if memory matters.
        self._last_dispatched: dict[tuple[str, str], float] = {}
        self._debounce_lock = threading.Lock()

    @property
    def on_event(self) -> OnEvent | None:
        if self._controller is None:
            return None
        return self._controller.callback

    @on_event.setter
    def on_event(self, value: OnEvent | None) -> None:
        if value is None:
            self._controller = None
            return
        if self._controller is None:
            self._controller = LoopController(value)
        else:
            self._controller.callback = value

    @property
    def _queue(self):  # legacy accessor for tests; delegates to controller
        return self._controller._queue if self._controller else None

    @property
    def _worker(self):
        return self._controller._worker if self._controller else None

    @property
    def _stopping(self):
        return self._controller._stopping if self._controller else None

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

    def _is_debounced(self, rel_path: str, change_type: str) -> bool:
        """Return True if the (path, change_type) just fired inside the window.

        The first event for a (path, change_type) pair always passes; only
        subsequent events landing within ``debounce_ms`` are dropped. This
        suppresses the burst of duplicate events that editors emit on save
        without losing distinct change kinds (a delete after a modify, or
        a create after a delete, are not collapsed).
        """
        if self.debounce_ms <= 0:
            return False
        key = (rel_path, change_type)
        now = time.monotonic()
        window_seconds = self.debounce_ms / 1000.0
        with self._debounce_lock:
            last = self._last_dispatched.get(key)
            if last is not None and (now - last) < window_seconds:
                return True
            self._last_dispatched[key] = now
            return False

    def _dispatch(self, event: FileSystemEvent) -> Event | None:
        try:
            rel = Path(event.src_path).resolve().relative_to(self.root)
        except ValueError:
            return None
        # Normalize to forward-slash so ignore patterns and downstream
        # consumers see the same path format on every OS. Without this,
        # ``Path.relative_to`` returns backslash-separated paths on
        # Windows; ``_is_ignored`` then misses ``.foo/`` style globs and
        # the ``"/" not in pattern`` segment-split branch (see issue #14
        # finding F2). Forward-slash is the canonical Karasu path form.
        rel_path = rel.as_posix()
        if self._is_ignored(rel_path):
            return None
        change_type = self._CHANGE_TYPES.get(event.event_type, event.event_type)
        if self._is_debounced(rel_path, change_type):
            return None
        appended = self.bus.append(
            Event(
                type="file_change",
                source="watcher",
                data={"path": rel_path, "change_type": change_type},
            )
        )
        if self._controller is not None:
            self._controller.submit(appended)
        return appended

    def start_pipeline(self) -> None:
        """Spin up the controller's worker thread."""
        if self._controller is None:
            return
        self._controller.start()

    def stop_pipeline(self, timeout: float = 5.0) -> None:
        """Signal the controller to stop and wait up to ``timeout`` seconds."""
        if self._controller is None:
            return
        self._controller.stop(timeout=timeout)

    def start(self) -> None:
        """Schedule and start the inotify observer.

        Phase 3 chunk 3c: the watcher is a TriggerSource. The
        controller starts its own worker + bus subscription before
        calling this method, so ``start`` no longer manages the
        pipeline lifecycle. ``start_pipeline``/``stop_pipeline``
        remain as legacy delegators for tests that want to drive
        the controller through the watcher directly.
        """
        self._observer.schedule(_Handler(self), str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def run_forever(self, poll_interval: float = 1.0) -> None:
        # Standalone-watcher path: bring up the controller worker so
        # callbacks run, then start the observer. Production goes
        # through ``LoopController.run_forever`` instead, which
        # manages the watcher as a registered source.
        self.start_pipeline()
        self.start()
        try:
            while True:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stop()
            self.stop_pipeline()
