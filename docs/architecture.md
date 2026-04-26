# Architecture

Karasu is organized as a chain of small, independent components connected
through an append-only event bus. Each component has one job and can be
replaced or extended without touching the rest.

## Component layout

```
┌──────────┐   ┌────────────┐   ┌────────┐   ┌──────────┐   ┌────────────┐
│ watcher  │──▶│ classifier │──▶│ router │──▶│ adapters │──▶│ reporter   │
└──────────┘   └────────────┘   └────────┘   └──────────┘   └────────────┘
      │              │              │             │               │
      └──────────────┴──────────────┴─────────────┴───────────────┘
                                    ▼
                       ┌──────────────────────┐
                       │  event bus (JSONL)   │
                       └──────────────────────┘
                                    ▲
                       ┌──────────────────────┐
                       │ scar engine + trust  │
                       └──────────────────────┘
                                    ▲
                       ┌──────────────────────┐
                       │ interface (Telegram) │
                       └──────────────────────┘
```

## Modules

- **`watcher/`** — wraps `watchdog` and emits `file_change` events for
  every relevant filesystem change. Ignore patterns are read from config.
- **`classifier/`** — assigns a `classification` and `priority` to each
  event using rule patterns from config. The scar engine can override
  the rule output.
- **`router/`** — looks at the classification and the per-agent `handles`
  list, picks an adapter, and dispatches.
- **`adapters/`** — thin wrappers around external agents. `base.py`
  defines the abstract interface; `claude_code.py` and `codex.py` are
  the two Phase 1 implementations.
- **`reporter/`** — receives `agent_response` events, filters them
  through the trust gradient (high-trust responses can be auto-applied,
  low-trust ones require human confirmation), and forwards what the
  human needs to see.
- **`trust/`** — keeps the per-agent trust level (0–3) and answers
  "does this response need a human?".
- **`scars/`** — correction memory. Records human overrides and
  replays them as routing rules. See [scar-engine.md](scar-engine.md).
- **`eventbus/`** — append-only JSONL log of every event. Every
  module reads from and writes to it; nothing else holds shared state.
- **`interface/`** — how the human talks to Karasu. Telegram bot in
  Phase 1, Progressive Web App in Phase 3.

## Event flow

1. The watcher detects a change on disk and writes a `file_change`
   event to the bus.
2. The classifier reads the event, attaches a classification and
   priority, and re-emits it.
3. The router picks an adapter based on classification, trust, and
   any matching scar, and dispatches.
4. The adapter calls the external agent and writes an `agent_response`
   event back to the bus.
5. The reporter applies the trust filter and forwards to the
   interface; if a human decision is required, it waits for one and
   writes a `human_decision` event back to the bus.
6. If the human's decision overrides the routing, the scar engine
   offers to save it as a rule.

The event log is the single source of truth: every component is a
pure transformer over the stream.
