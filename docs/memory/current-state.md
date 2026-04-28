# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: COMPLETED (no-adapter pass validated, all findings closed)
Phase 1C: NOT STARTED (real Claude adapter loop)

## System status

- Core pipeline: watcher → classifier → dispatcher → reporter ✔
- JSONL bus + TailReader ✔
- CLI consumer: `karasu tail` ✔
- CLI analyzer: `karasu analyze` ✔
- Cross-platform ignore matching (forward-slash normalization) ✔
- Debounce per `(path, change_type)` with 250 ms default ✔
- Dispatcher suppresses `agent_response` when no adapter handles ✔
- Telegram/UI: DEFERRED

## Verified behavior (Phase 1B closed)

- Reader is atomic (no loss on partial consumption)
- Unicode-safe line splitting
- Ignore patterns work on Windows (was the silent CI/local divergence)
- Editor save bursts collapse via debounce, leading event preserved
- No `agent_response` written when no adapter exists — bus is real work only

## Final Phase 1B metrics (from #14)

| Metric                | Baseline | Post F2+F4 | Post F3 (final) |
|-----------------------|---------:|-----------:|----------------:|
| Total events          |     3022 |         65 |          **11** |
| `file_change`         |     1521 |         31 |              11 |
| `agent_response`      |     1501 |         34 |           **0** |
| Duplication factor    |     253× |      2.82× |           2.75× |
| Peak events/sec       |      203 |         19 |           **2** |

99.6 % reduction from baseline on the same workload.

## Findings F1–F5 — all resolved

| | Status | PR |
|---|---|---|
| F1 cascade               | resolved (collateral)     | #15 |
| F2 Windows ignore        | resolved                  | #15 |
| F3 1:1 no-route response | resolved (option B)       | #22 |
| F4 no debounce           | resolved                  | #18 |
| F5 watcher exit code 2   | not reproduced post-fix   | (collateral #15) |

## Current risks

- Real agent (Claude CLI) loop not validated yet — Phase 1C.
- Adapter output contract not stress-tested under repeated edits.
- Cost/latency characteristics unknown (no real adapter run).

## Next step (entry point)

```text
Phase 1C — wire real Claude adapter (minimal, validation-only).
See docs/memory/next-session.md.
```

## Do NOT do yet

```text
- Do not add Telegram before Phase 1C validates the adapter loop.
- Do not add controller/loop.
- Do not mutate scars from chat.
- Do not optimize, parallelize, abstract, or generalize the adapter.
```
