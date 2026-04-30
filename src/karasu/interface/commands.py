"""Pure formatters for Telegram slash commands.

Read-only views over Karasu state. No telegram dependency, no IO
beyond the bus / scar files; tests can call them directly.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from karasu import __version__
from karasu.adapters import AgentAdapter
from karasu.eventbus import JsonlEventBus
from karasu.scars import ScarEngine


def format_status(bus: JsonlEventBus) -> str:
    """Render the response for ``/status``.

    Mirrors the shape of ``karasu status`` so the operator sees the
    same information in either surface.
    """
    counts: Counter[str] = Counter()
    last_ts = ""
    for event in bus.read():
        counts[event.type] += 1
        last_ts = event.timestamp

    lines = [
        f"karasu {__version__}",
        f"event log: {bus.path}",
        f"events: {sum(counts.values())}",
    ]
    for event_type, count in sorted(counts.items()):
        lines.append(f"  {event_type}: {count}")
    if last_ts:
        lines.append(f"last event: {last_ts}")
    return "\n".join(lines)


def format_agents(adapters: Iterable[AgentAdapter]) -> str:
    """Render the response for ``/agents``."""
    items = list(adapters)
    if not items:
        return "no agents registered"
    lines = ["agents:"]
    for adapter in items:
        handles = ", ".join(adapter.handles) if adapter.handles else "(catch-all)"
        lines.append(f"  {adapter.name}: handles=[{handles}]")
    return "\n".join(lines)


def format_scars(scars: ScarEngine) -> str:
    """Render the response for ``/scars``."""
    rules = list(scars.all())
    if not rules:
        return "no active scars"
    lines = ["scars:"]
    for scar in rules:
        trigger = ", ".join(f"{k}={v}" for k, v in sorted(scar.trigger.items()))
        correction = ", ".join(
            f"{k}={v}" for k, v in sorted(scar.correction.items())
        )
        lines.append(f"  - {scar.id[:8]}: [{trigger}] -> [{correction}]")
    return "\n".join(lines)
