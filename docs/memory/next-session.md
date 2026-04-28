# Next Session Entry Point

## Goal

Continue Phase 1B: real Claude dogfood

## Checklist

```text
1. Pull latest main
2. Run karasu watch
3. Use real Claude CLI
4. Modify files intentionally
5. Observe behavior
6. Record anomalies
```

## What to observe

```text
- number of events per save
- Claude latency
- stdout structure
- errors / failures
- cost implications
- repeated triggers
```

## Output

Create issue:

```text
phase:1B real Claude observations
```

## Do not

```text
Do not implement new features during observation
Do not optimize prematurely
```

## Exit condition

```text
Enough real data to justify next PR (JSONL or fixes)
```
