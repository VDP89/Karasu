"""Three-layer rate limit for push delivery (brief §3-D).

Composition (outermost first):

  Layer 1 — UI-write suppression (pin §11.6.9 binding).
            ``event.source == "ui"`` events drop here so they
            never consume Layer-2 / Layer-3 slots. The
            classifier (:mod:`._classifier`) ALSO returns
            ``None`` for source="ui" human_decision events;
            this defence-in-depth catches any future event
            type that emerges with source="ui".

  Layer 2 — Per-category TRAILING debounce (pin §11.6.14
            binding). Per ``(endpoint_hash, category)`` at
            most one push per debounce window (5 s default).
            Events arriving within the window are coalesced;
            the SINGLE push that fires after the quiet period
            carries the MOST RECENT event in the burst.

            State machine with race protection (Codex P1 round
            2): ``threading.Timer.cancel()`` is best-effort —
            an old timer can already be executing its callback
            when ``cancel()`` returns. A monotonic per-entry
            generation token + a shared mutex + a guard that
            checks the token against the current entry before
            popping ensures stale timers no-op cleanly.

  Layer 3 — Per-(endpoint, event_id) dedupe (pin §11.6.5
            implicit). Bounded ring (last N=64 dispatched
            event ids per endpoint). NOT persisted;
            restart-cleared by design.

The dispatcher callback fires OUTSIDE the lock so a slow push
service does not serialise unrelated ``on_event`` arrivals
(Codex P1 round 2 lock-released-before-dispatch binding).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Protocol

from karasu.eventbus import Event


# Brief §10.5 binding default. Per-category override via env
# var deferred to a future chunk if dogfood demands it.
DEFAULT_DEBOUNCE_SECONDS = 5.0

# Brief §10.6 binding — last N=64 dispatched event ids per
# subscription. NOT persisted; restart-cleared.
DEFAULT_DEDUP_RING_SIZE = 64

_UI_SOURCE = "ui"


class _CancellableTimer(Protocol):
    """The subset of ``threading.Timer`` :class:`RateLimit`
    actually uses. Mockable for tests."""

    def start(self) -> None: ...

    def cancel(self) -> None: ...


TimerFactory = Callable[
    [float, Callable[..., None], tuple], _CancellableTimer
]


def _real_timer_factory(
    delay: float,
    fn: Callable[..., None],
    args: tuple,
) -> _CancellableTimer:
    timer = threading.Timer(delay, fn, args=args)
    timer.daemon = True
    return timer


# Dispatcher signature: takes the event + the endpoint_hash +
# the category. The endpoint_hash (audit-only per pin §11.6.6)
# is what reaches the dispatcher; the raw endpoint is looked
# up by :class:`PushEmit` via the store at the moment of
# dispatch (so a pruned subscription doesn't get a delayed
# push).
Dispatcher = Callable[[Event, str, str], None]


@dataclass
class _PendingEntry:
    event: Event
    timer: _CancellableTimer
    generation: int


class RateLimit:
    """Three-layer rate limiter; one instance per
    :class:`PushEmit`.

    Threading: all mutations of ``_pending`` and ``_dedup`` are
    serialised through ``_lock``. The dispatcher callback fires
    OUTSIDE the lock (Codex P1 round 2 binding) so slow HTTP
    does not block sibling :meth:`on_event` calls.
    """

    def __init__(
        self,
        *,
        dispatcher: Dispatcher,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        dedup_ring_size: int = DEFAULT_DEDUP_RING_SIZE,
        timer_factory: TimerFactory | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._debounce_seconds = float(debounce_seconds)
        self._dedup_ring_size = int(dedup_ring_size)
        self._timer_factory = timer_factory or _real_timer_factory
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, str], _PendingEntry] = {}
        self._dedup: dict[str, Deque[str]] = {}

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def on_event(
        self,
        event: Event,
        endpoint_hash: str,
        category: str,
    ) -> None:
        """Layer-1-2-3 entry point.

        Layer 1 first: source="ui" events are filtered before
        any state mutation. The classifier already filters them
        out for the corrections category; this catches any
        other source="ui" event type a future chunk introduces.
        """
        # Layer 1 — UI-write suppression (pin §11.6.9).
        if event.source == _UI_SOURCE:
            return

        # Layer 2 — trailing debounce.
        with self._lock:
            key = (endpoint_hash, category)
            previous = self._pending.get(key)
            if previous is not None:
                # cancel() is best-effort; the generation token
                # check inside _dispatch_pending will discard
                # any stale timer that already started its
                # callback.
                previous.timer.cancel()
                next_gen = previous.generation + 1
            else:
                next_gen = 0
            timer = self._timer_factory(
                self._debounce_seconds,
                self._dispatch_pending,
                (endpoint_hash, category, next_gen),
            )
            self._pending[key] = _PendingEntry(
                event=event, timer=timer, generation=next_gen
            )
        # start() runs OUTSIDE the lock so a (test-only) timer
        # factory whose start() is synchronous cannot deadlock
        # against this method's own lock. threading.Timer.start
        # only spawns a thread; it does not block here.
        timer.start()

    def stop(self) -> None:
        """Cancel all pending timers and drop in-memory state.

        Called by :class:`PushEmit.stop`. The ring buffer of
        dispatched ids and the pending-debounce dict are
        in-memory only (brief §10.6: restart-cleared by design)
        — there is no persisted state to flush.
        """
        with self._lock:
            for entry in self._pending.values():
                try:
                    entry.timer.cancel()
                except Exception:  # pragma: no cover - defensive
                    pass
            self._pending.clear()
            self._dedup.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _dispatch_pending(
        self,
        endpoint_hash: str,
        category: str,
        gen_token: int,
    ) -> None:
        """Timer-fired callback: dispatch the most-recent event
        for ``(endpoint_hash, category)`` if the generation
        token still matches.

        Race protection contract:

          * ``cancel()`` was called when a newer event arrived
            in the same key, but ``cancel()`` is best-effort —
            this callback may already be running when the new
            ``on_event`` lands.
          * If our ``gen_token`` doesn't match the entry's
            current generation, we are a stale callback whose
            replacement has its own scheduled timer; we no-op.
          * If the entry is already gone (someone else
            dispatched it), we no-op.
          * Otherwise we pop the entry, record the event id in
            the dedup ring, and dispatch OUTSIDE the lock.
        """
        key = (endpoint_hash, category)
        # Resolve under the lock.
        with self._lock:
            entry = self._pending.get(key)
            if entry is None:
                return  # already dispatched / stop() ran
            if entry.generation != gen_token:
                return  # superseded
            event = entry.event
            del self._pending[key]

            # Layer 3 — event-id dedupe under the lock too,
            # because the ring is shared mutable state.
            ring = self._dedup.setdefault(
                endpoint_hash,
                deque(maxlen=self._dedup_ring_size),
            )
            if event.id in ring:
                return  # already dispatched this event id
            ring.append(event.id)

        # Lock released BEFORE dispatch (Codex P1 round 2
        # binding) so a slow push service does not block
        # sibling on_event calls.
        try:
            self._dispatcher(event, endpoint_hash, category)
        except Exception:
            # Dispatcher exceptions must not poison the rate
            # limiter; the dispatcher's own log discipline
            # records the failure.
            import logging

            logging.getLogger(__name__).exception(
                "rate-limit dispatcher raised; ignoring"
            )

    # ------------------------------------------------------------------
    # Test helpers (introspection only — not public API)
    # ------------------------------------------------------------------

    def _pending_size(self) -> int:
        with self._lock:
            return len(self._pending)

    def _dedup_size(self, endpoint_hash: str) -> int:
        with self._lock:
            return len(self._dedup.get(endpoint_hash, ()))
