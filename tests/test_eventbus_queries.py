"""Tests for ``karasu.eventbus.queries``.

Phase 3 audit follow-up (NICE-TO-HAVE #1, audit-noted on PR #60).
The dispatcher already persists the effective priority on
``agent_response.data["priority"]``; this module exposes the
canonical accessor so tooling does not duplicate the
"None-vs-default" decision at every call site.
"""

from karasu.eventbus import Event, effective_priority


def test_effective_priority_returns_value_from_agent_response() -> None:
    event = Event(
        type="agent_response",
        source="adapter",
        data={"correlates": "abc", "path": "a.py", "priority": "high"},
    )
    assert effective_priority(event) == "high"


def test_effective_priority_returns_none_when_field_absent() -> None:
    """Pre-PR #60 ``agent_response`` events have no priority field.

    The helper must surface that gap as ``None`` rather than
    substituting ``"normal"`` — a silent default would mask the
    incomplete audit trail. See PR #60 commit message.
    """
    event = Event(
        type="agent_response",
        source="adapter",
        data={"correlates": "abc", "path": "a.py"},
    )
    assert effective_priority(event) is None


def test_effective_priority_returns_none_when_explicit_none() -> None:
    """A literal ``None`` on the field is indistinguishable from absent."""
    event = Event(
        type="agent_response",
        source="adapter",
        data={"correlates": "abc", "path": "a.py", "priority": None},
    )
    assert effective_priority(event) is None


def test_effective_priority_reads_file_change_resubmit() -> None:
    """Controller resubmits inherit priority on the new ``file_change``.

    Chunk 3b copies ``original.data`` into the resubmitted
    file_change, so the effective priority is observable on those
    events too — not only on ``agent_response``.
    """
    event = Event(
        type="file_change",
        source="controller",
        data={
            "path": "a.py",
            "classification": "code_change",
            "priority": "high",
            "controller_resubmit": True,
            "resubmit_origin": "abc",
        },
    )
    assert effective_priority(event) == "high"


def test_effective_priority_coerces_non_string_values_to_str() -> None:
    """Stay defensive: bus events come from JSON, but a future
    source could write an integer or enum-like value. The helper
    returns ``str`` to give callers a single comparable type."""
    event = Event(
        type="agent_response",
        source="adapter",
        data={"correlates": "abc", "path": "a.py", "priority": 1},
    )
    assert effective_priority(event) == "1"
