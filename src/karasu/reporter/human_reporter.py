"""Filter agent responses through trust and format them for the human."""

from __future__ import annotations

from dataclasses import dataclass

from karasu.eventbus import Event
from karasu.trust import TrustGradient


@dataclass
class Report:
    text: str
    needs_decision: bool


class HumanReporter:
    """Decide which agent responses surface to the human, and how."""

    def __init__(self, trust: TrustGradient) -> None:
        self.trust = trust

    def report(self, event: Event) -> Report | None:
        if event.type != "agent_response":
            return None
        agent = event.dispatch.get("agent") or "unknown"
        content = event.response.get("content", "")
        agent_requires_human = bool(event.response.get("requires_human", True))
        trust_requires_human = self.trust.requires_human(agent)
        needs_decision = agent_requires_human or trust_requires_human
        prefix = "[DECISION]" if needs_decision else "[INFO]"
        return Report(
            text=f"{prefix} {agent}: {content}".strip(),
            needs_decision=needs_decision,
        )
