# Phase 2 Gate Audit — Karasu

Date: 2026-04-29
Reviewer: ChatGPT
Purpose: binary readiness gate before starting Phase 2. This is not a new feature backlog and should not create an open-ended review loop.

## Verdict

**GO for Phase 2 design.**

Karasu does not need another core-hardening loop before Phase 2. Phase 1C closed the minimum real loop: `file_change → classify → dispatch → claude -p → agent_response`. The remaining issues are surface-contract decisions, not blockers for beginning Phase 2.

## Gate rule

Phase 2 may start if all of these are true:

| Gate | Status | Decision |
|---|---:|---|
| Core pipeline works end-to-end | YES | Proceed |
| Event bus is sufficient for Phase 2 read surface | YES | Do not redesign now |
| Adapter contract is sufficient | YES | Do not redesign now |
| Dispatch semantics are coherent | YES | Do not re-open F3/F7 |
| Trust gradient is usable for first human surface | YES | Keep simple |
| Scar mutation through UI/chat is safe to build now | NO | Explicitly defer |
| LoopController/scheduler is required before Phase 2 | NO | Do not build yet |
| Parallel/batched adapter execution is required before Phase 2 | NO | Do not build yet |
| Plugin layer is required before Phase 2 | NO | Do not build yet |

## What is accepted as stable for Phase 2

### 1. Event bus

Decision: **ACCEPT AS-IS for Phase 2.**

The JSONL event bus is good enough as the system record for the first human surface. It supports event ids, timestamps, type/source, data, dispatch, and response payloads. It is append-only and already supports tailing/analyze workflows.

Do not introduce a database, queue server, replay engine, or event-versioning layer before the Phase 2 surface contract is written.

Allowed in Phase 2:
- Read from `.karasu/events.jsonl`.
- Render `agent_response` events.
- Correlate responses back to source events using `data.correlates`.
- Add a narrow `human_decision` event only if the surface contract explicitly defines it.

Not allowed in Phase 2 entry PR:
- Replace JSONL.
- Add migrations.
- Add distributed broker semantics.
- Add full replay semantics.

### 2. Adapter contract

Decision: **ACCEPT AS-IS.**

`AgentRequest(classification, path, priority, metadata)` and `AgentResponse(content, success, requires_human, metadata)` are sufficient for the first Phase 2 surface. The surface can display content, success/failure, whether a decision is required, and adapter metadata when useful.

Do not redesign the adapter interface before building the first human-surface contract.

Allowed:
- Surface may display `response.content` and dispatch metadata.
- Surface may use `requires_human` plus trust level to decide whether the message is actionable.

Not allowed:
- Add streaming response protocol.
- Add multi-message adapter protocol.
- Add tool-call schema for adapters.
- Add plugin abstraction.

### 3. Dispatch semantics

Decision: **ACCEPT AS-IS.**

The current semantics are coherent:

- No adapter handles classification → no `agent_response`.
- `code_change` excludes `deleted` by default.
- Per-rule `dispatch_on` can override the classification default.
- Other classifications remain unfiltered unless a rule says otherwise.

Do not re-open F3 or F7 before Phase 2.

Allowed:
- Phase 2 may explain unhandled events by absence of correlated `agent_response`.
- Phase 2 may display only `agent_response` initially, without building an unhandled-events inbox.

Not allowed:
- Reintroduce no-op `agent_response` events.
- Add global no-dispatch-on-delete.
- Move dispatch filtering into the dispatcher.

### 4. Reporter contract

Decision: **ACCEPT FOR MVP, BUT FREEZE THE NEXT CONTRACT BEFORE CODING UI.**

`Report(text, needs_decision)` is enough for terminal-level reporting, but a Telegram/Web surface needs a written contract before implementation.

The next document must define exactly what the human sees and what actions are possible.

Required before coding Telegram/Web:
- Primary surface: Telegram, Web, or terminal-first.
- Message shape for an `agent_response`.
- Action set: read-only, approve/reject, follow-up, waive, save-as-scar.
- Whether Phase 2 writes `human_decision` events.

Not required before coding:
- Scar mutation.
- Trust management UI.
- PWA.
- GitHub webhook/A2A integration.

### 5. Trust gradient

Decision: **ACCEPT SIMPLE MODEL.**

The current trust gradient is enough for deciding whether a surfaced response needs human attention. Per-category trust can wait.

Allowed:
- Use current per-agent trust level.
- Treat trust level 0–1 as requiring human visibility/decision.

Not allowed in first Phase 2 PR:
- Per-category trust matrix.
- Trust promotion/demotion UI.
- Auto-apply behavior.

### 6. Scar engine

Decision: **READ-ONLY / DEFER MUTATION.**

The scar concept is central, but Phase 2 should not start by allowing Telegram/chat to mutate scars. The current Phase 1 scar contract only supports correction of `classification`, `priority`, and `path`; direct agent override is explicitly deferred.

Allowed:
- Surface can mention that a response may become a future correction.
- Surface can log a human decision if the contract is clear.

Not allowed:
- Save scars from Telegram/chat in the first Phase 2 PR.
- Add direct agent override scars yet.
- Add scar history UI yet.

## Must-do before Phase 2 code

Create one short document:

`docs/phase-2-surface.md`

It must answer only these questions:

1. What is the first human surface? **Pick one.**
2. What event types does it read in MVP?
3. What exact message does the human see for `agent_response`?
4. What actions can the human take in MVP?
5. Does it write `human_decision` events? If yes, define the minimal event shape.
6. What is explicitly deferred?
7. What is the first PR, capped at roughly 400 lines?

## Binary Phase 2 scope

### YES — start Phase 2 with this

- Write `docs/phase-2-surface.md`.
- Build a minimal read surface over existing `agent_response` events.
- Keep the core synchronous.
- Keep JSONL as source of truth.
- Keep adapter contract unchanged.
- Keep scars mutation deferred.

### NO — do not do this before the first Phase 2 surface works

- No LoopController.
- No scheduler.
- No parallel adapter dispatch.
- No batching.
- No plugin layer.
- No database.
- No event schema redesign.
- No scar mutation from chat.
- No direct agent override scars.
- No trust-management UI.
- No A2A/GitHub webhook work.

## First PR recommendation

Recommended first PR title:

`docs: define Phase 2 human surface contract`

Scope:

- Add `docs/phase-2-surface.md`.
- No source-code changes.
- No Telegram implementation.
- No controller.

Exit condition:

- A new session with Claude can read `current-state.md`, this audit, and `phase-2-surface.md`, then implement exactly one small Phase 2 PR without re-litigating Phase 1.

## Final decision

**Proceed to Phase 2 design now.**

Do not run another broad review of Phase 1 before Phase 2. Only fix a Phase 1 issue now if it is a concrete, reproducible failure in the already-validated loop. Otherwise, treat it as Phase 2 backlog or explicit defer.
