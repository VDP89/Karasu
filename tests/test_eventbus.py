from pathlib import Path

from karasu.eventbus import Event, JsonlEventBus, JsonlTailReader


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


# ----------------------------------------------------------------------
# JsonlTailReader.
# ----------------------------------------------------------------------


def test_tail_reader_starts_at_eof_does_not_replay(bus: JsonlEventBus) -> None:
    bus.append(Event(type="A", source="s"))
    reader = JsonlTailReader(bus.path)
    bus.append(Event(type="B", source="s"))
    new = reader.read_new()
    assert [e.type for e in new] == ["B"]


def test_tail_reader_replays_when_start_at_end_false(bus: JsonlEventBus) -> None:
    bus.append(Event(type="A", source="s"))
    bus.append(Event(type="B", source="s"))
    reader = JsonlTailReader(bus.path, start_at_end=False)
    new = reader.read_new()
    assert [e.type for e in new] == ["A", "B"]


def test_tail_reader_handles_missing_path(tmp_path: Path) -> None:
    reader = JsonlTailReader(tmp_path / "missing.jsonl")
    assert reader.read_new() == []


def test_tail_reader_skips_partial_trailing_line(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    full = (
        '{"type":"A","source":"s","data":{},"dispatch":{},'
        '"response":{},"id":"1","timestamp":"t"}\n'
    )
    partial = '{"type":"par'
    p.write_text(full + partial, encoding="utf-8")

    reader = JsonlTailReader(p, start_at_end=False)
    first_pass = reader.read_new()
    assert [e.type for e in first_pass] == ["A"]

    rest = (
        'tial","source":"s","data":{},"dispatch":{},'
        '"response":{},"id":"2","timestamp":"t"}\n'
    )
    with p.open("a", encoding="utf-8") as fh:
        fh.write(rest)

    second_pass = reader.read_new()
    assert [e.type for e in second_pass] == ["partial"]


def test_tail_reader_skips_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text(
        "not json\n"
        '{"type":"ok","source":"s","data":{},"dispatch":{},"response":{},"id":"1","timestamp":"t"}\n',
        encoding="utf-8",
    )
    reader = JsonlTailReader(p, start_at_end=False)
    new = reader.read_new()
    assert [e.type for e in new] == ["ok"]


def test_tail_reader_advances_offset_only_on_complete_lines(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text("partial-no-newline", encoding="utf-8")
    reader = JsonlTailReader(p, start_at_end=False)

    assert reader.read_new() == []
    assert reader.offset == 0

    with p.open("a", encoding="utf-8") as fh:
        fh.write("\n")

    new = reader.read_new()
    assert new == []
    assert reader.offset > 0


def test_tail_reader_no_event_loss_on_partial_consumption(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    bus = JsonlEventBus(p)
    bus.append(Event(type="A", source="s"))
    bus.append(Event(type="B", source="s"))

    reader = JsonlTailReader(p, start_at_end=False)
    events = reader.read_new()

    first = events[0]
    remaining = events[1:]

    assert first.type == "A"
    assert [e.type for e in remaining] == ["B"]


def test_tail_reader_handles_unicode_separator_in_payload(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    bus = JsonlEventBus(p)

    # U+2028 line separator inside JSON string
    payload = "hello\u2028world"
    bus.append(Event(type="A", source="s", data={"text": payload}))

    reader = JsonlTailReader(p, start_at_end=False)
    events = reader.read_new()

    assert len(events) == 1
    assert events[0].data["text"] == payload
