"""Abstract adapter contract.

Every concrete adapter implements :meth:`AgentAdapter.dispatch`. The
return value is an :class:`AgentResponse` that the router writes back
to the bus as an ``agent_response`` event.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable


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

    def can_handle(self, classification: str) -> bool:
        return not self.handles or classification in self.handles

    @abstractmethod
    def dispatch(self, request: AgentRequest) -> AgentResponse:
        """Send ``request`` to the underlying agent and return its reply."""
