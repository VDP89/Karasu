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
