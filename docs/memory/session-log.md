# Session Log

## 2026-04-28 — Observability stack completed

What changed:
- PR #9: JsonlTailReader (fixed atomic consumption + unicode split)
- PR #10: `karasu tail` CLI
- PR #11: Local dogfood runbook
- PR #12: `karasu analyze` CLI

Decisions:
- Observability-first approach validated
- No UI/Telegram before data
- Event noise must be measured before any filtering

Impact:
- Karasu is now a fully observable system (input → storage → output → analysis)

Next step:
- Run Phase 1B dogfood locally
- Collect real metrics
- Decide on debounce/filtering based on data

---
