# Event schema

All Karasu state lives in an append-only JSONL log. Each line is one
event. Components communicate exclusively by reading and appending to
this log — there is no other shared state.

## Record shape

```json
{
  "id": "uuid",
  "timestamp": "ISO-8601",
  "type": "file_change | git_event | agent_response | human_decision",
  "source": "watcher | adapter | interface | ui",
  "data": {
    "path": "relative/path",
    "change_type": "created | modified | deleted",
    "classification": "code_change | doc_change | scar_change | config_change",
    "priority": "low | normal | high | critical"
  },
  "dispatch": {
    "agent": "claude_code | codex | null",
    "status": "pending | dispatched | completed | failed",
    "trust_level": 0
  },
  "response": {
    "content": "...",
    "requires_human": true
  }
}
```

## Field notes

- **`id`** — UUID v4. Used to correlate later events (an
  `agent_response` references the `file_change` it answers).
- **`timestamp`** — UTC, ISO-8601 with millisecond precision.
- **`type`** — drives which downstream component reacts. The
  classifier reacts to `file_change`/`git_event`; the reporter
  reacts to `agent_response`; the scar engine reacts to
  `human_decision`.
- **`source`** — which component produced the event. Useful for
  debugging and for trust accounting.
- **`data`** — type-dependent payload. The fields shown above are
  the union; not every type uses every field.
- **`dispatch`** — populated by the router when it picks an agent.
  `status` advances `pending → dispatched → completed | failed`.
- **`response`** — populated by adapters and consumed by the
  reporter. `requires_human` is set by the trust gradient.

## `human_decision` payloads

`human_decision` events come from operator-driven write paths.
Three surfaces produce them today:

- **Telegram** (`source = "interface"`) — `/correct` and `/scar`
  commands carry `data.user` (Telegram user id) and `data.text`
  (the raw command line). The redacted variants used for unknown
  / unauthorized callers omit the body.

- **UI scar revoke** (`source = "ui"`, UI-10) — the operator
  surface's `POST /api/scars/{id}/revoke` endpoint emits an
  additive payload pinned by the UI-10 brief §3-D:

  ```json
  {
    "type": "human_decision",
    "source": "ui",
    "data": {
      "action": "scar_revoke",
      "scar_id": "<existing-scar-id>",
      "reason": "<optional, only present when supplied>"
    }
  }
  ```

  - `data.action` — fixed string `"scar_revoke"` for revoke
    events. Future write paths may add other action strings;
    consumers should treat the field as a discriminator.
  - `data.scar_id` — the id of the scar the operator revoked.
    The character set is `[A-Za-z0-9._:-]+` (URL-safe; pinned
    by the HTTP shape lock in
    `tests/test_ui_server_http.py`).
  - `data.reason` — optional, free text. Brief §10.2 + the
    HTTP shape lock: empty / whitespace-only reasons MUST NOT
    serialise as `""` or `null` — the field is omitted from
    the payload entirely.

  The fields are **additive**. Pre-UI-10 `human_decision`
  consumers (the controller resubmit reaction in
  `controller.loop`, the telegram redaction logic) do not
  read them; they see the same `{user, text}` shape they
  always have when the event came from Telegram, and they
  see a different shape when it came from the UI but they
  ignore it (the controller filters on `text` startswith
  `/scar` / `/correct`, which the UI variant does not carry).

- **UI trust adjust** (`source = "ui"`, UI-11b) - the operator
  surface's `POST /api/agents/{name}/trust` endpoint records an
  intent to change one configured adapter's trust level for the
  next watcher run. It does not mutate a running adapter instance.

  ```json
  {
    "type": "human_decision",
    "source": "ui",
    "data": {
      "action": "trust_adjust",
      "agent": "<adapter-name>",
      "trust_before": 1,
      "trust_after": 2,
      "reason": "<optional, only present when supplied>"
    }
  }
  ```

  - `data.action` - fixed string `"trust_adjust"` for trust
    adjustments.
  - `data.agent` - adapter name from the configured UI list.
  - `data.trust_before` - integer trust level before the
    adjustment, limited to the documented UI range `{0, 1, 2}`.
  - `data.trust_after` - selected integer trust level, also
    limited to `{0, 1, 2}`.
  - `data.reason` - optional, free text. Empty / whitespace-only
    reasons are omitted from the payload entirely.

  Unsupported configured values outside `{0, 1, 2}` are read-only:
  `/api/agents` surfaces them with an unsupported tag and the POST
  path rejects mutation from that state.

