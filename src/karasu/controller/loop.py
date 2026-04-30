"""Single-worker dispatch controller.

Phase 3 chunk 3a — refactor wrapper. Owns one bounded queue and one
worker thread. Submitted events are processed in order through the
configured callback (the :class:`Pipeline` in production). No
parallelism, no retries, no reaction logic — those land in chunks
3b and 3c.

The watcher's previous internal worker is replaced by this class.
Bus output is bit-for-bit identical for any fixed event sequence;
the parity test in ``tests/test_controller.py`` enforces that.

See ``docs/phase-3-loop-controller.md`` for the contract.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from karasu.eventbus import Event

Callback = Callable[[Event], None]

_log = logging.getLogger(__name__)


class LoopController:
    """Single-worker dispatch coordinator.

    Lifecycle:
    - Construct with a callback (typically the :class:`Pipeline`).
    - :meth:`start` spawns the worker thread and creates the queue.
    - :meth:`submit` enqueues events; before :meth:`start` it falls
      back to a synchronous call so unit tests can exercise the
      controller without managing thread state.
    - :meth:`stop` signals the worker, joins with a timeout, and
      clears state. If the worker hangs past the timeout the state
      stays intact so a future :meth:`start` refuses rather than
      silently leaking a second worker against an abandoned queue.
    """

    DEFAULT_QUEUE_SIZE = 1024
    _WORKER_POLL_INTERVAL = 0.1

    def __init__(
        self,
        callback: Callback,
        queue_size: int | None = None,
    ) -> None:
        self.callback = callback
        self._queue_size = queue_size or self.DEFAULT_QUEUE_SIZE
        self._queue: queue.Queue[Event] | None = None
        self._worker: threading.Thread | None = None
        self._stopping: threading.Event | None = None

    def submit(self, event: Event) -> None:
        """Enqueue ``event`` for the worker.

        Synchronous fallback when the worker is not running — used
        by tests that exercise dispatch without lifecycle setup.
        """
        if self._queue is None:
            self._invoke(event)
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            _log.warning(
                "controller queue full (size=%d), dropping callback for %s",
                self._queue_size,
                event.data.get("path"),
            )

    def _invoke(self, event: Event) -> None:
        try:
            self.callback(event)
        except Exception:
            _log.exception(
                "controller callback failed for %s", event.data.get("path")
            )

    def _run_worker(
        self,
        q: "queue.Queue[Event]",
        stopping: threading.Event,
    ) -> None:
        # Per-worker queue and stop signal are passed in so an
        # abandoned worker (after stop times out) keeps its own
        # state and can never be confused by a subsequent start
        # that creates fresh objects on the controller.
        while True:
            try:
                event = q.get(timeout=self._WORKER_POLL_INTERVAL)
            except queue.Empty:
                if stopping.is_set():
                    return
                continue
            try:
                self._invoke(event)
            finally:
                q.task_done()

    def start(self) -> None:
        if self._worker is not None:
            if self._worker.is_alive():
                raise RuntimeError(
                    "controller worker from a previous start is still "
                    "alive (stop timed out); cannot restart until it "
                    "exits"
                )
            self._worker = None
            self._queue = None
            self._stopping = None
        self._queue = queue.Queue(maxsize=self._queue_size)
        self._stopping = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(self._queue, self._stopping),
            daemon=True,
            name="karasu-controller",
        )
        self._worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait up to ``timeout`` seconds.

        If the worker is mid-callback when ``stop`` fires it keeps
        draining; an abandoned hang leaves controller state intact
        so a future ``start`` raises rather than leaking.
        """
        if self._worker is None or self._stopping is None:
            return
        self._stopping.set()
        self._worker.join(timeout=timeout)
        if self._worker.is_alive():
            _log.warning(
                "controller worker did not exit within %.1fs; abandoning "
                "queue. start will refuse a restart until it exits.",
                timeout,
            )
            return
        self._worker = None
        self._queue = None
        self._stopping = None
