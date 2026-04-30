# Phase 2 — Human Surface (design)

Design document for the Phase 2 surface. The original draft was
design-only ("no code in this PR"); after the implementation
chunks shipped (PRs #31, #32, #33) the audit asked us to align the
contract with reality. The current text reflects the **shipped**
contract, with `## Revisions` at the end logging the update.

## Goal

Give the operator a way to read what Karasu is doing — and react —
without staring at `karasu tail`. The pipeline is closed
(`file_change → classify → dispatch → claude -p → agent_response`,
issue #25). What's missing is the layer that turns bus events into
something the human can consume on a phone and reply to.

This document fixes the surface contract before any Telegram /
controller code is written.

## Surface choice

```text
Decision:
- Phase 2 primary surface = Telegram. The surface delivers
  three capabilities (one per chunk):
    chunk 1 — outbound sink (agent_response forwarded to chat).
    chunk 2 — read-only slash commands (/status, /agents, /scars).
    chunk 3 — inbound scar capture (/correct, /scar) writing to
              ScarEngine. Pipeline still does NOT consume
              human_decision in Phase 2; the scar firing path is
              the existing Pipeline._apply_scar_override.
- Terminal (`karasu tail --follow`) stays as the dogfood / dev surface.
- Web UI / PWA = DEFERRED until the operator actually asks for it.

Reason:
- Telegram is already scaffolded in `src/karasu/interface/telegram_bot.py`
  (deferred since Phase 1A). The skeleton has `format(report)`,
  `is_allowed(user_id)`, `record_decision(user_id, text)` already
  lined up with the bus.
- Telegram covers the off-keyboard case the terminal cannot: operator
  away from the laptop, single push notification per `agent_response`.
- A web UI requires a server, auth, and a frontend — all of that is
  out of scope until we know whether Telegram is enough.

Discarded:
- Both surfaces in parallel: doubles the contract burden in the first
  PR with no operator demand for the web side yet.
- Telegram-only (no terminal): would deprecate `karasu tail`, which
  is the only debug tool we have during dogfood. Keep it.
- Web-first: zero scaffolding, multi-week build, no incremental
  validation path.
```

## Reporter ↔ surface contract

```text
Decision:
- The surface is a SINK on the read side: it subscribes via the
  existing `JsonlTailReader` (PR #9), runs
  `HumanReporter.report(event)` on each event, and forwards the
  resulting `Report` to the channel adapter.
- The `Report` dataclass (`text: str`, `needs_decision: bool`) is
  enough for Phase 2. Do NOT add fields preemptively.
- Channel adapter exposes one method: `send(report) -> None`.
  TelegramInterface already has `format(report)`; the send step
  wraps it.
- Read-only commands (/status, /agents, /scars) render Karasu state
  back to the chat. They do NOT mutate state.
- Write commands (/correct, /scar) mutate ScarEngine via
  `ScarEngine.record(scar)`. They do NOT emit file_change or
  agent_response. The pipeline still consumes scars only via the
  existing `Pipeline._apply_scar_override` path during a
  file_change dispatch — chat-originated scars are picked up the
  next time the relevant path triggers a dispatch, not via a new
  reaction loop.
- Every inbound message — read or write, accepted or rejected —
  writes a `human_decision` event on the bus for the audit trail.
  The pipeline does NOT consume `human_decision`.

Reason:
- Reuses existing primitives (`JsonlTailReader`, `HumanReporter`,
  `Report`, `TelegramInterface`, `ScarEngine`) without inventing
  new ones.
- Keeps F3 / F7 contracts intact: the surface only reads what the
  dispatcher chose to emit. It does NOT decide what to dispatch.
- Scar mutation from chat is intentional in Phase 2 (closes the
  Lucy-Syndrome correction loop one step earlier than the original
  draft proposed) but the firing path is unchanged: the pipeline
  reads scars, the surface writes scars, and the two never call
  each other directly.
```

### Pipeline boundary

```text
bus (JSONL) ──► JsonlTailReader ──► HumanReporter.report(event)
                                          │
                                          ▼
                                     Report or None
                                          │
                                          ▼
                              channel.send(report)        # outbound sink
                                          │
                                          ▼
                                     mobile chat

human reply ──► TelegramInterface
                  │
                  ├─► record_decision(user_id, text)         # always
                  │      │
                  │      ▼
                  │   bus.append(Event(type="human_decision"))
                  │      │
                  │      ▼
                  │   [pipeline does NOT consume this]
                  │
                  ├─► /status, /agents, /scars              # read-only
                  │      │
                  │      ▼
                  │   reply via channel.send(text)
                  │
                  └─► /correct, /scar                       # writes
                         │
                         ▼
                     ScarEngine.record(Scar)
                         │
                         ▼
                     [picked up by Pipeline._apply_scar_override
                      on the NEXT file_change dispatch — no new
                      reaction loop, no controller in Phase 2]
```

### Trigger derivation note (chunk 3)

When `/correct` or `/scar` builds a `Scar`, the trigger is derived
by re-classifying the path on `agent_response.data.path` with the
**currently configured** `RuleClassifier`. Classification is not
persisted on the on-disk file_change (the watcher writes
file_change before the classifier runs). In Phase 2 the classifier
instance is built once at startup and shared with `karasu watch`,
so the trigger matches what the dispatcher saw — but if classifier
config changes between runs, the recorded trigger reflects the
**current** config, not the historical one. Phase 3+ may persist
classification on the bus to make this explicit.

## Open questions — answered

```text
1. What does the human DO when an agent_response lands?
   → Read it via push (Telegram outbound, chunk 1) or poll
     (/status / /scars from the chat, chunk 2). They can also
     install a Scar with /correct or /scar (chunk 3) — the
     correction fires on the NEXT relevant file_change dispatch.

2. Where does the human read it?
   → Telegram primary. `karasu tail --follow` stays for dev.

3. How does the human override?
   → /correct <event_id-prefix> field=value
     /scar field=value
     Both record a Scar via ScarEngine. The pipeline does NOT
     react in Phase 2; the scar fires the next time a matching
     file_change runs through Pipeline._apply_scar_override.
     Strict whitelist: empty allowed_users rejects every write.

4. Reporter ↔ surface contract — Report enough?
   → Yes. `Report(text, needs_decision)` carries enough for the
     first cut. Add fields only when a concrete surface needs them.

5. LoopController in Phase 2?
   → No. Phase 2 stays synchronous. Debounce + adapter timeout are
     already in place; nothing to coordinate yet.
```

## First PR plan

```text
Branch:  feat/telegram-outbound-sink
Scope:   ≤400 LOC including tests.

Files touched:
- src/karasu/interface/telegram_bot.py   (extend; ~80 LOC)
- src/karasu/__main__.py                 (`karasu chat` subcommand; ~40 LOC)
- src/karasu/interface/__init__.py       (export TelegramInterface; ~5 LOC)
- tests/test_telegram_bot.py             (new; ~120 LOC, all mocked)
- docs/local-dogfood.md                  (append Telegram section; ~30 LOC)
- docs/memory/{current-state,session-log,decision-log}.md  (sync; ~40 LOC)

Behaviour shipped:
- `karasu chat` reads KARASU_TELEGRAM_TOKEN + KARASU_TELEGRAM_CHAT_ID
  from env, fails fast if either is missing.
- TelegramInterface gains `drain(reader)` that pulls events from a
  JsonlTailReader, runs HumanReporter, and sends each Report.
- Outbound only in chunk 1. Slash commands ship in chunk 2 and
  scar capture in chunk 3 (PRs #32, #33).
- Whitelist behaviour: refuse to start if KARASU_TELEGRAM_CHAT_ID
  is empty (single-operator default).

Tests:
- Mocked python-telegram-bot Application.
- HumanReporter integration: `[INFO]` vs `[DECISION]` prefix per
  trust gradient.
- `record_decision` writes a `human_decision` event with the
  user id and the raw text; pipeline does NOT react.
- Whitelist rejects non-allowed user.

Out of this PR:
- Slash commands (chunk 2 — PR #32).
- Scar capture from `/correct` / `/scar` (chunk 3 — PR #33).
- Web UI / PWA.
- Inbound override LOOP (a controller that REACTS to
  human_decision events on the bus). Scar capture is allowed in
  Phase 2; reaction-loop coordination is not.
```

## Do NOT do in Phase 2

```text
- LoopController / scheduler.
- Pipeline reaction to human_decision events. Chat-originated
  scars fire only via the existing Pipeline._apply_scar_override
  on the next matching file_change.
- Parallelize or batch adapter calls.
- Abstract the adapter behind a plugin layer.
- Touch AgentResponse, F3 dispatcher semantics, F7 dispatch_on,
  or F8 timeout_s. All four are frozen by issue #25 / PR #29.
- Add `event_log` rotation, schema versioning, or correlation_id
  enrichment. None blocks Phase 2.
```

## Exit condition for Phase 2 (first chunk)

```text
- TelegramInterface.drain() shipped, tested, mocked.
- `karasu chat` runs against a real bot token in a sandbox and
  delivers one Telegram message per agent_response.
- Memory files synced (current-state.md → Phase 2 in-progress
  with the chunk closed; session-log.md entry; next-session.md
  pointed at the next chunk — slash commands or scar capture).
```

## Revisions

### 2026-04-29 — audit alignment for chunks 2 + 3

The original draft of this document declared Phase 2 as "outbound
only, read-only" and listed scar capture as out of scope. Chunks 2
(slash commands) and 3 (scar capture) shipped a wider scope
nonetheless. The audit (ChatGPT, returned 2026-04-29) flagged the
contradiction and required the contract to be aligned with the
shipped behaviour before PR #33 merges.

This revision:

- Acknowledges the three chunks (outbound sink, read-only commands,
  scar capture) as Phase 2 deliverables.
- Restates the boundary so the reviewer's accept doesn't drift:
  `human_decision` events are recorded but the **pipeline does NOT
  consume them**; chat-originated scars fire only via the existing
  `Pipeline._apply_scar_override` path on the next file_change.
- Documents the trigger-derivation classifier-currency caveat
  (chunk 3 re-classifies on capture using the configured rules at
  capture time, not the historical classification).
- Updates the "Out of scope" and "Do NOT do" sections accordingly:
  scar capture is allowed; a reaction LOOP that consumes
  `human_decision` is still off the table for Phase 2.

What did NOT change:

- The frozen contracts: `AgentResponse`, F3, F7, F8.
- The "surface = sink on the read side" framing.
- The deferral of LoopController, web UI, and Phase 2+ archive
  (issue #5).
