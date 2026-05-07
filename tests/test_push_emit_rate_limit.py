"""Three-layer rate limit tests (brief §3-D + §3-I).

Covers:

  * Layer 1 alone: source="ui" event suppressed; no Layer-2
    or Layer-3 slot consumed.
  * Layer 2 alone: two events <5s apart in same category for
    same endpoint → second debounced; burst-most-recent wins.
  * Layer 3 alone: same event_id twice → second deduped.
  * L1 + L2 + L3 in combination: UI-write event in burst →
    suppressed at L1 even with dedupe slots saturated.
  * Restart clears state: in-memory dedupe ring + debounce
    timestamps reset on restart.
  * Race protection (Codex P1 round 2):
      - test_old_cancelled_timer_fires_after_replacement
      - test_arrival_races_with_expiry
      - test_dispatch_does_not_hold_lock_during_http

A fake :class:`Timer` is injected so the tests fire callbacks
deterministically rather than relying on wall-clock sleeps.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import pytest

from karasu.eventbus import Event
from karasu.push_emit._rate_limit import (
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_DEDUP_RING_SIZE,
    RateLimit,
)


# ---------------------------------------------------------------------------
# Fake timer that NEVER fires automatically — tests call .fire()
# ---------------------------------------------------------------------------


class FakeTimer:
    """Records the (delay, fn, args) it was constructed with;
    fires only when :meth:`fire` is called explicitly."""

    def __init__(
        self, delay: float, fn: Callable[..., None], args: tuple
    ) -> None:
        self.delay = delay
        self.fn = fn
        self.args = args
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        """Invoke the callback synchronously, simulating the
        timer expiring."""
        self.fn(*self.args)


@pytest.fixture
def factory_record() -> list[FakeTimer]:
    return []


@pytest.fixture
def fake_timer_factory(
    factory_record: list[FakeTimer],
) -> Callable[..., FakeTimer]:
    def make(delay: float, fn: Callable[..., None], args: tuple) -> FakeTimer:
        timer = FakeTimer(delay, fn, args)
        factory_record.append(timer)
        return timer

    return make


@pytest.fixture
def captured_dispatches() -> list[tuple[Event, str, str]]:
    return []


@pytest.fixture
def dispatcher(
    captured_dispatches: list[tuple[Event, str, str]],
) -> Callable[..., None]:
    def dispatch(event: Event, endpoint_hash: str, category: str) -> None:
        captured_dispatches.append((event, endpoint_hash, category))

    return dispatch


@pytest.fixture
def rate_limit(
    dispatcher: Callable[..., None],
    fake_timer_factory: Callable[..., FakeTimer],
) -> RateLimit:
    return RateLimit(
        dispatcher=dispatcher,
        debounce_seconds=5.0,
        dedup_ring_size=64,
        timer_factory=fake_timer_factory,
    )


def _ev(
    *,
    src: str = "watcher",
    type: str = "agent_response",
    id: str | None = None,
) -> Event:
    return Event(type=type, source=src, id=id or _new_id())


_id_counter = 0


def _new_id() -> str:
    global _id_counter
    _id_counter += 1
    return f"event-{_id_counter}"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults_match_brief() -> None:
    """Brief §10.5 + §10.6 binding defaults."""
    assert DEFAULT_DEBOUNCE_SECONDS == 5.0
    assert DEFAULT_DEDUP_RING_SIZE == 64


# ---------------------------------------------------------------------------
# Layer 1 — UI-write suppression
# ---------------------------------------------------------------------------


def test_layer1_ui_source_event_suppressed(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """source="ui" never schedules a timer + never reaches
    dispatch. Pin §11.6.9 binding."""
    ev = _ev(src="ui", type="human_decision")
    rate_limit.on_event(ev, "abc123", "corrections")

    assert factory_record == []          # no timer scheduled
    assert captured_dispatches == []     # no dispatch
    assert rate_limit._pending_size() == 0


def test_layer1_does_not_consume_dedup_slot(
    rate_limit: RateLimit,
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """A burst of source="ui" events must not fill the dedup
    ring — the suppression happens BEFORE Layer 3."""
    for _ in range(100):
        rate_limit.on_event(
            _ev(src="ui", type="human_decision"),
            "abc",
            "corrections",
        )
    assert rate_limit._dedup_size("abc") == 0
    assert captured_dispatches == []


# ---------------------------------------------------------------------------
# Layer 2 — trailing debounce
# ---------------------------------------------------------------------------


def test_layer2_single_event_dispatches_after_timer_fires(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    ev = _ev()
    rate_limit.on_event(ev, "abc", "attention")

    assert len(factory_record) == 1
    assert factory_record[0].started is True
    assert factory_record[0].delay == 5.0
    assert captured_dispatches == []  # not fired yet

    factory_record[0].fire()

    assert len(captured_dispatches) == 1
    assert captured_dispatches[0] == (ev, "abc", "attention")


def test_layer2_burst_most_recent_wins(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Brief §3-D: events arriving within the window are
    coalesced; the SINGLE push that fires after the quiet
    period carries the MOST RECENT event."""
    ev1 = _ev()
    ev2 = _ev()
    ev3 = _ev()

    rate_limit.on_event(ev1, "abc", "attention")
    rate_limit.on_event(ev2, "abc", "attention")
    rate_limit.on_event(ev3, "abc", "attention")

    # Three timers were created (one per arrival); the first
    # two were cancelled.
    assert len(factory_record) == 3
    assert factory_record[0].cancelled is True
    assert factory_record[1].cancelled is True
    assert factory_record[2].cancelled is False

    # Fire the LATEST timer — it dispatches ev3 only.
    factory_record[2].fire()
    assert len(captured_dispatches) == 1
    assert captured_dispatches[0][0] is ev3


