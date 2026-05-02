"""A2A AgentCard dataclasses + builder.

Snapshot of the A2A spec used by Karasu, recorded here so future
spec drift is a localised diff and not a scattered refactor.

Field naming follows the spec: dataclass attributes are
snake_case for Python idiom; ``to_dict`` emits the camelCase keys
the A2A spec wants on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from karasu import __version__

# Karasu's baseline skills. Static list — chunk 4b's audit said
# "describe what the agent CAN do, not the current process state",
# so all four are published unconditionally. Adapter-conditional
# filtering (per F-A2A-3) is deferred until a downstream peer
# actually needs it.
_KARASU_SKILLS: tuple[tuple[str, str, str], ...] = (
    (
        "watch-filesystem",
        "Filesystem watcher",
        "Observes a filesystem root and emits file_change events on the bus.",
    ),
    (
        "route-events",
        "Event router",
        "Classifies file_change events and dispatches to a registered adapter.",
    ),
    (
        "receive-github-webhooks",
        "GitHub webhook receiver",
        "Accepts HMAC-verified GitHub webhooks at POST /webhook and "
        "translates supported events into file_change events.",
    ),
    (
        "record-corrections",
        "Scar capture",
        "Persists human corrections (/correct, /scar) as ScarEngine "
        "rules that re-fire on subsequent matching dispatches.",
    ),
)


@dataclass(frozen=True)
class AgentCapabilities:
    """A2A AgentCapabilities. Off by default; chunk 4b is discovery-only."""

    streaming: bool = False
    push_notifications: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "streaming": self.streaming,
            "pushNotifications": self.push_notifications,
        }


@dataclass(frozen=True)
class Skill:
    """One published agent skill."""

    id: str
    name: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


@dataclass(frozen=True)
class AgentCard:
    """A2A AgentCard. Static snapshot; built once at startup.

    F-A2A-1: NEVER include runtime config (paths, secrets, registered
    scars, version of external CLIs). Only published-skill
    metadata + agent identity.
    """

    name: str
    description: str
    version: str
    url: str | None
    capabilities: AgentCapabilities
    skills: tuple[Skill, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": self.capabilities.to_dict(),
            "skills": [s.to_dict() for s in self.skills],
        }


def build_karasu_card(
    *,
    base_url: str | None = None,
) -> AgentCard:
    """Build the canonical Karasu AgentCard.

    ``base_url`` is the public address the peer should use to
    reach this Karasu instance (usually the same host:port the
    webhook receiver binds to, externalised for production).
    Pass ``None`` if the operator does not want to advertise an
    address — the peer can still read the skill list.

    Static snapshot per F-A2A-3: skills describe baseline
    capability. Adapter-conditional filtering is deferred until a
    downstream peer needs it.
    """
    return AgentCard(
        name="karasu",
        description=(
            "Adaptive coordination layer between AI agents. "
            "Single-worker dispatch with scar-based correction memory."
        ),
        version=__version__,
        url=base_url,
        capabilities=AgentCapabilities(),
        skills=tuple(
            Skill(id=skill_id, name=name, description=desc)
            for skill_id, name, desc in _KARASU_SKILLS
        ),
    )
