# Architectural decisions

These are the load-bearing choices behind Karasu's Phase 1 design.
Each decision is paired with a rationale so that future contributors
can revisit it with the same context we had.

| ID    | Decision               | Choice                                           | Rationale                                                              |
|-------|------------------------|--------------------------------------------------|------------------------------------------------------------------------|
| D-001 | Event bus              | JSONL flat file                                  | Simple, no dependencies, crash-safe, version-controllable              |
| D-002 | Agent communication    | CLI/HTTP adapters (Phase 1), A2A (Phase 2)       | Start simple, standardize later                                        |
| D-003 | Human-in-the-loop      | Trust gradient per agent (0→3)                   | More nuanced than binary approve/reject                                |
| D-004 | State persistence      | JSONL                                            | No database dependency                                                 |
| D-005 | Watcher                | watchdog (Python)                                | Mature, cross-platform, event-driven                                   |
| D-006 | Correction memory      | Scar engine (Lucy mechanism)                     | Corrections become routing rules                                       |
| D-007 | Mobile interface       | Telegram bot (MVP) → PWA (target)                | Telegram for immediate use, PWA for branded experience                 |
