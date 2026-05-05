# Karasu (烏)

Adaptive coordination layer between AI agents.

## The problem

When you run multiple AI agents on the same project, the human becomes the
message bus.

In our daily work we run Claude Code for implementation, Codex as a reviewer,
and a set of in-house enforcement hooks that watch the repository. Each of
those agents produces output that some other agent — or some human — needs
to react to. The reviewer leaves a comment, somebody needs to translate it
into a task. The hook rejects a commit, somebody needs to decide whether the
rule was right or whether the rule needs to change. The implementer finishes
a change, somebody needs to push it through the next gate.

That somebody was always us. We were the routing layer. Karasu is the routing
layer we wished we had: the human talks to Karasu, Karasu talks to the
agents, the agents respond to Karasu, and Karasu reports back.

## What Karasu does

**Watch.** A filesystem observer (and, later, git and webhook listeners)
turns events in the repository into a structured stream.

**Route.** Each event is classified and dispatched to the agent best suited
to handle it, taking into account that agent's current trust level and any
correction rules learned from past human feedback.

**Report.** Agent responses are filtered and formatted for the human
through a single interface — Telegram in the MVP, a Progressive Web App
later — instead of being scattered across terminals, review threads, and
notification panes.

## Five original elements

- **Correction memory.** When the human overrides a routing or response
  decision, Karasu offers to keep the correction as a rule. Future similar
  events are routed accordingly.
- **Feedback loops as core design.** Every dispatch is treated as a question
  whose answer feeds back into the system. Loops are first-class, not an
  afterthought bolted on top of a one-shot pipeline.
- **Trust gradient per agent (0→3).** Agents earn autonomy. A new adapter
  starts at level 0 (every action requires confirmation) and climbs toward
  level 3 (the agent acts and only reports). Trust is per-agent and per
  category of work.
- **Pure broker.** Karasu does not replace your agents. It connects the
  agents you already run — Claude Code, Codex, custom hooks — through
  thin adapters. It is a coordination layer, not a framework.
- **Watch-first trigger model.** The default trigger is "something changed
  on disk", not "the human typed a command". The human enters the loop
  when Karasu needs a decision, not to start every action.

## Quick start

```bash
pip install -e .
cp config/karasu.yaml.example karasu.yaml
karasu watch
```

To use the Telegram interface, set `KARASU_TELEGRAM_TOKEN` in your
environment and run:

```bash
karasu chat
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the module layout
and the flow of an event through watcher → classifier → router →
adapter → reporter.

## Roadmap

- **Phase 1 — Local daemon + Telegram (current).** Filesystem watcher,
  rule-based classifier, agent adapters, trust gradient, scar engine,
  JSONL event log, Telegram bot.
- **Phase 2 — Git-aware + A2A.** Git hook listener, GitHub webhook
  receiver, A2A Agent Cards for discovery, automatic Codex-review →
  Claude-Code-task handoff.
- **Phase 3 — PWA + Advanced.** Branded Progressive Web App, trust
  management UI, correction history visualization, push notifications.

Full plan in [docs/roadmap.md](docs/roadmap.md).

## The name

Karasu (烏) means *crow* in Japanese. In the old stories crows are
supernatural messengers — they cross between worlds and carry word
back. The project takes its name from that role: a messenger between
agents.

## Third-party notices

Karasu's UI ships a small number of third-party assets — the
crow silhouette adapted from OpenMoji's "Black Bird" emoji
(CC-BY-SA 4.0), Inter Display, and JetBrains Mono (both SIL
OFL 1.1). Full attributions, licence terms, and the list of
modifications live in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Built by

[DG Ingeniería SRL](mailto:info@dgingenieriasrl.com) — an infrastructure
engineering firm with a dedicated AI research lab. Karasu grew out of
the lab's day-to-day need to coordinate the agents already running in
production.
