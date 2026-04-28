"""Tests for the Telegram bridge.

Network-free: the tail loop receives an injected fake ``send`` and
``sleep``, so no Telegram client is built and no HTTP calls are made.
"""

from __future__ import annotations

import asyncio

import pytest

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.interface import TelegramInterface


# ----------------------------------------------------------------------
# Whitelist (fail-closed).
# ----------------------------------------------------------------------


def test_is_allowed_empty_whitelist_refuses_everyone(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)
    assert interface.is_allowed(123) is False
    assert interface.is_allowed(0) is False


def test_is_allowed_user_in_whitelist(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, allowed_users=[42, 7])
    assert interface.is_allowed(42) is True
    assert interface.is_allowed(7) is True
    assert interface.is_allowed(8) is False


# ----------------------------------------------------------------------
# Event formatting.
# ----------------------------------------------------------------------


def test_format_event_decision(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"agent": "claude_code"},
        response={"content": "ran tests, 3 failures", "requires_human": True},
    )
    assert interface.format_event(event) == "[DECISION] claude_code: ran tests, 3 failures"


def test_format_event_info(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)
    event = Event(
        type="agent_response",
        source="adapter",
        dispatch={"agent": "codex"},
        response={"content": "review posted", "requires_human": False},
    )
    assert interface.format_event(event) == "[INFO] codex: review posted"


def test_format_event_missing_agent_uses_unknown(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)
    event = Event(
        type="agent_response",
        source="router",
        dispatch={"agent": None},
        response={"content": "no adapter", "requires_human": True},
    )
    assert interface.format_event(event) == "[DECISION] unknown: no adapter"


# ----------------------------------------------------------------------
# Inbound — record_decision wires through to the bus.
# ----------------------------------------------------------------------


def test_record_decision_appends_human_decision_event(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)
    interface.record_decision(user_id=42, text="approve")
    events = list(bus.read())
    assert len(events) == 1
    assert events[0].type == "human_decision"
    assert events[0].source == "interface"
    assert events[0].data == {"user": 42, "text": "approve"}


# ----------------------------------------------------------------------
# Outbound tail loop.
# ----------------------------------------------------------------------


class _FakeSink:
    """Collects (chat_id, text) tuples that ``tail_loop`` forwards."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.fail_next = False

    async def __call__(self, chat_id: int, text: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("transient telegram error")
        self.calls.append((chat_id, text))


def _stop_after(stop_event: asyncio.Event, ticks: int) -> "asyncio.Future[None]":
    """Schedule ``stop_event`` to fire after ``ticks`` calls to ``sleep``."""

    async def fake_sleep(_interval: float) -> None:
        nonlocal_ticks[0] -= 1
        if nonlocal_ticks[0] <= 0:
            stop_event.set()

    nonlocal_ticks = [ticks]
    return fake_sleep  # type: ignore[return-value]


async def test_tail_loop_forwards_agent_response(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=999)

    # Pre-populate one event before the reader is constructed; the
    # reader defaults to start_at_end=True so this should NOT be replayed.
    bus.append(Event(type="agent_response", source="adapter",
                     dispatch={"agent": "x"},
                     response={"content": "old", "requires_human": False}))

    reader = JsonlTailReader(bus.path)

    # New event after the reader is constructed — this is what tail_loop must surface.
    bus.append(Event(type="agent_response", source="adapter",
                     dispatch={"agent": "claude_code"},
                     response={"content": "new", "requires_human": True}))

    sink = _FakeSink()
    stop_event = asyncio.Event()
    sleep = _stop_after(stop_event, ticks=1)

    await interface.tail_loop(sink, reader=reader, stop_event=stop_event, sleep=sleep)

    assert sink.calls == [(999, "[DECISION] claude_code: new")]


async def test_tail_loop_skips_non_agent_response_events(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=999)
    reader = JsonlTailReader(bus.path)

    bus.append(Event(type="file_change", source="watcher", data={"path": "a.py"}))
    bus.append(Event(type="human_decision", source="interface", data={"user": 1, "text": "ok"}))

    sink = _FakeSink()
    stop_event = asyncio.Event()
    sleep = _stop_after(stop_event, ticks=1)

    await interface.tail_loop(sink, reader=reader, stop_event=stop_event, sleep=sleep)

    assert sink.calls == []


async def test_tail_loop_swallows_transient_send_errors(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=999)
    reader = JsonlTailReader(bus.path)

    bus.append(Event(type="agent_response", source="adapter",
                     dispatch={"agent": "a"},
                     response={"content": "first", "requires_human": False}))
    bus.append(Event(type="agent_response", source="adapter",
                     dispatch={"agent": "a"},
                     response={"content": "second", "requires_human": False}))

    sink = _FakeSink()
    sink.fail_next = True
    stop_event = asyncio.Event()
    sleep = _stop_after(stop_event, ticks=1)

    await interface.tail_loop(sink, reader=reader, stop_event=stop_event, sleep=sleep)

    # First send raised; loop continued and delivered the second event.
    assert sink.calls == [(999, "[INFO] a: second")]


async def test_tail_loop_returns_immediately_without_chat_id(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus)  # no chat_id

    sink = _FakeSink()

    # If chat_id is None the loop must return without ever calling sleep.
    async def sleep_should_not_run(_interval: float) -> None:
        pytest.fail("sleep should not be called when chat_id is None")

    await interface.tail_loop(sink, sleep=sleep_should_not_run)

    assert sink.calls == []
