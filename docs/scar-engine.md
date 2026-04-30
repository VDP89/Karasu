# Scar engine

The scar engine is Karasu's correction memory. Whenever the human
overrides a routing or response decision, the engine offers to keep
the correction as a rule so the same mistake is not repeated.

## What a scar is

A scar is a structured correction rule. It captures:

- the **trigger** — what kind of event the rule applies to
  (classification, path glob, agent, response shape);
- the **correction** — what should happen instead (different agent,
  different priority, suppress the dispatch entirely);
- the **provenance** — when the human made the original correction
  and against which event id, so the rule can be inspected and
  revoked.

Scars are stored as JSONL files under `.karasu/scars/`, one rule per
line, grouped by trigger family.

## How scars are created

1. Karasu dispatches an event to an agent.
2. The reporter forwards the response to the human through the
   interface.
3. The human overrides — for example, "this should have gone to
   Codex, not Claude Code", or "ignore changes to this path".
4. Karasu writes a `human_decision` event to the bus and asks:
   *Save this as a rule?*
5. If the human accepts, the engine derives a scar from the
   triggering event and the correction, and appends it to the
   appropriate rules file.

## How scars affect routing

Before the router picks an agent, the classifier consults the scar
engine. If a scar matches the incoming event, the matching keys of
the scar's correction overwrite the corresponding fields on the
event before dispatch. The router then acts on the corrected event.

This means scars are first-class routing inputs, not post-hoc
filters: an event that matches a scar never reaches the agent the
classifier originally would have selected for it.

## Golden rule — Scar ≠ execution

This rule is non-negotiable. Stated explicitly so future contributors
do not introduce control-flow regressions:

```text
Scar = stored correction only.
Scar ≠ execution.
Scar ≠ control-flow primitive.
```

Concretely, the codebase **must not**:

- Skip dispatching to an agent because "a scar exists for this path".
- Modify dispatch routing based on the *presence* of a scar (only
  via the explicit `_apply_scar_override` field rewrite, which is
  data correction, not control flow).
- Auto-retry an event because a scar was found at consultation time.
- Treat scars as a stateful agent with side effects.

The only valid scar effect is the in-memory rewrite of
``classification`` / ``priority`` / ``path`` performed by
``Pipeline._apply_scar_override`` *during a normal dispatch* of a
``file_change``. Every other use of scars (UI rendering via
``/scars``, audit, telemetry) is read-only.

Phase 3 chunk 3b (`/correct` / `/scar` resubmit) does NOT violate
this rule. The trigger for the resubmit is the **human action**
(`human_decision` event on the bus), not the *existence* of a scar
in `ScarEngine`. The resubmit is bounded by `RESUBMIT_CAP=3` per
originating `file_change.id`; subsequent dispatches that find the
same scar via `_apply_scar_override` apply the correction without
re-firing the loop.

## Phase 1 correction contract

The Phase 1 pipeline routes off the event's classification, priority,
and path. A scar correction may therefore only override these keys:

- `classification`
- `priority`
- `path`

Any other key (`agent`, `trust_level`, etc.) raises `ValueError` at
apply time. Recording an override the dispatcher cannot honour would
silently keep the original misroute and confuse the operator who
saved it.

Direct **agent override** (a scar that says *"send this to Codex
regardless of classification"*) is planned for Phase 2 once the
Telegram capture flow exists and we have real correction data to
inform the precedence rules (override vs. handles, override vs.
trust gradient, behaviour when the named agent is missing). See
`docs/roadmap.md`.

## Storage format

```jsonl
{"id":"uuid","created":"ISO-8601","trigger":{"classification":"code_change","path":"docs/**"},"correction":{"classification":"audit","priority":"high"},"source_event":"uuid"}
```

## Relationship with Lucy Syndrome

The scarring mechanism originates from the Lucy Syndrome research
framework, which models how a system's response to repeated harm
hardens into structural rules. In Karasu the same mechanism is
applied to a much smaller domain: a correction is a *harm* the human
has already had to absorb once, and the scar is the structural rule
that prevents the second occurrence.
