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


# ---------------------------------------------------------------------------
# Phase 3+ chunk 4c — AgentRequest.metadata round-trip
# ---------------------------------------------------------------------------


def test_dispatch_copies_event_data_into_request_metadata(
    bus: JsonlEventBus,
) -> None:
    """Adapters need source-specific fields (github_body, github_author,
    etc.) without widening AgentRequest's named schema for every new
    source. The dispatcher copies event.data into request.metadata so
    the adapter (or its prompt builder) can read them.
    """
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])
    event = Event(
        type="file_change",
        source="github_webhook",
        data={
            "path": "a.py",
            "classification": "code_change",
            "priority": "high",
            "github_pr": 42,
            "github_author": "reviewer1",
            "github_body": "please rename foo to bar",
        },
    )
    dispatcher.dispatch(event)
    assert len(stub.calls) == 1
    request = stub.calls[0]
    assert request.metadata["github_pr"] == 42
    assert request.metadata["github_author"] == "reviewer1"
    assert request.metadata["github_body"] == "please rename foo to bar"
    # Named fields stay populated for back-compat.
    assert request.path == "a.py"
    assert request.classification == "code_change"
    assert request.priority == "high"


def test_dispatch_metadata_is_a_copy_not_a_reference(
    bus: JsonlEventBus,
) -> None:
    """The adapter must not be able to mutate event.data through the
    metadata dict. This guards F3 (the bus is the canonical record):
    if an adapter rewrites metadata mid-dispatch, the file_change on
    disk must stay untouched."""
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])
    event = Event(
        type="file_change",
        source="github_webhook",
        data={
            "path": "a.py",
            "classification": "code_change",
            "priority": "normal",
            "github_body": "hello",
        },
    )
    dispatcher.dispatch(event)
    request = stub.calls[0]
    request.metadata["github_body"] = "REWRITTEN"
    assert event.data["github_body"] == "hello"


def test_dispatch_metadata_is_empty_for_watcher_events(
    bus: JsonlEventBus,
) -> None:
    """No github fields on a normal watcher event — the metadata dict
    just mirrors event.data (path/classification/priority)."""
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])
    dispatcher.dispatch(_classified("a.py", "code_change"))
    request = stub.calls[0]
    assert "github_body" not in request.metadata
    assert request.metadata["path"] == "a.py"
    assert request.metadata["classification"] == "code_change"


# ---------------------------------------------------------------------------
# Phase 3 audit follow-up — persist effective priority on agent_response.data
# ---------------------------------------------------------------------------


def test_dispatch_persists_priority_on_agent_response(
    bus: JsonlEventBus,
) -> None:
    """An operator inspecting events.jsonl post-hoc must be able to
    audit "what priority did this dispatch run at?" without
    cross-referencing the originating file_change. The dispatcher
    persists the effective priority on agent_response.data."""
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])

    event = Event(
        type="file_change",
        source="watcher",
        data={
            "path": "a.py",
            "classification": "code_change",
            "priority": "high",
        },
    )
    dispatcher.dispatch(event)
    response_event = list(bus.read())[-1]

    assert response_event.type == "agent_response"
    assert response_event.data["priority"] == "high"


def test_dispatch_priority_defaults_to_normal_when_absent(
    bus: JsonlEventBus,
) -> None:
    """When the file_change carries no priority field, the dispatch
    runs at the documented default ("normal") and that default is
    persisted on agent_response. The audit trail must reflect the
    REAL priority used, not "missing"."""
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])

    event = Event(
        type="file_change",
        source="watcher",
        data={"path": "a.py", "classification": "code_change"},
    )
    dispatcher.dispatch(event)
    response_event = list(bus.read())[-1]

    assert response_event.data["priority"] == "normal"


def test_dispatch_priority_reflects_scar_override(
    bus: JsonlEventBus,
) -> None:
    """When a scar overrides priority before dispatch (e.g.
    ``/scar priority=high``), the agent_response must show the
    POST-override priority — that's the value the adapter actually
    saw and that future analyze passes need to attribute the
    dispatch to."""
    stub = _StubAdapter()
    dispatcher = Dispatcher(bus=bus, adapters=[stub])

    # Simulate an event whose priority was rewritten by a scar
    # override before reaching the dispatcher (the pipeline mutates
    # data.priority in-place when applying a scar).
    rewritten = Event(
        type="file_change",
        source="watcher",
        data={
            "path": "a.py",
            "classification": "code_change",
            "priority": "high",  # was "normal", overridden by scar
        },
    )
    dispatcher.dispatch(rewritten)
    response_event = list(bus.read())[-1]

    assert response_event.data["priority"] == "high"
    # Adapter saw the same effective priority — agent_response and
    # request agree, no audit-trail divergence.
    assert stub.calls[0].priority == "high"
