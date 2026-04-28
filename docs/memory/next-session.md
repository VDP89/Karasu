# Next Session Entry Point

## Goal

Execute Phase 1B dogfood with full observability.

## Checklist

```text
1. Pull latest branches
2. Setup local env
3. Run karasu watch
4. Run karasu tail --follow
5. Modify files
6. Run karasu analyze
7. Record findings
```

## What to observe

```text
- events per file save
- duplicate rate
- burst rate (events/sec)
- Claude latency (if active)
- failures or crashes
```

## Output

Create issue:

```text
phase:1B dogfood results
```

Include metrics from analyze + subjective observations.

## Exit condition

```text
Enough data to decide:
- debounce needed or not
- filtering needed or not
- pipeline adjustments
```