def test_layer2_per_category_isolated(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Two events at the same endpoint but different
    categories DO NOT debounce each other — the pending key
    is (endpoint_hash, category)."""
    ev_a = _ev()
    ev_e = _ev()

    rate_limit.on_event(ev_a, "abc", "attention")
    rate_limit.on_event(ev_e, "abc", "errors")

    assert len(factory_record) == 2
    # Neither was cancelled.
    assert factory_record[0].cancelled is False
    assert factory_record[1].cancelled is False

    factory_record[0].fire()
    factory_record[1].fire()
    assert len(captured_dispatches) == 2


def test_layer2_per_endpoint_isolated(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    rate_limit.on_event(_ev(), "endpoint-A", "attention")
    rate_limit.on_event(_ev(), "endpoint-B", "attention")

    assert len(factory_record) == 2
    assert factory_record[0].cancelled is False
    assert factory_record[1].cancelled is False


# ---------------------------------------------------------------------------
# Layer 3 — event-id dedupe
# ---------------------------------------------------------------------------


def test_layer3_same_event_id_dispatched_at_most_once(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    ev = _ev(id="dup-id")
    rate_limit.on_event(ev, "abc", "attention")
    factory_record[0].fire()
    assert len(captured_dispatches) == 1

    # Same id arrives again (e.g. watcher restart replayed
    # the bus tail) → debounced + then dropped at Layer 3.
    rate_limit.on_event(ev, "abc", "attention")
    factory_record[1].fire()
    assert len(captured_dispatches) == 1  # still 1


def test_layer3_ring_bounded_at_size(
    dispatcher: Callable[..., None],
    fake_timer_factory: Callable[..., FakeTimer],
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Bounded ring per endpoint; oldest entries evict when
    the ring fills. Default size 64 is exercised here with
    size=3 for fast tests."""
    rl = RateLimit(
        dispatcher=dispatcher,
        debounce_seconds=5.0,
        dedup_ring_size=3,
        timer_factory=fake_timer_factory,
    )
    ids = ["a", "b", "c", "d"]
    for i, eid in enumerate(ids):
        rl.on_event(_ev(id=eid), "abc", "attention")
        factory_record[i].fire()

    # All four dispatched; the ring evicted "a" on "d"'s
    # arrival.
    assert len(captured_dispatches) == 4

    # Replay "a" — the ring no longer carries it, so it
    # dispatches again.
    rl.on_event(_ev(id="a"), "abc", "attention")
    factory_record[-1].fire()
    assert len(captured_dispatches) == 5


def test_layer3_per_endpoint_isolated(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Same event id arriving for two different endpoints
    dispatches twice (each endpoint owns its own ring)."""
    ev = _ev(id="shared")
    rate_limit.on_event(ev, "endpoint-A", "attention")
    factory_record[0].fire()
    rate_limit.on_event(ev, "endpoint-B", "attention")
    factory_record[1].fire()
    assert len(captured_dispatches) == 2


# ---------------------------------------------------------------------------
# Composition — Layer 1 + Layer 2 + Layer 3
# ---------------------------------------------------------------------------


def test_layer1_blocks_burst_filling_dedup_slots(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Brief §3-I: UI-write event in a burst → suppressed at
    L1 even with dedupe slots saturated."""
    # Saturate Layer 3 with 64 distinct ids first.
    for i in range(64):
        rate_limit.on_event(_ev(id=f"id-{i}"), "abc", "attention")
        factory_record[-1].fire()
    assert rate_limit._dedup_size("abc") == 64

    # Now a UI-write event arrives. Should NOT consume any
    # slot, NOT dispatch.
    rate_limit.on_event(
        _ev(src="ui", type="human_decision"), "abc", "corrections"
    )
    assert rate_limit._dedup_size("abc") == 64  # unchanged
    assert len(captured_dispatches) == 64


# ---------------------------------------------------------------------------
# stop() — drop in-memory state (restart-cleared by design)
# ---------------------------------------------------------------------------


def test_stop_cancels_pending_timers(
    rate_limit: RateLimit, factory_record: list[FakeTimer]
) -> None:
    rate_limit.on_event(_ev(), "abc", "attention")
    rate_limit.on_event(_ev(), "abc", "errors")
    rate_limit.stop()

    assert factory_record[0].cancelled is True
    assert factory_record[1].cancelled is True
    assert rate_limit._pending_size() == 0


def test_stop_clears_dedup_ring(
    rate_limit: RateLimit, factory_record: list[FakeTimer]
) -> None:
    rate_limit.on_event(_ev(id="x"), "abc", "attention")
    factory_record[0].fire()
    assert rate_limit._dedup_size("abc") == 1

    rate_limit.stop()
    assert rate_limit._dedup_size("abc") == 0


# ---------------------------------------------------------------------------
# Race protection (Codex P1 round 2)
# ---------------------------------------------------------------------------


def test_old_cancelled_timer_fires_after_replacement(
    rate_limit: RateLimit,
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """Force a cancelled timer to fire AFTER its replacement
    arrived. The generation token check no-ops the stale
    callback; the replacement still dispatches at its own
    fire."""
    ev1 = _ev()
    ev2 = _ev()

    rate_limit.on_event(ev1, "abc", "attention")
    rate_limit.on_event(ev2, "abc", "attention")
    # Two timers; the first was cancelled, the second is live.
    assert factory_record[0].cancelled is True

    # The cancelled timer's callback runs LATE (cancel() is
    # best-effort). It should no-op.
    factory_record[0].fire()
    assert captured_dispatches == []  # stale callback ignored

    # Replacement fires at its scheduled moment → dispatches.
    factory_record[1].fire()
    assert len(captured_dispatches) == 1
    assert captured_dispatches[0][0] is ev2


def test_arrival_races_with_expiry(
    dispatcher: Callable[..., None],
    fake_timer_factory: Callable[..., FakeTimer],
    factory_record: list[FakeTimer],
    captured_dispatches: list[tuple[Event, str, str]],
) -> None:
    """A burst of two arrivals at the same key produces ONE
    dispatch (the most recent event) even when the
    cancelled timer's callback runs after the replacement was
    enqueued. The race between cancel() and the callback is
    expressed here as fire-order: cancelled timer fires first
    (its generation token mismatches the current entry → no-op),
    replacement fires next (matches → dispatch).

    The threading-level race (callback waiting on state.lock
    while a new on_event holds it) is covered structurally by
    ``test_dispatch_does_not_hold_lock_during_http`` +
    ``test_old_cancelled_timer_fires_after_replacement``."""
    rl = RateLimit(
        dispatcher=dispatcher,
        debounce_seconds=5.0,
        timer_factory=fake_timer_factory,
    )

    ev1 = _ev()
    ev2 = _ev()

    rl.on_event(ev1, "abc", "attention")
    rl.on_event(ev2, "abc", "attention")
    factory_record[0].fire()  # cancelled timer; gen-token mismatch → no-op
    factory_record[1].fire()  # replacement; dispatches ev2

    assert len(captured_dispatches) == 1
    assert captured_dispatches[0][0] is ev2


def test_dispatch_does_not_hold_lock_during_http() -> None:
    """The dispatcher callback must run OUTSIDE the rate-limit
    lock. Otherwise a slow push service serialises every
    sibling on_event call.

    We assert the invariant by capturing the dispatcher's
    ability to call back into the rate limit AT THE SAME
    instant (without deadlock or back-pressure)."""
    record: list[str] = []
    inside_event = threading.Event()
    proceed = threading.Event()

    def slow_dispatcher(event: Event, eh: str, cat: str) -> None:
        # Signal we're inside dispatch + park.
        inside_event.set()
        record.append(f"dispatch:start:{event.id}")
        proceed.wait(timeout=2.0)
        record.append(f"dispatch:end:{event.id}")

    factory_record: list[FakeTimer] = []

    def make_fake(delay: float, fn: Any, args: tuple) -> FakeTimer:
        t = FakeTimer(delay, fn, args)
        factory_record.append(t)
        return t

    rl = RateLimit(
        dispatcher=slow_dispatcher,
        debounce_seconds=5.0,
        timer_factory=make_fake,
    )
    rl.on_event(_ev(id="slow"), "abc", "attention")

    # Fire the timer in a worker thread so we can keep the
    # main thread free to issue another on_event during the
    # slow dispatch.
    worker = threading.Thread(target=factory_record[0].fire)
    worker.start()

    # Wait until dispatch is in-flight.
    assert inside_event.wait(timeout=2.0)

    # NOW issue another on_event. If the lock is held during
    # dispatch, this call would block until proceed.set().
    started_at = time.monotonic()
    rl.on_event(_ev(id="other"), "xyz", "attention")
    elapsed = time.monotonic() - started_at

    # Less than the dispatcher's parked time — the lock was
    # NOT held.
    assert elapsed < 0.5, (
        f"on_event blocked {elapsed:.2f}s during slow dispatch — "
        "the lock was held across the callback (regression)"
    )
    assert rl._pending_size() == 1  # the new event scheduled

    # Release the slow dispatcher and clean up.
    proceed.set()
    worker.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Dispatcher exception swallowed (defensive)
# ---------------------------------------------------------------------------


def test_dispatcher_exception_does_not_break_rate_limit(
    fake_timer_factory: Callable[..., FakeTimer],
    factory_record: list[FakeTimer],
) -> None:
    """A dispatcher that raises must not poison the rate
    limit — subsequent events still process."""
    bad_calls: list[Event] = []

    def bad(event: Event, eh: str, cat: str) -> None:
        bad_calls.append(event)
        raise RuntimeError("dispatcher bug")

    rl = RateLimit(
        dispatcher=bad,
        debounce_seconds=5.0,
        timer_factory=fake_timer_factory,
    )
    rl.on_event(_ev(id="x"), "abc", "attention")
    factory_record[0].fire()  # raises inside dispatcher

    # Second event still processes.
    rl.on_event(_ev(id="y"), "abc", "attention")
    factory_record[1].fire()

    assert len(bad_calls) == 2


def test_dispatcher_exception_logs_only_type_not_message(
    fake_timer_factory: Callable[..., FakeTimer],
    factory_record: list[FakeTimer],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Codex P1 round 1 (UI-12c code audit): the broad-except
    around the dispatcher MUST NOT use ``logger.exception``
    (attaches exc_info + traceback) and MUST NOT emit the
    exception's args/message. Upstream callees can carry raw
    endpoint URLs or payload bytes in their args; a traceback
    would resurface them per pin §11.6.16."""
    sentinel = "SENTINEL_LEAK_TOKEN_https://fcm.test/abc-secret"

    def bad(event: Event, eh: str, cat: str) -> None:
        raise ValueError(sentinel)

    rl = RateLimit(
        dispatcher=bad,
        debounce_seconds=5.0,
        timer_factory=fake_timer_factory,
    )
    rl.on_event(_ev(id="x"), "abc", "attention")
    with caplog.at_level("DEBUG", logger="karasu.push_emit._rate_limit"):
        factory_record[0].fire()

    for record in caplog.records:
        msg = record.getMessage()
        assert sentinel not in msg
        assert "SENTINEL_LEAK_TOKEN" not in msg
        # Traceback would appear in record.exc_info / formatted
        # output if exc_info=True was used. Assert absent.
        assert record.exc_info is None
    # The TYPE is logged.
    assert any(
        "ValueError" in r.getMessage() for r in caplog.records
    )
