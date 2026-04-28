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
