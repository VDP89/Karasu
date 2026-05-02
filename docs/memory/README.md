# Karasu Project Memory

This directory is the persistent operational memory for Karasu.

It exists so Claude Code, Codex, ChatGPT, and future agents can restart work without relying on external chat history or the user acting as the message bus.

## Files

- [`current-state.md`](current-state.md) — latest stable project state, active phase, open decisions, and next session entry point.
- [`session-log.md`](session-log.md) — chronological bitacora of important sessions, merges, decisions, and phase transitions. One paragraph per session; per-session deep dives live in `sessions/`.
- [`sessions/`](sessions/) — per-session deep-dive bitácoras: setup, real-time debugging, evidence captured, lessons learned. Written for sessions that close a phase, surface multiple findings, or run a dogfood. See [`sessions/README.md`](sessions/README.md) for the convention.
- [`decision-log.md`](decision-log.md) — durable architectural and product decisions, including what was deferred and why.
- [`next-session.md`](next-session.md) — startup checklist for any agent beginning a new work session.

## Update rule

Any PR that changes project direction, phase, architecture, or operational policy should update this directory.

Small bugfix PRs do not need to update memory unless they change the roadmap or the agent workflow.

## Canonical protocol

The user should not be required to copy context between agents.

Current temporary loop:

```text
Claude leaves report in repo -> user notifies ChatGPT
ChatGPT replies in repo -> user notifies Claude
```

Target loop:

```text
GitHub event -> Karasu detects -> Karasu routes -> agent acts or human decision is requested
```

Until Karasu implements automatic GitHub event listening, this directory is the shared state surface.
