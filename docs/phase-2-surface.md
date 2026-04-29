# Phase 2 — Human Surface (design)

Design-only. No code in this PR. Exit condition for `next-session.md`
Phase 2 entry: surface picked, reporter↔surface contract on paper,
first PR plan sized.

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
- Phase 2 primary surface = Telegram (outbound only, read-only).
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
- The surface is a SINK over the JSONL bus. Not an orchestrator.
- It subscribes via the existing `JsonlTailReader` (PR #9), pulls
  events as they land, runs `HumanReporter.report(event)` on each,
  and forwards the resulting `Report` to the channel adapter.
- The `Report` dataclass (`text: str`, `needs_decision: bool`) is
  enough for Phase 2. Do NOT add fields preemptively.
- Channel adapter exposes one method: `send(report) -> None`.
  TelegramInterface already has `format(report)`; the send step
  wraps it.
- Inbound (human → Karasu) writes `human_decision` events on the
  bus and stops there. The pipeline does NOT consume them in
  Phase 2 (no scar capture, no override loop).

Reason:
- Reuses existing primitives (`JsonlTailReader`, `HumanReporter`,
  `Report`, `TelegramInterface`) without inventing new ones.
- Keeps F3 / F7 contracts intact: the surface only reads what the
  dispatcher chose to emit. It does NOT decide what to dispatch.
- `human_decision` events on the bus are recorded for the future
  scar-capture work (Phase 1D / 2+, per issue #5) but do not feed
  back into the loop yet.
```

### Pipeline boundary

```text
bus (JSONL) ──► JsonlTailReader ──► HumanReporter.report(event)
                                          │
                                          ▼
                                     Report or None
                                          │
                                          ▼
                              channel.send(report)        # Telegram in Phase 2
                                          │
                                          ▼
                                     mobile chat

human reply ──► TelegramInterface.record_decision(user_id, text)
                                          │
                                          ▼
                          bus.append(Event(type="human_decision"))
                                          │
                                          ▼
                          [STOPS HERE in Phase 2 — recorded only]
```

## Open questions — answered

```text
1. What does the human DO when an agent_response lands?
   → Read it. Phase 2 is read-only. Approval / reject / follow-up
     loops require scar capture, which is Phase 1D / 2+.

2. Where does the human read it?
   → Telegram primary. `karasu tail --follow` stays for dev.

3. How does the human override?
   → They don't, in Phase 2. Replies are recorded on the bus as
     `human_decision` events but the pipeline ignores them.
     Override = Phase 1D scar-capture work.

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
- Outbound only. No `/correct`, no `/scars`, no slash commands.
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
- Slash commands (status, agents, scars).
- Scar capture from `/scar` messages.
- Web UI / PWA.
- Inbound override loop.
```

## Do NOT do in Phase 2

```text
- LoopController / scheduler.
- Mutate scars from chat or Telegram.
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
