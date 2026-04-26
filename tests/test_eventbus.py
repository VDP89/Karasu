from karasu.eventbus import Event, JsonlEventBus


def test_append_and_read_roundtrip(bus: JsonlEventBus) -> None:
    bus.append(Event(type="file_change", source="watcher", data={"path": "a.py"}))
    bus.append(Event(type="agent_response", source="adapter", response={"content": "ok"}))
    events = list(bus.read())
    assert [e.type for e in events] == ["file_change", "agent_response"]
    assert events[0].data["path"] == "a.py"
    assert events[1].response["content"] == "ok"


def test_event_has_id_and_timestamp() -> None:
    event = Event(type="file_change", source="watcher")
    assert event.id
    assert event.timestamp
