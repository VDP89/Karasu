"""Route classified events to the right adapter.

The dispatcher walks the registered adapters in registration order
and picks the first one whose ``can_handle`` returns true. The chosen
adapter's response is appended to the bus as an ``agent_response``
event correlated with the original event id.
"""

from __future__ import annotations

from typing import Iterable

from karasu.adapters.base import AgentAdapter, AgentRequest
from karasu.eventbus import Event, JsonlEventBus


class Dispatcher:
    """Route ``Event`` instances to adapters."""

    def __init__(
        self,
        bus: JsonlEventBus,
        adapters: Iterable[AgentAdapter] = (),
    ) -> None:
        self.bus = bus
        self.adapters: list[AgentAdapter] = list(adapters)

    def register(self, adapter: AgentAdapter) -> None:
        self.adapters.append(adapter)

    def select(self, classification: str) -> AgentAdapter | None:
        for adapter in self.adapters:
            if adapter.can_handle(classification):
                return adapter
        return None

    def dispatch(self, event: Event) -> Event | None:
        classification = event.data.get("classification", "")
        adapter = self.select(classification)
        if adapter is None:
            event.dispatch = {"agent": None, "status": "failed", "trust_level": 0}
            return self.bus.append(event)
        request = AgentRequest(
            classification=classification,
            path=event.data.get("path", ""),
            priority=event.data.get("priority", "normal"),
        )
        response = adapter.dispatch(request)
        return self.bus.append(
            Event(
                type="agent_response",
                source="adapter",
                data={"correlates": event.id, "path": request.path},
                dispatch={
                    "agent": adapter.name,
                    "status": "completed" if response.success else "failed",
                    "trust_level": adapter.trust_level,
                },
                response={
                    "content": response.content,
                    "requires_human": response.requires_human,
                },
            )
        )
