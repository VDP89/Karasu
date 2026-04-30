"""Pure formatters and write handlers for Telegram slash commands.

Read-only views over Karasu state plus the inbound capture handlers
for ``/correct`` and ``/scar``. No telegram dependency, no IO beyond
the bus / scar files; tests call these directly.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from karasu import __version__
from karasu.adapters import AgentAdapter
from karasu.classifier import RuleClassifier
from karasu.eventbus import Event, JsonlEventBus
from karasu.scars import Scar, ScarEngine

# Phase 1 scar contract — the pipeline only honours these keys when a
# Scar fires. Surface enforces the same allowlist on the WRITE side so
# operators learn at capture time, not at the next dispatch.
# (See ``Pipeline.SUPPORTED_SCAR_KEYS``.)
ALLOWED_CORRECTION_FIELDS = frozenset({"classification", "priority", "path"})


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


# ---------------------------------------------------------------------------
# /correct, /scar — write handlers
# ---------------------------------------------------------------------------


def parse_correction(text: str) -> dict[str, str]:
    """Parse ``field=value field2=value2 ...`` into a mapping.

    Raises ``ValueError`` on malformed tokens so the caller can
    surface a clear reply. Empty input is rejected — a correction
    with no fields is meaningless.
    """
    pairs: dict[str, str] = {}
    tokens = text.strip().split()
    if not tokens:
        raise ValueError("expected at least one field=value pair")
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"expected field=value, got {token!r}")
        key, _, value = token.partition("=")
        if not key or not value:
            raise ValueError(f"empty field or value in {token!r}")
        if key in pairs:
            raise ValueError(f"field {key!r} specified more than once")
        pairs[key] = value
    return pairs


def validate_correction(correction: dict[str, str]) -> None:
    """Reject correction fields outside the Phase 1 allowlist."""
    bad = sorted(set(correction) - ALLOWED_CORRECTION_FIELDS)
    if bad:
        raise ValueError(
            f"fields not allowed: {bad}; allowed: {sorted(ALLOWED_CORRECTION_FIELDS)}"
        )


def find_agent_response(bus: JsonlEventBus, prefix: str) -> Event | None:
    """Find the unique ``agent_response`` whose id starts with ``prefix``.

    Returns ``None`` if no match. Raises ``ValueError`` on multiple
    matches so the operator must use a longer prefix (git-style).
    """
    if not prefix:
        raise ValueError("event id prefix is empty")
    matches = [
        event
        for event in bus.read()
        if event.type == "agent_response" and event.id.startswith(prefix)
    ]
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous prefix {prefix!r}: {len(matches)} matches; use more characters"
        )
    return matches[0] if matches else None


def latest_agent_response(bus: JsonlEventBus) -> Event | None:
    """Return the most recent ``agent_response`` on the bus, or ``None``."""
    last: Event | None = None
    for event in bus.read():
        if event.type == "agent_response":
            last = event
    return last


def derive_trigger(
    classifier: RuleClassifier,
    agent_response: Event,
) -> dict[str, str]:
    """Build a Scar trigger from an ``agent_response``.

    The path is on ``agent_response.data.path``. Classification is
    re-derived by running the configured classifier against that path
    — the file_change written to the bus by the watcher does not
    persist classification (the classifier mutates the in-memory copy
    only).
    """
    path = agent_response.data.get("path", "")
    if not path:
        raise ValueError("agent_response has no path; cannot derive trigger")
    probe = Event(type="file_change", source="surface", data={"path": path})
    classified = classifier.classify(probe)
    classification = classified.data.get("classification", "unknown")
    return {"classification": classification, "path": path}


def _record_scar(
    scars: ScarEngine,
    target: Event,
    correction: dict[str, str],
    classifier: RuleClassifier,
) -> str:
    trigger = derive_trigger(classifier, target)
    scar = scars.record(
        Scar(trigger=trigger, correction=correction, source_event=target.id)
    )
    return (
        f"recorded scar {scar.id[:8]}: "
        f"trigger={trigger} correction={correction}"
    )


def capture_correct(
    bus: JsonlEventBus,
    scars: ScarEngine,
    classifier: RuleClassifier,
    args: str,
) -> str:
    """Handle ``/correct <event_id> <field>=<value> ...``.

    Returns the human-readable reply text. All errors are caught
    and rendered as user-facing messages — the surface never raises
    out of a chat handler.
    """
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return "usage: /correct <event_id> <field>=<value> ..."
    prefix, rest = parts[0], parts[1]

    try:
        correction = parse_correction(rest)
        validate_correction(correction)
    except ValueError as exc:
        return f"error: {exc}"

    try:
        target = find_agent_response(bus, prefix)
    except ValueError as exc:
        return f"error: {exc}"
    if target is None:
        return f"no agent_response found with id prefix {prefix!r}"

    try:
        return _record_scar(scars, target, correction, classifier)
    except ValueError as exc:
        return f"error: {exc}"


def capture_scar(
    bus: JsonlEventBus,
    scars: ScarEngine,
    classifier: RuleClassifier,
    args: str,
) -> str:
    """Handle ``/scar <field>=<value> ...`` against the latest ``agent_response``."""
    try:
        correction = parse_correction(args)
        validate_correction(correction)
    except ValueError as exc:
        return f"error: {exc}"

    target = latest_agent_response(bus)
    if target is None:
        return "no agent_response on the bus yet; nothing to correct"

    try:
        return _record_scar(scars, target, correction, classifier)
    except ValueError as exc:
        return f"error: {exc}"