- **UI push subscribe** (`source = "ui"`, UI-12b) — the operator
  subscribed a browser to receive Web Push notifications. Emitted
  by `POST /api/push/subscribe` on a successful 204 (including the
  idempotent UPDATE path that overwrites an existing entry's
  categories).

  ```json
  {
    "type": "human_decision",
    "source": "ui",
    "data": {
      "action": "push_subscribe",
      "endpoint_hash": "<sha256-hex of the raw endpoint, 64 chars>",
      "categories": ["attention", "errors", "corrections"]
    }
  }
  ```

  - `data.action` — fixed string `"push_subscribe"`.
  - `data.endpoint_hash` — `hashlib.sha256(endpoint.encode("utf-8"))
    .hexdigest()`. Audit metadata only (UI-12 §11.6.6 + §11.6.16):
    NEVER used as a store lookup key; the raw endpoint is the
    operational id and lives ONLY in `karasu-push.json` (mode
    0o600 on POSIX). The hash is stable across subscribe /
    unsubscribe pairs for the same endpoint so an audit can
    correlate "operator unsubscribed the same browser they
    subscribed".
  - `data.categories` — validated, closed-enum subset of
    `{attention, errors, corrections}`. Canonical sort order
    (PUSH_CATEGORIES). Empty array allowed as a deliberate
    zero-noise subscription.

  Raw `endpoint`, `keys.p256dh`, `keys.auth`, and the VAPID
  private key NEVER appear on the bus under any circumstance
  (UI-12 §11.6.5 binding).

- **UI push unsubscribe** (`source = "ui"`, UI-12b) — the
  operator removed a browser subscription. Emitted by
  `POST /api/push/unsubscribe` on a successful 204 (server-side
  store mutation). The 404 path (endpoint already absent from
  the store) emits ZERO bus events — server silence is the
  audit truth on a non-mutation per UI-12b §11.6.13.

  ```json
  {
    "type": "human_decision",
    "source": "ui",
    "data": {
      "action": "push_unsubscribe",
      "endpoint_hash": "<sha256-hex of the raw endpoint, 64 chars>"
    }
  }
  ```

  - `data.action` — fixed string `"push_unsubscribe"`.
  - `data.endpoint_hash` — same shape + same restrictions as
    `push_subscribe`. No `categories` field on unsubscribe
    (the operator is removing the subscription wholesale, not
    updating selections).

  Audit-event correspondence: exactly one `push_unsubscribe`
  per server-side store mutation. The 204 path emits one;
  the 404 convergence path (operator's browser still holds a
  PushSubscription that the server has already pruned) emits
  zero.

## Priority semantics

`data.priority` on an `agent_response` is the **effective**
priority — the value that actually reached the adapter for that
dispatch, i.e. post any scar or classifier override. The
pre-override value (when an override fired) lives only on the
originating `file_change`; reconstruct it by following
`data.correlates` back to the `file_change.id`. See PR #60.

Tooling that audits the bus post-hoc should read this field via
`karasu.eventbus.effective_priority(event)`. The helper returns
`None` for events without the field rather than substituting a
default, so a missing priority on a pre-PR #60 `agent_response`
stays visible as a gap in the audit trail instead of silently
becoming `"normal"`.

## Compaction

Phase 1 keeps the log forever; Phase 2 will rotate when the file
exceeds `event_bus.max_size_mb` (see `karasu.yaml.example`). Rotated
segments are kept beside the active log and remain replayable.
