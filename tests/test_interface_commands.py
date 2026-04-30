"""Tests for the slash-command formatters (Phase 2, chunk 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from karasu import __version__
from karasu.adapters import AgentAdapter, AgentRequest, AgentResponse
from karasu.eventbus import Event, JsonlEventBus
from karasu.interface.commands import format_agents, format_scars, format_status
from karasu.scars import Scar, ScarEngine


class _FakeAdapter(AgentAdapter):
    """Concrete adapter for formatter tests; dispatch is never called."""

    def dispatch(self, request: AgentRequest) -> AgentResponse:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


def test_format_status_empty_bus(bus: JsonlEventBus) -> None:
    text = format_status(bus)
    assert f"karasu {__version__}" in text
    assert str(bus.path) in text
    assert "events: 0" in text
    # No event types and no "last event" line when the bus is empty.
    assert "last event" not in text


def test_format_status_counts_by_type(bus: JsonlEventBus) -> None:
    bus.append(Event(type="file_change", source="watcher"))
    bus.append(Event(type="file_change", source="watcher"))
    bus.append(Event(type="agent_response", source="dispatcher"))

    text = format_status(bus)

    assert "events: 3" in text
    assert "  agent_response: 1" in text
    assert "  file_change: 2" in text
    assert "last event:" in text


# ---------------------------------------------------------------------------
# /agents
# ---------------------------------------------------------------------------


def test_format_agents_empty() -> None:
    assert format_agents([]) == "no agents registered"


def test_format_agents_lists_name_and_handles() -> None:
    a = _FakeAdapter(name="claude_code", handles=("code_change", "bug_fix"))
    b = _FakeAdapter(name="codex", handles=("code_review",))
    text = format_agents([a, b])

    assert text.startswith("agents:")
    assert "claude_code: handles=[code_change, bug_fix]" in text
    assert "codex: handles=[code_review]" in text


def test_format_agents_marks_catch_all_when_handles_empty() -> None:
    a = _FakeAdapter(name="anything", handles=())
    text = format_agents([a])

    assert "anything: handles=[(catch-all)]" in text


# ---------------------------------------------------------------------------
# /scars
# ---------------------------------------------------------------------------


def test_format_scars_empty(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    assert format_scars(engine) == "no active scars"


def test_format_scars_renders_trigger_and_correction(tmp_path: Path) -> None:
    engine = ScarEngine(tmp_path / "scars")
    engine.record(
        Scar(
            trigger={"classification": "code_change", "path": "*.py"},
            correction={"classification": "doc_change", "priority": "low"},
        )
    )
    text = format_scars(engine)

    assert text.startswith("scars:")
    assert "classification=code_change" in text
    assert "path=*.py" in text
    assert "classification=doc_change" in text
    assert "priority=low" in text
