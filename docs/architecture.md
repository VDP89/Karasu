# Architecture

Karasu is organized as a chain of small, independent components connected
through an append-only event bus. Each component has one job and can be
replaced or extended without touching the rest.

## Karasu is a broker, not a decision engine

This framing is a load-bearing invariant. State it explicitly so
future contributors don't drift it:

```text
Karasu = message broker + memory writer.
Karasu ≠ decision engine.
```

Concretely:

- The **bus** is the source of truth. Every component reads from
  and writes to it; no other shared state exists.
- The **pipeline** is single-event synchronous. It classifies,
  consults scars, dispatches, reports — and stops.
- The **surface** (Telegram) is read + write over the bus. It
  never calls the dispatcher, never executes decisions.
- The **controller** coordinates dispatch on a single worker. It
  observes the bus to react to chat-recorded scars (chunk 3b),
  but the trigger is always a discrete human action, never the
  *existence* of a scar.
- **Scars** are stored corrections, not control flow primitives.
  See `docs/scar-engine.md` "Golden rule".

If a future change tempts you to make Karasu "decide" something
(skip an agent because a scar exists, retry on its own, mutate
in-flight events), check that framing first.

## Component layout

```
┌──────────┐                ┌────────────┐                ┌──────────┐
│ watcher  │──▶ controller ─▶│ classifier │──▶ router ──▶│ adapters │──▶ reporter
└──────────┘                └────────────┘                └──────────┘
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

The watcher hands each `file_change` to the **LoopController** instead
of running the pipeline inline. The controller owns one bounded
queue + one worker thread; it dispatches the pipeline call from that
worker. Phase 3 chunk 3a introduced this seam without changing
behaviour; chunks 3b (react to `human_decision` events) and 3c
(plug-in trigger sources beyond the watcher) build on top.

## Modules

- **`watcher/`** — wraps `watchdog` and emits `file_change` events for
  every relevant filesystem change. Ignore patterns are read from config.
  Implements `controller.sources.TriggerSource`; registered with the
  `LoopController` for downstream dispatch.
- **`controller/`** — `LoopController` owns the single worker thread
  that runs the pipeline. Bounded queue, daemon worker, crash
  containment. Reads `human_decision` events off the bus and resubmits
  the originating `file_change` so chat-recorded scars fire (chunk 3b).
  Manages a list of trigger sources via `add_source` (chunk 3c).
  - **`controller/sources/`** — `TriggerSource` Protocol plus the
    one-shot `git_hook` source. Long-running sources (watcher, future
    webhook receiver, A2A peer) implement the Protocol; one-shot
    producers (the `karasu hook` CLI) call `controller.submit`
    directly.
  See [phase-3-loop-controller.md](phase-3-loop-controller.md).
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
