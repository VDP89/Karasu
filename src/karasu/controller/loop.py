"""Single-worker dispatch controller.

Phase 3 chunk 3a — refactor wrapper. Owns one bounded queue and one
worker thread. Submitted events are processed in order through the
configured callback (the :class:`Pipeline` in production).

Phase 3 chunk 3b — react to ``human_decision`` events. When a
``JsonlEventBus`` is supplied, :meth:`start` also spawns a bus
subscription thread that polls the bus and resubmits the originating
``file_change`` whenever the surface records a ``/correct`` or
``/scar`` text. The pipeline still does NOT consume ``human_decision``
directly — only the controller does — and the resubmit fires through
the same single worker as the watcher's regular events. No
parallelism, no retries beyond the bounded resubmit cap.

See ``docs/phase-3-loop-controller.md`` for the contract.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader

Callback = Callable[[Event], None]

_log = logging.getLogger(__name__)


class LoopController:
    """Single-worker dispatch coordinator with optional bus reactions.

    Lifecycle:
    - Construct with a callback (typically the :class:`Pipeline`).
    - :meth:`start` spawns the worker thread and creates the queue.
      If a ``bus`` was supplied at construction, also spawns the
      bus-subscription thread for chunk-3b reactions.
    - :meth:`submit` enqueues events; before :meth:`start` it falls
      back to a synchronous call so unit tests can exercise the
      controller without managing thread state.
    - :meth:`stop` signals the bus subscription first, then the
      worker, joining each with a timeout. If a thread hangs past
      the timeout state stays intact so a future :meth:`start`
      refuses rather than silently leaking a second worker against
      an abandoned queue.
    """

    DEFAULT_QUEUE_SIZE = 1024
    _WORKER_POLL_INTERVAL = 0.1
    _BUS_POLL_INTERVAL = 0.5
    # Cap resubmits per originating file_change id. Phase 1 had no
    # retry semantics; chunk 3b introduces one bounded reaction so a
    # human spamming /scar (or a misbehaving surface) cannot drive
    # the dispatcher in an unbounded loop. Phase 3+ may extend the
    # key shape (e.g. (id, scar_id)) once we have escalation events.
    RESUBMIT_CAP = 3

    def __init__(
        self,
        callback: Callback,
        queue_size: int | None = None,
        bus: JsonlEventBus | None = None,
    ) -> None:
        self.callback = callback
        self.bus = bus
        self._queue_size = queue_size or self.DEFAULT_QUEUE_SIZE
        self._queue: queue.Queue[Event] | None = None
        self._worker: threading.Thread | None = None
        self._stopping: threading.Event | None = None
        # Bus subscription state (chunk 3b). Only populated when
        # ``bus`` was supplied AND :meth:`start` has been called.
        self._bus_thread: threading.Thread | None = None
        self._bus_stopping: threading.Event | None = None
        self._bus_reader: JsonlTailReader | None = None
        self._resubmit_counts: dict[str, int] = {}
        self._resubmit_lock = threading.Lock()

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
        # Chunk 3b — opt-in bus subscription. The watcher cmd_watch
        # builds the controller with ``bus`` set, so this fires
        # alongside the worker. Tests that don't care about
        # reactions construct the controller without ``bus`` and
        # this branch is a no-op.
        if self.bus is not None and self._bus_thread is None:
            self._start_bus_subscription_locked()

    def _start_bus_subscription_locked(self) -> None:
        # Caller must guarantee no live bus thread exists.
        assert self.bus is not None
        self._bus_reader = JsonlTailReader(self.bus.path, start_at_end=True)
        self._bus_stopping = threading.Event()
        self._bus_thread = threading.Thread(
            target=self._run_bus_subscription,
            args=(self._bus_reader, self._bus_stopping, self.bus),
            daemon=True,
            name="karasu-controller-bus",
        )
        self._bus_thread.start()

    def _run_bus_subscription(
        self,
        reader: JsonlTailReader,
        stopping: threading.Event,
        bus: JsonlEventBus,
    ) -> None:
        # Same shape as the worker loop: poll, dispatch, swallow
        # exceptions per event so the subscription survives bad
        # input and keeps observing the bus.
        while not stopping.is_set():
            try:
                events = reader.read_new()
            except Exception:
                _log.exception("controller bus reader failed")
                events = []
            for event in events:
                try:
                    self.on_bus_event(event, bus)
                except Exception:
                    _log.exception(
                        "controller on_bus_event failed for event %s",
                        event.id,
                    )
            stopping.wait(timeout=self._BUS_POLL_INTERVAL)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker (and bus subscription) to stop.

        Bus subscription is signalled first so any in-flight reaction
        gets one last submit chance. Then the worker. If either hangs
        past the timeout state stays intact so a future ``start``
        raises rather than leaking.
        """
        # Bus subscription first.
        if self._bus_thread is not None and self._bus_stopping is not None:
            self._bus_stopping.set()
            self._bus_thread.join(timeout=timeout)
            if self._bus_thread.is_alive():
                _log.warning(
                    "controller bus subscription did not exit within "
                    "%.1fs; abandoning. start will refuse a restart "
                    "until it exits.",
                    timeout,
                )
                # Leave _bus_thread populated so start() refuses.
                return
            self._bus_thread = None
            self._bus_stopping = None
            self._bus_reader = None
        # Then the worker.
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

    # ------------------------------------------------------------------
    # Chunk 3b — bus reaction
    # ------------------------------------------------------------------

    def on_bus_event(self, event: Event, bus: JsonlEventBus) -> None:
        """Inspect a bus event and react if it's a ``/correct`` or
        ``/scar``.

        Other event types (``file_change``, ``agent_response``,
        ``scar_consultation``, etc.) are no-ops — the pipeline already
        handled them. Redacted ``human_decision`` texts (those
        containing ``(unauthorized)`` or ``(unknown command)``, written
        by the surface for rejected attempts) are also skipped: by
        construction the args are not available, so there is nothing
        to react to.
        """
        if event.type != "human_decision":
            return
        text = (event.data.get("text") or "").strip()
        if not text:
            return
        if "(unauthorized)" in text or "(unknown command)" in text:
            return
        parts = text.split(None, 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        if cmd == "/correct":
            self._react_correct(args, bus)
        elif cmd == "/scar":
            self._react_scar(bus)

    def _react_correct(self, args: str, bus: JsonlEventBus) -> None:
        # ``/correct <prefix> field=value field=value ...`` — only
        # the prefix matters for routing the resubmit; the surface
        # already recorded the Scar in chunk 3, so the controller
        # only needs to find the originating file_change.
        from karasu.interface.commands import find_agent_response

        tokens = args.split(None, 1)
        if not tokens:
            _log.warning("controller /correct: empty prefix; skipping")
            return
        prefix = tokens[0]
        try:
            target = find_agent_response(bus, prefix)
        except ValueError as exc:
            _log.warning("controller /correct prefix %r: %s", prefix, exc)
            return
        if target is None:
            _log.warning(
                "controller /correct: prefix %r matched no agent_response",
                prefix,
            )
            return
        self._resubmit_for(target, bus)

    def _react_scar(self, bus: JsonlEventBus) -> None:
        from karasu.interface.commands import latest_agent_response

        target = latest_agent_response(bus)
        if target is None:
            _log.warning(
                "controller /scar: no agent_response on bus; skipping"
            )
            return
        self._resubmit_for(target, bus)

    def _resubmit_for(self, agent_response: Event, bus: JsonlEventBus) -> None:
        """Resubmit the file_change correlated with ``agent_response``.

        Cap is per-originating-id. Past the cap, log and skip — the
        surface already wrote the human_decision audit record on the
        bus, so the operator's correction is preserved even when the
        controller refuses to fire it again.
        """
        correlates_id = agent_response.data.get("correlates")
        if not correlates_id:
            _log.warning(
                "controller resubmit: agent_response %s has no correlates",
                agent_response.id,
            )
            return
        original = self._find_file_change(bus, correlates_id)
        if original is None:
            _log.warning(
                "controller resubmit: originating file_change %s not "
                "found on bus; skipping",
                correlates_id,
            )
            return
        with self._resubmit_lock:
            count = self._resubmit_counts.get(original.id, 0)
            if count >= self.RESUBMIT_CAP:
                _log.warning(
                    "controller resubmit: cap (%d) reached for "
                    "file_change %s; skipping",
                    self.RESUBMIT_CAP,
                    original.id,
                )
                return
            self._resubmit_counts[original.id] = count + 1

        new_event = bus.append(
            Event(
                type="file_change",
                source="controller",
                data={
                    **original.data,
                    "controller_resubmit": True,
                    "resubmit_origin": original.id,
                },
            )
        )
        self.submit(new_event)

    @staticmethod
    def _find_file_change(
        bus: JsonlEventBus, event_id: str
    ) -> Event | None:
        for event in bus.read():
            if event.id == event_id and event.type == "file_change":
                return event
        return None
