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
parallelism, no retries beyond the bounded chain cap.

Issue #47 — chain cap with origin-aware tracking. Resubmits are
bounded per chain (walking ``resubmit_origin`` transitively to
the root), not per single originating id, so that distributed
chains where each ``/scar`` produces a fresh ``agent_response``
correlated to a new ``file_change.id`` cannot extend without
limit. See ``docs/phase-3-cap-design.md`` for the design and the
F-CAP-1..F-CAP-5 failure modes.

See ``docs/phase-3-loop-controller.md`` for the contract.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from karasu.controller.sources import TriggerSource
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
    # Chain cap with origin-aware tracking (issue #47, design in
    # docs/phase-3-cap-design.md).
    #
    # CHAIN_CAP bounds the TOTAL number of resubmits that can occur
    # in a chain rooted at a single originating file_change. Spam at
    # depth 1 (same agent_response /scar'd N times) and progressing
    # chains both increment the SAME counter, both bounded here.
    # That preserves the Phase 3 dogfood behaviour
    # (RESUBMIT_CAP=3 was per-originating-id and bounded the same
    # spam case at the same magnitude).
    #
    # MAX_CHAIN_WALK_DEPTH bounds the walk cost (F-CAP-5). A forged
    # or cyclic resubmit_origin lineage cannot otherwise spin
    # _chain_root forever or burn CPU on every dispatch. 64 hops is
    # ~21x the cap — wide margin for legitimate use, narrow enough
    # to fail fast on adversarial input.
    #
    # CHAIN_COUNTS_MAX_SIZE bounds the in-memory dict growth
    # (F-CAP-3). When the dict exceeds the ceiling the oldest entry
    # (insertion-order) is evicted; the operator gets one fresh shot
    # at a chain whose counter was evicted — same trade-off as the
    # F-WH-2 dedup ring.
    CHAIN_CAP = 3
    MAX_CHAIN_WALK_DEPTH = 64
    CHAIN_COUNTS_MAX_SIZE = 1024

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
        # Chain root id → resubmit count for that chain. Bounded
        # by CHAIN_COUNTS_MAX_SIZE with insertion-order eviction
        # when full. In-memory and per-process — does NOT survive
        # restart by design (live counter; persisted depth on bus
        # events lets analyze audit chain depth across restarts).
        self._chain_counts: dict[str, int] = {}
        self._chain_lock = threading.Lock()
        # Trigger sources (chunk 3c). Each source's start() runs after
        # the worker + bus subscription are up; stop() runs first on
        # shutdown so producers stop emitting before the worker drains.
        self._sources: list[TriggerSource] = []

    def add_source(self, source: TriggerSource) -> None:
        """Register a long-running trigger source.

        Order of registration is order of start(). Sources can be
        added before :meth:`start` (they will be started by it) or
        after (they must be started by the caller — the controller
        only manages sources that were registered before start).
        """
        self._sources.append(source)

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
        # Chunk 3c — start each registered trigger source AFTER the
        # worker and bus thread are running. Sources may begin
        # producing events immediately; they need the queue and
        # subscription in place to handle them.
        for source in self._sources:
            try:
                source.start()
            except Exception:
                _log.exception(
                    "controller: trigger source %r failed to start",
                    type(source).__name__,
                )

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
        """Signal trigger sources, bus subscription, and worker to stop.

        Order:
        1. Trigger sources first — stop producing before the worker
           drains, otherwise dropped-on-shutdown events look like
           bugs in the worker.
        2. Bus subscription — one last reaction window, then exit.
        3. Worker — drains the queue and exits.

        If any thread hangs past the timeout state stays intact so a
        future ``start`` raises rather than leaking.
        """
        # Trigger sources first (chunk 3c).
        for source in self._sources:
            try:
                source.stop()
            except Exception:
                _log.exception(
                    "controller: trigger source %r raised during stop",
                    type(source).__name__,
                )
        # Bus subscription next.
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

    def run_forever(self, poll_interval: float = 1.0) -> None:
        """Block until ``KeyboardInterrupt``, then stop cleanly.

        Calls :meth:`start` (which spawns the worker, bus
        subscription, and registered trigger sources), sleeps in a
        loop, and calls :meth:`stop` on Ctrl-C. Used by
        ``cmd_watch``; tests drive the lifecycle manually.
        """
        import time

        self.start()
        try:
            while True:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stop()

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

        Cap is per-chain (issue #47, Option B). Walks the resubmit
        lineage back to the chain root; the counter on that root
        bounds the total resubmits in the entire chain. Past the
        cap, log and skip — the surface already wrote the
        human_decision audit record on the bus, so the operator's
        correction is preserved even when the controller refuses
        to fire it again.

        New resubmit events persist ``controller_chain_depth`` on
        ``data`` so analyze can audit chain depth across restarts
        even though the live counter is in-memory only.
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
        root_id = self._chain_root(original, bus)
        with self._chain_lock:
            count = self._chain_counts.get(root_id, 0)
            if count >= self.CHAIN_CAP:
                _log.warning(
                    "controller resubmit: chain cap (%d) reached for "
                    "chain root %s; skipping",
                    self.CHAIN_CAP,
                    root_id,
                )
                return
            # F-CAP-3: bounded eviction. When the dict exceeds the
            # ceiling, evict the oldest entry (insertion order).
            # Worst case post-eviction: a /scar lands on the evicted
            # chain root and the operator gets one fresh shot —
            # same trade-off as the F-WH-10 dedup ring overflow.
            if (
                root_id not in self._chain_counts
                and len(self._chain_counts) >= self.CHAIN_COUNTS_MAX_SIZE
            ):
                evicted = next(iter(self._chain_counts))
                del self._chain_counts[evicted]
                _log.info(
                    "controller chain counts: evicted oldest entry %s "
                    "(ceiling=%d)",
                    evicted,
                    self.CHAIN_COUNTS_MAX_SIZE,
                )
            self._chain_counts[root_id] = count + 1

        # F-CAP-2: only trust controller_chain_depth on events the
        # controller itself emitted. For any other source the field
        # is untrusted input and depth resets to 1 (this resubmit is
        # the first hop on a chain rooted at ``original``).
        if (
            original.source == "controller"
            and isinstance(original.data.get("controller_chain_depth"), int)
        ):
            new_depth = original.data["controller_chain_depth"] + 1
        else:
            new_depth = 1

        new_event = bus.append(
            Event(
                type="file_change",
                source="controller",
                data={
                    **original.data,
                    "controller_resubmit": True,
                    "resubmit_origin": original.id,
                    "controller_chain_depth": new_depth,
                },
            )
        )
        self.submit(new_event)

    def _chain_root(self, file_change: Event, bus: JsonlEventBus) -> str:
        """Walk ``resubmit_origin`` back to the chain root id.

        Defences:

        - F-CAP-1: missing parent (log-rotated away or partial
          replay) → treat the current cursor as root and stop.
        - F-CAP-2: only follow lineage on ``source="controller"``
          events with ``controller_resubmit=True``. External
          sources can carry ``controller_resubmit`` /
          ``resubmit_origin`` / ``controller_chain_depth`` as
          untrusted strings and we MUST NOT walk through them.
        - F-CAP-5: bounded walk via ``visited`` (cycle break)
          AND ``MAX_CHAIN_WALK_DEPTH`` (forged-deep-lineage
          break). On either trip, treat the current cursor as
          root.
        """
        cursor = file_change
        visited: set[str] = set()
        for _ in range(self.MAX_CHAIN_WALK_DEPTH):
            if cursor.id in visited:
                return cursor.id  # F-CAP-5: cycle detected
            visited.add(cursor.id)
            if cursor.source != "controller":
                return cursor.id  # F-CAP-2
            if not cursor.data.get("controller_resubmit"):
                return cursor.id
            parent_id = cursor.data.get("resubmit_origin")
            if not isinstance(parent_id, str) or not parent_id:
                return cursor.id
            parent = self._find_file_change(bus, parent_id)
            if parent is None:
                return cursor.id  # F-CAP-1: parent log-rotated away
            cursor = parent
        # F-CAP-5: walk depth ceiling reached. Treat the deepest
        # reached cursor as root rather than continuing forever.
        return cursor.id

    @staticmethod
    def _find_file_change(
        bus: JsonlEventBus, event_id: str
    ) -> Event | None:
        for event in bus.read():
            if event.id == event_id and event.type == "file_change":
                return event
        return None
