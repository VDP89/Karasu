# Next Session Entry Point

## Goal

**Phase 3 chunk 3b — react to `human_decision` events on the bus.**

Chunk 3a (LoopController wrapper) is shipped and merged on `main`.
The architectural seam exists; behaviour is identical to pre-3a.
Chunk 3b makes the controller actually *react*: when a Telegram
`/correct` or `/scar` lands a `human_decision` event on the bus,
the controller resolves the originating `file_change` and
re-submits it. The existing `Pipeline._apply_scar_override` picks
up the chat-recorded scar on the resubmit.

## Scope

```text
What ships in 3b:
- LoopController gains a JsonlTailReader subscription to the bus.
- A new method on_bus_event(event) inspects each event:
    * agent_response → no-op (already dispatched)
    * file_change    → no-op (the trigger source already submitted it)
    * human_decision → parse the text field; if it matches /correct
                       <prefix> or /scar, look up the originating
                       agent_response, find its correlated
                       file_change, and re-submit that file_change.

What does NOT ship in 3b:
- Multi-source trigger plug-in (3c).
- Retries beyond the resubmit cap.
- Telemetry events (controller_action) — defer until reaction
  has dogfood evidence.
- Any change to AgentResponse, F3, F7, F8.
```

## Surface contract — must respect

```text
- Pipeline still does NOT consume human_decision events. The
  CONTROLLER consumes them; the pipeline only sees the resubmitted
  file_change.
- The controller never mutates ScarEngine. /correct + /scar already
  recorded the Scar (Phase 2 chunk 3); the controller only reacts
  to that record by triggering a fresh dispatch.
- Single-worker invariant: the resubmit goes through the same
  bounded queue + worker. No parallelism.
- Reaction cap: at most 3 resubmits per (originating event_id,
  scar_id) tuple. Beyond the cap, log a warning and skip. Phase 1
  had no retry; introducing one needs a stop rule.
```

## Pre-reads

```text
1. docs/phase-3-loop-controller.md     — chunk 3b design (open question 1: cap)
2. docs/phase-2-surface.md             — surface contract (frozen)
3. docs/memory/current-state.md        — phase + capabilities
4. docs/memory/session-log.md          — chunk 3a summary
5. src/karasu/controller/loop.py       — extension target
6. src/karasu/interface/commands.py    — find_agent_response,
                                          parse_correction (reuse)
7. src/karasu/eventbus/jsonl_bus.py    — JsonlTailReader
```

## Open questions to resolve while implementing

```text
1. Where does the bus subscription live? Lean: a new private
   thread on LoopController that calls JsonlTailReader.read_new()
   in a poll loop and dispatches to on_bus_event. Same shape as
   TelegramInterface.run_application's job queue, but threaded.

2. How is the resubmit cap tracked? Lean: an in-memory dict on
   LoopController keyed by (originating_id, scar_id). Resets on
   process restart — we are not persisting controller state in
   3b. Phase 3+ may extend.

3. Should the resubmit re-emit the file_change to the bus, or
   pass a fresh in-memory Event? Lean: re-emit. Audit trail
   shows the controller's reaction explicitly; no special
   "resubmit" event type, just a normal file_change with
   data.controller_resubmit=True so analyze can tell them apart.

4. What about /scar (no event_id)? Lean: target the latest
   agent_response on the bus, same as Phase 2 chunk 3 capture
   logic. Reuse latest_agent_response from commands.py.
```

## Do NOT do yet

```text
- Do not start chunk 3c (multi-source trigger plug-in).
- Do not parallelize the controller worker.
- Do not abstract the adapter behind a plugin layer.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
- Do not persist controller state between runs.
```

## Exit condition

```text
A new feat/* branch, ≤400 LOC, with:
- LoopController.on_bus_event implemented and tested.
- Bus subscription wired in cmd_watch.
- Resubmit cap enforced; tests cover the cap and the happy path
  (chat-recorded scar fires on the very next resubmit).
- Memory files synced; this file pointed at chunk 3c.
```

## Audit gate after chunk 3c

Per the Phase 2 cadence: ChatGPT reviews chunks 3a + 3b + 3c
together once 3c is pushed. The maintainer hands the stack.
**No new phase opens until the audit returns.**

## Anchor for the previous sessions

- Phase 1C closed 2026-04-29 (PR #29).
- Phase 2 closed 2026-04-30 (PRs #30 #31 #32 #33 merged after audit
  + condition fix).
- Phase 3 design merged 2026-04-30 (PR #34).
- `feat/loop-controller-wrapper` (this session) — chunk 3a code,
  11 new controller tests, 162/162 green locally.
