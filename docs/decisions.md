# Architectural decisions

These are the load-bearing choices behind Karasu's design. Each
decision is paired with a rationale so that future contributors
can revisit it with the same context we had.

## Invariants — non-negotiable framing

```text
I-001  Karasu = message broker + memory writer. Karasu ≠ decision engine.
I-002  The bus is the source of truth. No other shared state.
I-003  Pipeline is single-event synchronous. No parallelism.
I-004  Surface ≠ orchestrator. Telegram never calls the dispatcher.
I-005  Scar = stored correction only. Scar ≠ execution. Scar ≠ control flow.
I-006  Frozen contracts: AgentResponse, F3 (no-route suppression),
       F7 (dispatch_on filter), F8 (per-agent timeout_s).
```

If a change touches any of I-001..I-006, escalate to the
maintainer; do not absorb the change into a feature PR.

## Choice table

| ID    | Decision               | Choice                                           | Rationale                                                              |
|-------|------------------------|--------------------------------------------------|------------------------------------------------------------------------|
| D-001 | Event bus              | JSONL flat file                                  | Simple, no dependencies, crash-safe, version-controllable              |
| D-002 | Agent communication    | CLI/HTTP adapters (Phase 1), A2A (Phase 2)       | Start simple, standardize later                                        |
| D-003 | Human-in-the-loop      | Trust gradient per agent (0→3)                   | More nuanced than binary approve/reject                                |
| D-004 | State persistence      | JSONL                                            | No database dependency                                                 |
| D-005 | Watcher                | watchdog (Python)                                | Mature, cross-platform, event-driven                                   |
| D-006 | Correction memory      | Scar engine (Lucy mechanism)                     | Corrections become routing rules                                       |
| D-007 | Mobile interface       | Telegram bot (MVP) → PWA (target)                | Telegram for immediate use, PWA for branded experience                 |
| D-008 | Phase 2 surface scope  | Read + Write (scar capture), NO execution        | Surface mutates ScarEngine, not the pipeline; loop stays out           |
| D-009 | Loop coordinator       | LoopController (single-worker, bounded queue)    | Chunk-3a refactor; chunks 3b/3c add reaction + multi-source plug-in    |
| D-010 | Trigger source plug-in | Protocol (start/stop) for long-running producers | One-shot producers (git hooks) call submit() directly; no protocol     |
