# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: IN PROGRESS (real Claude dogfood)

## System status

- Local pipeline implemented: watcher → classifier → dispatcher → reporter
- CI enabled and passing (Python 3.10 / 3.12)
- JSONL logging: planned (next PR)
- Telegram: planned (after observability)

## Verified behavior

- 46 tests passing
- Stub adapter smoke test successful
- No silent data loss observed
- No silent misrouting observed

## Current risk

- Real Claude CLI behavior unknown
- Event noise not yet measured
- Output format not validated for downstream routing

## Active work

- Phase 1B dogfood with real Claude CLI

## Next step (entry point)

```text
Run karasu watch with real Claude CLI
Observe behavior (no architecture changes yet)
Record findings
```

## Do NOT do yet

```text
Do not implement Telegram before logs are validated
Do not add LoopController
Do not add GitHub webhooks
Do not add scars mutation pipeline
```
