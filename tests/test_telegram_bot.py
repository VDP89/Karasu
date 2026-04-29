"""Tests for the Telegram outbound sink (Phase 2, chunk 1)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader
from karasu.interface import TelegramInterface
from karasu.reporter import HumanReporter, Report
from karasu.trust import TrustGradient


def _interface(bus: JsonlEventBus, **overrides: Any) -> TelegramInterface:
    kwargs: dict[str, Any] = {
        "token": "fake-token",
        "bus": bus,
        "chat_id": 123456,
        "allowed_users": (),
    }
    kwargs.update(overrides)
    return TelegramInterface(**kwargs)


def _agent_response(agent: str, content: str, requires_human: bool = False) -> Event:
    return Event(
        type="agent_response",
        source="dispatcher",
        dispatch={"agent": agent},
        response={"content": content, "requires_human": requires_human},
    )


def test_drain_returns_report_for_agent_response(bus: JsonlEventBus) -> None:
    bus.append(_agent_response("claude_code", "ok"))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient({"claude_code": 2}))

    reports = interface.drain(reader, reporter)

    assert len(reports) == 1
    assert reports[0].text.startswith("[INFO]")
    assert "claude_code" in reports[0].text
    assert "ok" in reports[0].text


def test_drain_skips_non_agent_response_events(bus: JsonlEventBus) -> None:
    bus.append(Event(type="file_change", source="watcher", data={"path": "x.py"}))
    bus.append(Event(type="classification", source="classifier", data={"path": "x.py"}))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient())

    assert interface.drain(reader, reporter) == []


def test_drain_marks_decision_when_trust_low(bus: JsonlEventBus) -> None:
    bus.append(_agent_response("claude_code", "edit", requires_human=False))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    # NOTIFY_SYNC requires human notification.
    reporter = HumanReporter(TrustGradient({"claude_code": 1}))

    reports = interface.drain(reader, reporter)

    assert reports[0].text.startswith("[DECISION]")
    assert reports[0].needs_decision is True


def test_drain_marks_info_when_trust_high(bus: JsonlEventBus) -> None:
    bus.append(_agent_response("claude_code", "auto", requires_human=False))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient({"claude_code": 2}))

    reports = interface.drain(reader, reporter)

    assert reports[0].text.startswith("[INFO]")
    assert reports[0].needs_decision is False


def test_drain_returns_empty_when_no_new_events(bus: JsonlEventBus) -> None:
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient())

    assert interface.drain(reader, reporter) == []


def test_drain_only_consumes_new_events(bus: JsonlEventBus) -> None:
    bus.append(_agent_response("a", "first"))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient({"a": 2}))

    first = interface.drain(reader, reporter)
    second = interface.drain(reader, reporter)

    assert len(first) == 1
    assert second == []


def test_drain_picks_up_events_appended_between_calls(bus: JsonlEventBus) -> None:
    reader = JsonlTailReader(bus.path, start_at_end=False)
    interface = _interface(bus)
    reporter = HumanReporter(TrustGradient({"a": 2}))

    assert interface.drain(reader, reporter) == []
    bus.append(_agent_response("a", "later"))
    reports = interface.drain(reader, reporter)

    assert len(reports) == 1
    assert "later" in reports[0].text


def test_send_raises_when_chat_id_missing(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=None)
    with pytest.raises(RuntimeError, match="chat_id"):
        interface.send(Report(text="x", needs_decision=False))


def test_send_invokes_bot_send_message(
    bus: JsonlEventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface = _interface(bus)
    captured: dict[str, Any] = {}

    class FakeBot:
        def __init__(self, token: str) -> None:
            captured["token"] = token

        async def send_message(self, chat_id: int, text: str) -> None:
            captured["chat_id"] = chat_id
            captured["text"] = text

    fake_module = types.ModuleType("telegram")
    fake_module.Bot = FakeBot  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "telegram", fake_module)

    interface.send(Report(text="hello", needs_decision=False))

    assert captured == {"token": "fake-token", "chat_id": 123456, "text": "hello"}


def test_record_decision_writes_human_decision_event(bus: JsonlEventBus) -> None:
    interface = _interface(bus)
    event = interface.record_decision(user_id=42, text="/scar foo=bar")

    assert event.type == "human_decision"
    assert event.source == "interface"
    assert event.data == {"user": 42, "text": "/scar foo=bar"}

    stored = list(bus.read())
    assert len(stored) == 1
    assert stored[0].id == event.id


def test_is_allowed_with_empty_whitelist_allows_anyone(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=1)
    assert interface.is_allowed(999) is True


def test_is_allowed_with_whitelist_rejects_outsider(bus: JsonlEventBus) -> None:
    interface = TelegramInterface(token="t", bus=bus, chat_id=1, allowed_users=(42,))

    assert interface.is_allowed(42) is True
    assert interface.is_allowed(99) is False
