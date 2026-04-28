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
        debounce_ms: int = 0,
    ) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.ignore = tuple(ignore)
        self.on_event = on_event
        self._queue_size = queue_size or self.DEFAULT_QUEUE_SIZE
        self.debounce_ms = max(0, int(debounce_ms))
        self._observer = Observer()
        self._queue: queue.Queue[Event] | None = None
        self._worker: threading.Thread | None = None
        self._stopping: threading.Event | None = None
        # Per-(path, change_type) timestamp of the last dispatched event,
        # in monotonic seconds. Grows unbounded over a long-lived watcher;
        # acceptable for Phase 1 single-repo use, revisit if memory matters.
        self._last_dispatched: dict[tuple[str, str], float] = {}
        self._debounce_lock = threading.Lock()

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

    def _run_worker(
        self, q: "queue.Queue[Event]", stopping: threading.Event
    ) -> None:
        # Per-worker queue and stop signal are passed in so an abandoned
        # worker (after stop_pipeline times out) keeps its own state and
        # can never be confused by a subsequent start_pipeline that
        # creates fresh objects on the watcher.
        while True:
            try:
                event = q.get(timeout=self._WORKER_POLL_INTERVAL)
            except queue.Empty:
                if stopping.is_set():
                    return
                continue
            try:
                self._invoke_on_event(event)
            finally:
                q.task_done()

    def start_pipeline(self) -> None:
        """Spin up the worker thread that drains pipeline callbacks."""
        if self.on_event is None:
            return
        if self._worker is not None:
            if self._worker.is_alive():
                raise RuntimeError(
                    "pipeline worker from a previous start_pipeline is "
                    "still alive (stop_pipeline timed out); cannot restart "
                    "until it exits"
                )
            # Worker terminated since stop_pipeline returned — clear stale state.
            self._worker = None
            self._queue = None
            self._stopping = None
        self._queue = queue.Queue(maxsize=self._queue_size)
        self._stopping = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(self._queue, self._stopping),
            daemon=True,
            name="karasu-pipeline",
        )
        self._worker.start()

    def stop_pipeline(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait up to ``timeout`` seconds.

        The worker continues draining the queue until ``timeout`` elapses;
        any in-flight callback that hangs (e.g., stuck subprocess or
        network call) is abandoned with a warning rather than holding the
        shutdown forever. The worker is a daemon thread, so an abandoned
        callback dies with the process.

        If the timeout fires while the worker is still alive, watcher
        state (``_worker``/``_queue``/``_stopping``) is left intact so a
        future ``start_pipeline`` raises rather than silently leaking
        a second worker against an abandoned queue.
        """
        if self._worker is None or self._stopping is None:
            return
        self._stopping.set()
        self._worker.join(timeout=timeout)
        if self._worker.is_alive():
            _log.warning(
                "pipeline worker did not exit within %.1fs; abandoning queue. "
                "start_pipeline will refuse a restart until it exits.",
                timeout,
            )
            return
        self._worker = None
        self._queue = None
        self._stopping = None

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
