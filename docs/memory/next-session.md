# Next Session Entry Point

## Goal

**Phase 2 — design the human surface (UI / Telegram / controller).**

Phase 1C closed the validation loop: file change → classify → dispatch → real Claude CLI → `agent_response` on the bus. The findings F1–F8 are all resolved (see `current-state.md`). The adapter contract (`AgentResponse(content, success, requires_human, metadata)`) does not need redesign.

The next layer is how a human reads the bus and acts on it. Phase 2 is design-first: write down the surface contract before building the Telegram bot, web UI, or LoopController.

## Pre-reads

```text
1. docs/memory/current-state.md         — phase + capabilities snapshot
2. docs/memory/session-log.md           — what changed last session
3. docs/memory/decision-log.md          — durable decisions (esp. F3 / F7 / F8)
4. docs/architecture.md                 — module map
5. docs/scar-engine.md, docs/review-loop.md — Phase 1 contracts the next surface must respect
6. issue #25 (closed)                   — Phase 1C dogfood + Codex review summary
```

## Open questions to answer in Phase 2 design

```text
1. What does the human *do* when an agent_response lands?
   - Read it inline?
   - Approve/reject it (trust-level driven)?
   - Ask a follow-up?
2. Where does the human read it?
   - Telegram (already scaffolded in src/karasu/interface/, deferred since Phase 1A)
   - Web UI
   - Terminal-only via `karasu tail --follow`
3. How does the human override?
   - Inline command in chat?
   - Slash commands?
   - Web form?
4. What is the contract between reporter and surface?
   - Is the Report dataclass enough, or does the surface need richer payload?
5. Loop control:
   - Does Phase 2 add a LoopController or does it stay synchronous?
   - If LoopController, how does it interact with debounce + adapter timeout?
```

## Do NOT do yet

```text
- Do not start coding Telegram before the surface contract is on paper.
- Do not parallelize or batch adapter calls (Phase 1 stays synchronous).
- Do not abstract the adapter behind a plugin layer.
- Do not mutate scars from chat / Telegram.
```

## Exit condition

```text
A short docs/phase-2-surface.md (or equivalent) with:
- The human's primary surface picked (Telegram / Web / both).
- The reporter ↔ surface contract.
- A first PR plan (one chunk, ~400 lines max).
```

## Anchor for the previous session

Phase 1C closed 2026-04-29. PRs #24 (adapter), #26 (F7 dispatch_on), #27 (F6 default ignores), #28 (F8 timeout) all merged. Issue #25 documents the dogfood and the Codex review. Bus volume during a single live edit: 3 events (1 file_change + 1 watch.log noise + 1 agent_response). End-to-end latency ~38.5 s (Claude `-p` with auto-discovery).

A non-blocking follow-up was filed by Codex on PR #24: support **list-form `command` in YAML** to avoid shell-like string parsing entirely. Filed for whenever string parsing actually bites; not blocking Phase 2.
