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
        path = event.data.get("path", "")
        adapter = self.select(classification)
        if adapter is None:
            # Per F3 decision (issue #17): suppress agent_response when no
            # adapter handles the event. The bus represents real agent work,
            # not pipeline mechanics. The originating file_change is still
            # on the bus; an operator reconstructs "seen but unhandled" from
            # the file_change presence + the absence of a correlated
            # agent_response.
            return None
        # Phase 3+ chunk 4c: copy event.data into AgentRequest.metadata
        # so adapters see source-specific fields (github_body,
        # github_author, github_pr_number, etc.) without having to
        # widen the AgentRequest schema for every new source. The
        # named fields (classification, path, priority) stay on the
        # request for back-compat; metadata is the new escape hatch.
        #
        # SHALLOW COPY BY DESIGN. event.data values today are JSON
        # scalars / collections; a top-level mutation by an adapter
        # cannot reach the bus event. If a future source carries
        # nested mutable state inside data, this needs revisiting
        # (likely with a deep copy or an immutable view).
        request = AgentRequest(
            classification=classification,
            path=path,
            priority=event.data.get("priority", "normal"),
            metadata=dict(event.data),
        )
        response = adapter.dispatch(request)
        # Phase 3 audit follow-up: persist the EFFECTIVE priority
        # (i.e. the value that actually reached the adapter, after
        # any scar / classifier override) on the agent_response so
        # `analyze` can audit dispatch priority post-hoc without
        # cross-referencing the originating file_change. This is an
        # additive schema bump on agent_response.data; old
        # consumers that ignore the field continue to work.
        return self.bus.append(
            Event(
                type="agent_response",
                source="adapter",
                data={
                    "correlates": event.id,
                    "path": request.path,
                    "priority": request.priority,
                },
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
