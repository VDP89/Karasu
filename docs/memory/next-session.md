# Next Session Entry Point

## Goal

**Phase 2 — chunk 3: inbound scar capture from Telegram.**

Chunks 1 (outbound sink) and 2 (read-only slash commands) shipped.
Chunk 3 closes the Phase 2 surface by letting the operator turn a
correction in chat into a durable rule via `ScarEngine`.

## Scope

```text
Commands shipped:
- /correct <event_id> <field>=<value>[ <field>=<value>...]
    Find the agent_response with the given id (prefix-match like
    git commits), derive the trigger from the originating
    file_change/classification, and record a Scar with the
    correction map.
- /scar <field>=<value>[ <field>=<value>...]
    Same as /correct but uses the latest agent_response on the bus
    as the trigger source. Convenience for "fix the thing I just
    saw".

Allowed correction fields (per PR #1 contract):
- classification
- priority
- path

Anything else is rejected with a clear "field not allowed" reply.
The ScarEngine itself does not enforce this — the surface does.
```

## Surface contract — must respect

```text
- Pipeline does NOT consume scars-from-chat events in Phase 2.
- The flow is one-way: chat -> ScarEngine.record(scar). Reading
  scars happens via /scars (chunk 2) and via the existing
  ScarEngine.find/apply path used by Pipeline._consult_scars.
- The bus stays the canonical record. Every scar capture writes
  TWO events: the human_decision (text raw) and a scar_consultation
  (the resulting Scar). Pipeline ignores both.
- No coupling new code paths to LoopController. Phase 2 stays
  synchronous.
```

## Pre-reads

```text
1. docs/phase-2-surface.md             — surface contract (do not violate)
2. docs/memory/current-state.md        — phase + capabilities
3. docs/memory/session-log.md          — chunk 1 + chunk 2 summaries
4. src/karasu/interface/telegram_bot.py — extension target
5. src/karasu/scars/engine.py          — Scar / ScarEngine API
6. docs/scar-engine.md                 — Lucy-Syndrome correction loop
```

## Open questions to resolve while implementing

```text
1. Should /correct fail-fast on unknown event_id, or fall back to
   "latest agent_response"? Lean: fail-fast — operator should know
   when their id is wrong.
2. Should /scar require an agent_response to exist on the bus, or
   accept "no work has run yet"? Lean: require — empty bus means
   nothing to correct.
3. Whitelist behaviour for write commands: should they ALWAYS
   require an explicit allowed_users entry, even when the empty
   whitelist still allows /status? Lean: yes — write commands
   need stricter trust than reads.
```

## Do NOT do yet

```text
- Do not parallelize or batch adapter calls.
- Do not abstract the adapter behind a plugin layer.
- Do not introduce a LoopController.
- Do not let the pipeline react to scars-from-chat in Phase 2.
- Do not touch AgentResponse, F3 dispatcher semantics, F7
  dispatch_on, F8 timeout_s. All four are frozen.
```

## Exit condition

```text
A new feat/* branch, ≤400 LOC, with:
- /correct + /scar implemented and tested with a fake ScarEngine.
- Allowlist of correction fields enforced at the surface.
- Stricter whitelist for write commands (empty whitelist refuses).
- docs/local-dogfood.md updated with the inbound section.
- Memory files synced; this file pointed at the post-chunk-3 audit.
```

## Audit gate after chunk 3

Per the operator policy: ChatGPT review is triggered manually after
all three chunks are pushed. The maintainer passes the PR set to
ChatGPT for the audit. **No new chunk starts before the audit
returns.** If the audit accepts, Phase 2 is complete and the next
session opens Phase 3 (PWA / web UI) — see roadmap.md.

## Anchor for the previous sessions

- Phase 1C closed 2026-04-29 (PR #29).
- `docs/phase-2-surface.md` (PR #30) — design only.
- `feat/telegram-outbound-sink` (PR #31) — chunk 1 code.
- `feat/telegram-slash-commands` (this session) — chunk 2 code,
  stacked on chunk 1, 118/118 tests green locally.
