# Next Session Entry Point

## Goal

**Phase 2 — chunk 2: pick between read-only slash commands and inbound scar-capture.**

Phase 2 chunk 1 (Telegram outbound sink) shipped: `karasu chat`
forwards every `agent_response` to a configured Telegram chat via
`TelegramInterface.drain(reader, reporter)` + `send(report)`. The
surface contract (sink, not orchestrator) is frozen in
`docs/phase-2-surface.md`.

The next chunk has to choose one direction — both are valid, but
shipping them together would push the PR over 400 LOC and over the
review-loop's "small chunks" rule.

## The two options

### Option A — read-only slash commands

```text
Scope: /status, /agents, /scars
Where: TelegramInterface gets a python-telegram-bot Application
       with three command handlers, each a pure function over current
       Karasu state.
Effect on bus: none — these are read-only.
PR size estimate: ~250 LOC including mocked tests.
Risk: low. No new contracts. No pipeline coupling.
Value: operator can poll system state without leaving Telegram.
```

### Option B — inbound scar-capture

```text
Scope: /correct <event_id> <field>=<value> and /scar <field>=<value>
Where: TelegramInterface routes the message text to ScarEngine via
       a new `record_scar_correction(event_id, ...)` method on top of
       the existing `record_decision(user_id, text)`.
Effect on bus: writes scar_consultation events; pipeline still does
       NOT consume them in Phase 2 (per surface contract).
PR size estimate: ~400 LOC including ScarEngine glue and tests.
Risk: medium. Couples surface to ScarEngine. Crosses Phase 1D
      (scar-capture) territory.
Value: closes the Lucy-Syndrome correction loop one step earlier.
```

## Recommendation

**Option A first.** Lower risk, ships under 250 LOC, validates the
inbound polling path with mocked tests before adding the
ScarEngine coupling. Option B follows in chunk 3 once the inbound
plumbing has dogfood evidence.

## Pre-reads

```text
1. docs/phase-2-surface.md            — surface contract (do not violate)
2. docs/memory/current-state.md       — phase + capabilities
3. docs/memory/session-log.md         — chunk 1 summary
4. src/karasu/interface/telegram_bot.py — extension target
5. src/karasu/scars/engine.py         — only if Option B
```

## Do NOT do yet

```text
- Do not parallelize or batch adapter calls.
- Do not abstract the adapter behind a plugin layer.
- Do not mutate scars from chat (Option B may approach this; respect
  the F3 / F7 contracts and keep the pipeline single-event).
- Do not touch AgentResponse, F3 dispatcher semantics, F7 dispatch_on,
  F8 timeout_s. All four are frozen.
- Do not introduce a LoopController.
```

## Exit condition

```text
A new feat/* branch, ≤400 LOC, with:
- The chosen option implemented and tested with mocked python-telegram-bot.
- docs/local-dogfood.md updated with the new commands.
- Memory files synced (current-state, session-log, decision-log,
  this file pointed at chunk 3).
```

## Anchor for the previous session

Phase 2 chunk 1 closed 2026-04-29.

- `docs/phase-2-surface.md` (PR #30) — design only.
- `feat/telegram-outbound-sink` (this session) — `TelegramInterface.drain` + `send`, `karasu chat` rewritten, 106/106 tests green locally.

Codex review pending; ChatGPT acts as reviewer for this repo per
`CLAUDE.md` and `docs/review-loop.md`. The maintainer passes the PR
to the reviewer manually when an audit is needed.
