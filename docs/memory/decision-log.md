# Decision Log

## Core principles

- Karasu is a broker, not an agent
- Human is not the message bus
- Observe first, design after

## Phase decisions

### Observability-first (NEW)

Decision:
- Build tail + analyze before any UI or automation

Reason:
- Prevent blind system design
- Quantify event noise before filtering

---

### Event integrity

Decision:
- Atomic consumption in tail reader
- Byte-based splitting (no splitlines)

Reason:
- Prevent silent data loss
- Ensure JSON correctness

---

### Analysis before control

Decision:
- Introduce `karasu analyze` before debounce/controller

Reason:
- Avoid premature optimization
- Base decisions on measured data

---

### F3 — agent_response semantics (issue #17)

Decision:
- The dispatcher emits `agent_response` ONLY when an adapter actually performs work.
- When no adapter handles the classification, dispatcher returns None and the bus carries no `agent_response`.

Reason:
- Bus represents real agent work, not pipeline mechanics.
- The previous 1:1 contract produced ~2× bus volume with zero information value (every no-route response said the same thing).
- "Seen but unhandled" is reconstructable from the originating `file_change` plus the absence of a correlated `agent_response`.
- Aligns with the principle "human is not the message bus" — the bus is a record, not a heartbeat.

Discarded:
- Option A (keep strict 1:1): doubles disk for no information.
- Option C (explicit no-op response): preserves contract but still doubles volume.
- Option B' with periodic summary: defer until trust gradient actually needs unhandled-event accounting.

---

### F7 — dispatch_on semantics (issue #25, PR #26)

Decision:
- `code_change` excludes `deleted` from dispatch by default.
- Per-rule `dispatch_on` overrides the default.
- Other classifications are NOT filtered at the pipeline; the dispatcher remains the single source of "no adapter handles this".

Reason:
- Atomic-write editors (VS Code, Claude Code Write tool, most "atomic save" implementations) emit a `deleted` event on the original path before the new content lands. Dispatching the adapter on that transient state sends it at a path that does not exist yet.
- Hardcoding "no dispatch on delete" globally would break legitimate workflows (security audit, scar/index cleanup, build-config deletion). Per-rule override preserves those.
- Other classifications without a documented default are NOT filtered — keeping the F3 contract that the dispatcher is the only place that decides "no adapter handles this".

Discarded:
- Global ban on dispatch-on-delete: would block valid security/cleanup flows.
- Hardcoding per classification: not extensible.
- Move the filter into the dispatcher: would conflate "no adapter for this classification" (F3) with "this change_type doesn't apply" (F7) — two distinct reasons that operators read differently.

---

### F8 — adapter timeout configurable per-agent (issue #25, PR #28)

Decision:
- `agents.<name>.timeout_s` reads from YAML and overrides the adapter's constructor default.
- Absent → keep the constructor default (120 s).
- `0`, negatives, and non-numeric values raise `ValueError` at startup with the YAML section name.

Reason:
- Phase 1C dogfood saw ~38 s for an auto-discovery dispatch. Real refactors will exceed 120 s.
- Operators must raise (or lower) the timeout without editing source.
- A silent "timeout = 0 means no timeout" coercion would let a bad config hang the watcher indefinitely. Explicit fail-fast is safer in Phase 1.

Discarded:
- Global `defaults.adapter_timeout_s`: not needed yet; per-agent unblocks Phase 2 work and the operator can copy the same number into multiple agents until a default is required.
- Coerce `0` to "no timeout": opaque footgun.

