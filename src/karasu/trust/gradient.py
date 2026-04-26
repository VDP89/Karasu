"""Trust gradient.

Each agent sits somewhere on a four-step ladder:

* ``0`` — every action requires explicit human confirmation.
* ``1`` — the agent acts, the human is notified and can intervene.
* ``2`` — the agent acts, the human is notified asynchronously.
* ``3`` — the agent acts silently and only reports on failure.

Trust is per-agent. Phase 2 will refine it to per-agent / per-category.
"""

from __future__ import annotations

from enum import IntEnum


class TrustLevel(IntEnum):
    CONFIRM = 0
    NOTIFY_SYNC = 1
    NOTIFY_ASYNC = 2
    SILENT = 3


class TrustGradient:
    """Track trust levels for a fleet of agents."""

    def __init__(self, levels: dict[str, int] | None = None) -> None:
        self._levels: dict[str, TrustLevel] = {
            agent: TrustLevel(level) for agent, level in (levels or {}).items()
        }

    def level(self, agent: str) -> TrustLevel:
        return self._levels.get(agent, TrustLevel.CONFIRM)

    def set(self, agent: str, level: int | TrustLevel) -> None:
        self._levels[agent] = TrustLevel(int(level))

    def requires_human(self, agent: str) -> bool:
        return self.level(agent) <= TrustLevel.NOTIFY_SYNC
