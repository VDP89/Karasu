"""Abstract adapter contract.

Every concrete adapter implements :meth:`AgentAdapter.dispatch`. The
return value is an :class:`AgentResponse` that the router writes back
to the bus as an ``agent_response`` event.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable

# NICE-TO-HAVE #3 (audit-promoted to chunk-4c hard pre-req).
# trust_level >= AUTONOMOUS_TRUST_LEVEL means the agent can mutate
# operator state without per-call approval. The Phase 3 dogfood
# (issue #39) confirmed this live: Claude at trust_level=2
# autonomously edited sample.py to fix a divide-by-zero. Documented
# explicitly in docs/local-dogfood.md and docs/decisions.md D-003.
AUTONOMOUS_TRUST_LEVEL = 2

_log = logging.getLogger(__name__)


@dataclass
class AgentRequest:
    """A unit of work handed to an adapter."""

    classification: str
    path: str
    priority: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """An adapter's reply."""

    content: str
    success: bool = True
    requires_human: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """Base class for agent adapters."""

    name: str = ""

    def __init__(
        self,
        name: str | None = None,
        handles: Iterable[str] = (),
        trust_level: int = 0,
    ) -> None:
        if name is not None:
            self.name = name
        self.handles = tuple(handles)
        self.trust_level = trust_level
        # NICE-TO-HAVE #3: structured warning when an adapter is
        # constructed at trust_level >= 2. Operators wiring this up
        # the first time get a visible, greppable signal that the
        # agent will mutate state without per-call approval.
        # Doc-only mitigation (D-003 + local-dogfood.md) is not
        # enough for the chunk-4c combination (auto-handoff +
        # trust>=2 = remote code edits triggered by PR comments).
        if trust_level >= AUTONOMOUS_TRUST_LEVEL:
            _log.warning(
                "adapter %r constructed with trust_level=%d (>= %d): "
                "agent will mutate operator state without per-call "
                "approval. See docs/local-dogfood.md "
                '"Trust gradient — what trust_level actually does in '
                'production".',
                self.name or type(self).__name__,
                trust_level,
                AUTONOMOUS_TRUST_LEVEL,
            )

    def can_handle(self, classification: str) -> bool:
        return not self.handles or classification in self.handles

    @abstractmethod
    def dispatch(self, request: AgentRequest) -> AgentResponse:
        """Send ``request`` to the underlying agent and return its reply."""
