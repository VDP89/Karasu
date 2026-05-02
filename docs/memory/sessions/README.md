# Session bitácoras

Per-session operational deep dives. Each file is a self-contained
narrative of one focused work session: setup, what was tried, what
was found, what was decided, what was filed.

This is **complementary** to `../session-log.md` (the chronological
index) and `../current-state.md` (the latest snapshot). The index
gets a one-paragraph entry per session; the deep dive goes here.

## When to write one

Write a session bitácora for sessions that:

- Run a dogfood (Phase 1B/1C/3 patterns).
- Close a phase boundary.
- Surface ≥2 findings that need PR follow-ups.
- Involve a real-time debugging story worth preserving.

Skip for routine PR work — the commit + PR description are enough.

## Naming convention

```text
docs/memory/sessions/YYYY-MM-DD-<short-slug>.md
```

Examples:

- `2026-05-02-phase-3-dogfood.md`
- `2026-05-15-webhook-receiver-integration.md`

## Shape

Each file should cover, in order:

```text
1. Date + operator + environment (OS, Python, Claude version, tool versions)
2. Goal of the session
3. Setup steps (commands run, with output where instructive)
4. Findings and how they surfaced (real-time debugging narrative)
5. Evidence captured (timestamps, bus events, observable outputs)
6. Decisions made (and what was discarded)
7. Artifacts left behind (PRs filed, issues created, docs updated)
8. Lessons learned (what we'd repeat / change)
9. Next step pointer (back to next-session.md)
```

The narrative form matters. A future contributor (or agent) reading
this should be able to reconstruct what happened **and why** without
chat logs.
