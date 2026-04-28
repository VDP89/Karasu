# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: IN PROGRESS (local dogfood with observability)

## System status

- Core pipeline: watcher → classifier → dispatcher → reporter ✔
- JSONL bus + TailReader ✔
- CLI consumer: `karasu tail` ✔
- CLI analyzer: `karasu analyze` ✔
- Telegram/UI: DEFERRED

## Verified behavior (so far)

- Reader is atomic (no loss on partial consumption)
- Unicode-safe line splitting
- Tail CLI provides real-time visibility
- Analyzer provides metrics for noise/duplicates

## Current risks

- Real agent (Claude) loop not validated yet
- Event noise unknown until dogfood run
- Cost/latency characteristics unknown

## Active work

- Phase 1B: run local dogfood following docs/local-dogfood.md
- Collect metrics using `karasu analyze`

## Next step (entry point)

```text
1. Run karasu watch
2. Run karasu tail --follow
3. Trigger file changes
4. Run karasu analyze
5. Record findings in session-log
```

## Do NOT do yet

```text
- Do not add Telegram
- Do not add controller/loop
- Do not mutate scars from chat
- Do not optimize without data
```
