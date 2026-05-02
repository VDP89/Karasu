# Karasu UI-1 — Runtime Plan

## Purpose

Define the first implementable UI chunk for Karasu.

UI-1 is not the full product UI. It is the smallest local web runtime that proves the UI track can read Karasu state and make it understandable to the operator without touching the pipeline.

## Core Principle

> UI = surface, not orchestrator.

UI-1 reads and renders. It does not execute, dispatch, mutate, apply scars, or coordinate agents.

## Goal

Ship a local web dashboard:

```text
karasu ui
  -> starts local server
  -> opens / serves http://127.0.0.1:8787
  -> displays event timeline
  -> displays crow state
```

## Source of Truth

```text
.karasu/events.jsonl
```

UI-1 must not introduce a database.

## Architecture

```text
.karasu/events.jsonl
        |
        | read-only
        v
Karasu UI Server
127.0.0.1:8787
        |
        | HTTP JSON + static HTML
        v
Browser UI
```

## Proposed Files

```text
src/karasu/ui/__init__.py
src/karasu/ui/server.py
src/karasu/ui/static/index.html
src/karasu/ui/static/app.js
src/karasu/ui/static/style.css
tests/test_ui_server.py
```

Optional CLI wiring:

```text
src/karasu/__main__.py
```

## CLI

```bash
karasu ui --host 127.0.0.1 --port 8787
```

Defaults:

```text
host = 127.0.0.1
port = 8787
```

UI-1 is local-only by default.

## API Contract

### GET /api/events

Returns recent events from `.karasu/events.jsonl`.

Response shape:

```json
{
  "events": [
    {
      "id": "...",
      "timestamp": "...",
      "type": "agent_response",
      "source": "dispatcher",
      "path": "src/example.py",
      "agent": "claude_code",
      "requires_human": true
    }
  ]
}
```

Notes:

- This is a UI projection, not a replacement for the Event schema.
- Missing fields should become `null`, not crash the UI.
- Default limit: latest 100 events.

### GET /api/health

Returns minimal UI health.

```json
{
  "status": "ok",
  "event_log": ".karasu/events.jsonl",
  "events": 42,
  "last_event": "...",
  "crow_state": "idle"
}
```

## Crow State v1

UI-1 includes a simple derived crow state.

```text
idle       -> no recent events or no pending decision
processing -> latest event is file_change
waiting    -> latest agent_response has requires_human=true
error      -> latest agent_response has success=false
```

Priority order:

```text
error > waiting > processing > idle
```

No fake animation rule:

> The UI may animate only when derived from real bus state.

## UI Screen

UI-1 ships one page only.

### Main page

Sections:

1. Header
   - Karasu UI
   - crow state
   - event count

2. Live Map placeholder
   - Usuario
   - Karasu
   - Claude
   - Codex
   - GitHub
   - no complex animation yet

3. Timeline
   - timestamp
   - type
   - path
   - agent
   - requires_human marker

4. Event Detail placeholder
   - appears when selecting an event
   - shows raw projected fields

## Visual Direction

UI-1 should establish the retro direction without overbuilding it.

Style:

```text
retro operating-system panel
simple borders
monospace/pixel-like feel
crow state indicator as text or emoji placeholder
```

Do not add pixel art assets yet.

## Constraints

UI-1 must NOT:

- call Pipeline
- call Dispatcher
- call adapters
- consume `human_decision`
- apply scars
- mutate AgentResponse
- mutate `.karasu/events.jsonl`
- add authentication
- add WebSocket complexity
- add React/Vite/Electron
- add voice input
- add token monitor

## Tests

Required tests:

1. `/api/events` returns empty list when event log does not exist.
2. `/api/events` returns projected events from JSONL.
3. `/api/health` returns event count and last event.
4. Crow state derives `waiting` from `requires_human=true`.
5. Crow state derives `error` from `success=false`.
6. Static `index.html` is served.

## First PR Budget

Target:

```text
<= 400 LOC including tests
```

If exceeded, split static UI polish out of UI-1.

## Out of Scope

- Voice input / transcription
- Token monitor
- Push notifications
- Real crow animation
- Live graph animation
- PWA installability
- User settings
- Human actions beyond selecting an event

## Exit Condition

UI-1 is complete when:

```text
karasu ui
```

starts a local server and the browser can show:

- event count
- crow state
- timeline of recent events
- basic event detail

with no changes to pipeline, dispatcher, scars, AgentResponse, F3, F7, F8, surface=sink, single-worker, or TriggerSource contracts.
