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


# ---------------------------------------------------------------------------
# /correct, /scar — Phase 2 chunk 3 capture handlers
# ---------------------------------------------------------------------------

from karasu.classifier import ClassificationRule, RuleClassifier
from karasu.interface.commands import (
    capture_correct,
    capture_scar,
    derive_trigger,
    find_agent_response,
    latest_agent_response,
    parse_correction,
    validate_correction,
)


def _classifier_for_py() -> RuleClassifier:
    return RuleClassifier(
        [ClassificationRule(match="*.py", type="code_change", priority="normal")]
    )


def _seed_agent_response(bus: JsonlEventBus, path: str = "sample.py") -> Event:
    file_change = bus.append(
        Event(type="file_change", source="watcher", data={"path": path, "change_type": "modified"})
    )
    return bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"correlates": file_change.id, "path": path},
            dispatch={"agent": "claude_code", "status": "completed"},
            response={"content": "ok", "requires_human": False},
        )
    )


def test_parse_correction_single_pair() -> None:
    assert parse_correction("priority=high") == {"priority": "high"}


def test_parse_correction_multiple_pairs() -> None:
    assert parse_correction("priority=high path=*.md") == {
        "priority": "high",
        "path": "*.md",
    }


def test_parse_correction_rejects_empty() -> None:
    with pytest.raises(ValueError, match="at least one"):
        parse_correction("")


def test_parse_correction_rejects_missing_equals() -> None:
    with pytest.raises(ValueError, match="expected field=value"):
        parse_correction("priority")


def test_parse_correction_rejects_empty_field_or_value() -> None:
    with pytest.raises(ValueError, match="empty field or value"):
        parse_correction("=high")
    with pytest.raises(ValueError, match="empty field or value"):
        parse_correction("priority=")


def test_parse_correction_rejects_duplicate_field() -> None:
    with pytest.raises(ValueError, match="more than once"):
        parse_correction("priority=high priority=low")


def test_validate_correction_accepts_allowed_fields() -> None:
    validate_correction({"classification": "x", "priority": "y", "path": "z"})


def test_validate_correction_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="fields not allowed"):
        validate_correction({"agent": "claude_code"})


def test_find_agent_response_returns_match(bus: JsonlEventBus) -> None:
    target = _seed_agent_response(bus)
    found = find_agent_response(bus, target.id[:8])
    assert found is not None
    assert found.id == target.id


def test_find_agent_response_returns_none_when_absent(bus: JsonlEventBus) -> None:
    _seed_agent_response(bus)
    assert find_agent_response(bus, "ffffffff") is None


def test_find_agent_response_rejects_empty_prefix(bus: JsonlEventBus) -> None:
    with pytest.raises(ValueError, match="empty"):
        find_agent_response(bus, "")


def test_find_agent_response_rejects_ambiguous_prefix(bus: JsonlEventBus) -> None:
    # Two agent_response events in a row — the empty-string prefix
    # would match every event id, but parse rejects empty before
    # this. Force ambiguity by injecting two events with the same
    # id prefix character.
    bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"path": "a.py"},
            id="aaaa-1111",
        )
    )
    bus.append(
        Event(
            type="agent_response",
            source="adapter",
            data={"path": "b.py"},
            id="aaaa-2222",
        )
    )
    with pytest.raises(ValueError, match="ambiguous"):
        find_agent_response(bus, "aaaa")


def test_latest_agent_response_returns_most_recent(bus: JsonlEventBus) -> None:
    _seed_agent_response(bus, path="first.py")
    second = _seed_agent_response(bus, path="second.py")
    found = latest_agent_response(bus)
    assert found is not None
    assert found.id == second.id


def test_latest_agent_response_returns_none_when_empty(bus: JsonlEventBus) -> None:
    bus.append(Event(type="file_change", source="watcher", data={"path": "x.py"}))
    assert latest_agent_response(bus) is None


def test_derive_trigger_uses_classifier(bus: JsonlEventBus) -> None:
    target = _seed_agent_response(bus, path="sample.py")
    classifier = _classifier_for_py()
    trigger = derive_trigger(classifier, target)
    assert trigger == {"classification": "code_change", "path": "sample.py"}


def test_derive_trigger_falls_back_to_unknown(bus: JsonlEventBus) -> None:
    target = _seed_agent_response(bus, path="other.txt")
    trigger = derive_trigger(_classifier_for_py(), target)
    assert trigger == {"classification": "unknown", "path": "other.txt"}


def test_derive_trigger_rejects_missing_path(bus: JsonlEventBus) -> None:
    target = bus.append(
        Event(type="agent_response", source="adapter", data={})
    )
    with pytest.raises(ValueError, match="no path"):
        derive_trigger(_classifier_for_py(), target)


def test_capture_correct_records_scar(tmp_path: Path, bus: JsonlEventBus) -> None:
    target = _seed_agent_response(bus, path="sample.py")
    scars = ScarEngine(tmp_path / "scars")
    classifier = _classifier_for_py()

    reply = capture_correct(bus, scars, classifier, f"{target.id[:8]} priority=high")

    assert reply.startswith("recorded scar ")
    assert "priority" in reply
    rules = list(scars.all())
    assert len(rules) == 1
    assert rules[0].correction == {"priority": "high"}
    assert rules[0].trigger == {"classification": "code_change", "path": "sample.py"}
    assert rules[0].source_event == target.id


def test_capture_correct_rejects_short_args(tmp_path: Path, bus: JsonlEventBus) -> None:
    scars = ScarEngine(tmp_path / "scars")
    reply = capture_correct(bus, scars, _classifier_for_py(), "abc")
    assert reply.startswith("usage:")
    assert list(scars.all()) == []


def test_capture_correct_rejects_unknown_field(tmp_path: Path, bus: JsonlEventBus) -> None:
    target = _seed_agent_response(bus)
    scars = ScarEngine(tmp_path / "scars")
    reply = capture_correct(
        bus, scars, _classifier_for_py(), f"{target.id[:8]} agent=claude_code"
    )
    assert "fields not allowed" in reply
    assert list(scars.all()) == []


def test_capture_correct_reports_missing_target(tmp_path: Path, bus: JsonlEventBus) -> None:
    scars = ScarEngine(tmp_path / "scars")
    reply = capture_correct(
        bus, scars, _classifier_for_py(), "ffffffff priority=high"
    )
    assert "no agent_response found" in reply
    assert list(scars.all()) == []


def test_capture_scar_uses_latest(tmp_path: Path, bus: JsonlEventBus) -> None:
    _seed_agent_response(bus, path="old.py")
    latest = _seed_agent_response(bus, path="new.py")
    scars = ScarEngine(tmp_path / "scars")

    reply = capture_scar(bus, scars, _classifier_for_py(), "priority=high")

    assert reply.startswith("recorded scar ")
    rules = list(scars.all())
    assert len(rules) == 1
    assert rules[0].source_event == latest.id
    assert rules[0].trigger["path"] == "new.py"


def test_capture_scar_when_bus_has_no_response(tmp_path: Path, bus: JsonlEventBus) -> None:
    scars = ScarEngine(tmp_path / "scars")
    reply = capture_scar(bus, scars, _classifier_for_py(), "priority=high")
    assert "nothing to correct" in reply
    assert list(scars.all()) == []


def test_capture_scar_rejects_empty_args(tmp_path: Path, bus: JsonlEventBus) -> None:
    _seed_agent_response(bus)
    scars = ScarEngine(tmp_path / "scars")
    reply = capture_scar(bus, scars, _classifier_for_py(), "")
    assert "at least one" in reply
    assert list(scars.all()) == []
