from karasu.adapters.base import AgentAdapter, AgentRequest, AgentResponse
from karasu.eventbus import Event, JsonlEventBus
from karasu.router import Dispatcher


class _StubAdapter(AgentAdapter):
    name = "stub"

    def __init__(self, handles=("code_change",), trust_level=2) -> None:
        super().__init__(handles=handles, trust_level=trust_level)
        self.calls: list[AgentRequest] = []

    def dispatch(self, request: AgentRequest) -> AgentResponse:
        self.calls.append(request)
        return AgentResponse(content="done", success=True, requires_human=False)


def _classified(path: str, classification: str) -> Event:
    return Event(
        type="file_change",
        source="watcher",
        data={"path": path, "classification": classification, "priority": "normal"},
    )


def test_dispatch_routes_to_first_capable_adapter(bus: JsonlEventBus) -> None:
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])
    dispatcher.dispatch(_classified("a.py", "code_change"))
    assert len(stub.calls) == 1
    assert stub.calls[0].path == "a.py"
    response_event = list(bus.read())[-1]
    assert response_event.type == "agent_response"
    assert response_event.dispatch == {
        "agent": "stub",
        "status": "completed",
        "trust_level": 2,
    }


def test_dispatch_emits_nothing_when_no_adapter_matches(bus: JsonlEventBus) -> None:
    """Per F3 decision (issue #17): the dispatcher suppresses ``agent_response``
    when no adapter handles the event. The bus is a record of real agent
    work, not pipeline mechanics. The originating file_change is still on
    the bus; absence of a correlated agent_response means "seen but
    unhandled".
    """
    dispatcher = Dispatcher(bus=bus, adapters=[_StubAdapter(handles=("doc_change",))])
    original = _classified("a.py", "code_change")
    bus.append(original)

    result = dispatcher.dispatch(original)

    assert result is None
    events = list(bus.read())
    assert len(events) == 1  # only the file_change appended manually above
    assert events[0].id == original.id
    assert events[0].type == "file_change"


def test_dispatch_returns_none_does_not_corrupt_bus_when_no_adapter(
    bus: JsonlEventBus,
) -> None:
    """Repeated no-adapter dispatches must not accumulate noise on the bus."""
    dispatcher = Dispatcher(bus=bus, adapters=[_StubAdapter(handles=("doc_change",))])
    for _ in range(5):
        dispatcher.dispatch(_classified("a.py", "code_change"))

    assert list(bus.read()) == []
