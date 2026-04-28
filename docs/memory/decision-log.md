# Decision Log

## Core principles

- Karasu is a broker, not an agent
- Human is not the message bus
- Observe first, design after

## Phase decisions

### Phase 1A

Decision:
- Close PR early once loop works

Reason:
- Avoid infinite review loops

---

### Phase 1B

Decision:
- Dogfood first, PR after

Reason:
- Real behavior > assumptions

---

### JSONL logging

Decision:
- Keep implementation minimal (append-only)

Reason:
- Observability first, architecture later

---

### Telegram

Decision:
- Not core product, only temporary interface

Reason:
- Final direction is Karasu native console
