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


def test_dispatch_marks_failed_when_no_adapter_matches(bus: JsonlEventBus) -> None:
    dispatcher = Dispatcher(bus=bus, adapters=[_StubAdapter(handles=("doc_change",))])
    dispatcher.dispatch(_classified("a.py", "code_change"))
    event = list(bus.read())[-1]
    assert event.dispatch["status"] == "failed"
    assert event.dispatch["agent"] is None
