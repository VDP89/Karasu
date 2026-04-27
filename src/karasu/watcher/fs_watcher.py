"""watchdog-based filesystem observer.

Turns inotify-style events into Karasu ``file_change`` events on the
bus. Ignore patterns are matched against the path relative to the
watch root.

The pipeline callback runs on a dedicated worker thread, not on
watchdog's observer thread. A slow adapter (CLI subprocess, HTTP
round trip) therefore cannot stall filesystem event capture; the
observer keeps draining inotify events into a bounded queue while
the worker processes them in order.
"""

from __future__ import annotations

import fnmatch
import logging
import queue
import threading
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
    DEFAULT_QUEUE_SIZE = 1024
    _WORKER_POLL_INTERVAL = 0.1

    def __init__(
        self,
        root: str | Path,
        bus: JsonlEventBus,
        ignore: Iterable[str] = (),
        on_event: OnEvent | None = None,
        queue_size: int | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.ignore = tuple(ignore)
        self.on_event = on_event
        self._queue_size = queue_size or self.DEFAULT_QUEUE_SIZE
        self._observer = Observer()
        self._queue: queue.Queue[Event] | None = None
        self._worker: threading.Thread | None = None
        self._stopping = threading.Event()

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
            self._enqueue(appended)
        return appended

    def _enqueue(self, event: Event) -> None:
        if self._queue is None:
            # No worker started — synchronous fallback. Used by unit
            # tests that exercise _dispatch directly without starting
            # the pipeline; production goes through start_pipeline().
            self._invoke_on_event(event)
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            _log.warning(
                "pipeline queue full (size=%d), dropping callback for %s",
                self._queue_size,
                event.data.get("path"),
            )

    def _invoke_on_event(self, event: Event) -> None:
        assert self.on_event is not None
        try:
            self.on_event(event)
        except Exception:
            _log.exception(
                "on_event callback failed for %s", event.data.get("path")
            )

    def _run_worker(self) -> None:
        # Bind to a local so an abandoned worker (after stop_pipeline
        # times out and the watcher resets self._queue to None) can
        # still finish its current task cleanly.
        q = self._queue
        assert q is not None
        while True:
            try:
                event = q.get(timeout=self._WORKER_POLL_INTERVAL)
            except queue.Empty:
                if self._stopping.is_set():
                    return
                continue
            try:
                self._invoke_on_event(event)
            finally:
                q.task_done()

    def start_pipeline(self) -> None:
        """Spin up the worker thread that drains pipeline callbacks."""
        if self.on_event is None or self._worker is not None:
            return
        self._queue = queue.Queue(maxsize=self._queue_size)
        self._stopping.clear()
        self._worker = threading.Thread(
            target=self._run_worker, daemon=True, name="karasu-pipeline"
        )
        self._worker.start()

    def stop_pipeline(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait up to ``timeout`` seconds.

        The worker continues draining the queue until ``timeout`` elapses;
        any in-flight callback that hangs (e.g., stuck subprocess or
        network call) is abandoned with a warning rather than holding the
        shutdown forever. The worker is a daemon thread, so an abandoned
        callback dies with the process.
        """
        if self._worker is None:
            return
        self._stopping.set()
        self._worker.join(timeout=timeout)
        if self._worker.is_alive():
            _log.warning(
                "pipeline worker did not exit within %.1fs; abandoning queue",
                timeout,
            )
        self._worker = None
        self._queue = None

    def start(self) -> None:
        self.start_pipeline()
        self._observer.schedule(_Handler(self), str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
        self.stop_pipeline()

    def run_forever(self, poll_interval: float = 1.0) -> None:
        self.start()
        try:
            while True:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stop()
