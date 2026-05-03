# Event schema

All Karasu state lives in an append-only JSONL log. Each line is one
event. Components communicate exclusively by reading and appending to
this log — there is no other shared state.

## Record shape

```json
{
  "id": "uuid",
  "timestamp": "ISO-8601",
  "type": "file_change | git_event | agent_response | human_decision",
  "source": "watcher | adapter | interface",
  "data": {
    "path": "relative/path",
    "change_type": "created | modified | deleted",
    "classification": "code_change | doc_change | scar_change | config_change",
    "priority": "low | normal | high | critical"
  },
  "dispatch": {
    "agent": "claude_code | codex | null",
    "status": "pending | dispatched | completed | failed",
    "trust_level": 0
  },
  "response": {
    "content": "...",
    "requires_human": true
  }
}
```

## Field notes

- **`id`** — UUID v4. Used to correlate later events (an
  `agent_response` references the `file_change` it answers).
- **`timestamp`** — UTC, ISO-8601 with millisecond precision.
- **`type`** — drives which downstream component reacts. The
  classifier reacts to `file_change`/`git_event`; the reporter
  reacts to `agent_response`; the scar engine reacts to
  `human_decision`.
- **`source`** — which component produced the event. Useful for
  debugging and for trust accounting.
- **`data`** — type-dependent payload. The fields shown above are
  the union; not every type uses every field.
- **`dispatch`** — populated by the router when it picks an agent.
  `status` advances `pending → dispatched → completed | failed`.
- **`response`** — populated by adapters and consumed by the
  reporter. `requires_human` is set by the trust gradient.

## Priority semantics

`data.priority` on an `agent_response` is the **effective**
priority — the value that actually reached the adapter for that
dispatch, i.e. post any scar or classifier override. The
pre-override value (when an override fired) lives only on the
originating `file_change`; reconstruct it by following
`data.correlates` back to the `file_change.id`. See PR #60.

Tooling that audits the bus post-hoc should read this field via
`karasu.eventbus.effective_priority(event)`. The helper returns
`None` for events without the field rather than substituting a
default, so a missing priority on a pre-PR #60 `agent_response`
stays visible as a gap in the audit trail instead of silently
becoming `"normal"`.

## Compaction

Phase 1 keeps the log forever; Phase 2 will rotate when the file
exceeds `event_bus.max_size_mb` (see `karasu.yaml.example`). Rotated
segments are kept beside the active log and remain replayable.
