"""Read-side helpers over :class:`Event` records.

The bus persists every dispatch with the EFFECTIVE priority on
``agent_response.data["priority"]`` (PR #60). Tooling that audits
the bus post-hoc — ``analyze``, future analytics, the UI projection
— needs a single canonical accessor for that field so the meaning
of "what priority did this run at?" stays consistent across call
sites.

This module owns those accessors. It does NOT mutate the bus.
"""

from __future__ import annotations

from karasu.eventbus.jsonl_bus import Event


def effective_priority(event: Event) -> str | None:
    """Return the effective priority recorded on ``event``, or ``None``.

    The "effective" priority is the value that actually reached the
    adapter for that dispatch — i.e. post any scar / classifier
    override. It is persisted on:

    - ``agent_response.data["priority"]`` since PR #60.
    - ``file_change.data["priority"]`` on controller resubmits
      (chunk 3b copies ``original.data`` into the new event).

    Returns ``None`` when the field is absent. Callers MUST treat
    ``None`` as "no audit trail recorded" rather than substituting
    a default — pre-PR #60 ``agent_response`` events have no
    priority recorded, and a silent default would mask that gap.
    See PR #60 commit message for the full rationale.
    """
    raw = event.data.get("priority")
    if raw is None:
        return None
    return str(raw)
