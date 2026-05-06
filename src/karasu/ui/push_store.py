"""Push subscription store — read-only surface (UI-12a).

The store is a flat JSON file at a configurable path (default
``karasu-push.json`` next to ``events.jsonl``). UI-12a only
reads the store; UI-12b earns the writers (subscribe /
unsubscribe). UI-12c earns the VAPID generation + the
server-side push emitter.

File shape (top-level sections explicitly separate; Codex
audit pin §11.6 — same file, two normalised sections):

```json
{
  "vapid": {"public": "<b64u>", "private": "<b64u>"},
  "subscriptions": [
    {
      "endpoint": "<full url>",
      "endpoint_hash": "<sha256-hex>",
      "keys": {"p256dh": "<b64u>", "auth": "<b64u>"},
      "categories": ["attention", "errors"],
      "created_at": "<iso8601 utc>"
    }
  ]
}
```

UI-12 brief §3-F binding: PRIVATE STORE.

- File mode 0600 on POSIX. The reader does not enforce
  the mode (operator hygiene); the WRITER added in UI-12b
  will. Reader does not log raw endpoint / keys.
- Never bus-replayed; not part of /api/events.
- Only the count + the VAPID public key surface via
  /api/push (no per-subscription contents).

UI-12a contract: if the file is absent, the reader
returns the empty-store sentinel. VAPID keys are NOT
generated here — UI-12c earns that path with the
``cryptography`` dep gated by §11.6.13.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PushStoreState:
    """Read-only projection of the push subscription store.

    Surfaced to the UI server's ``/api/push`` handler. The
    raw subscriptions, raw endpoints, p256dh / auth keys, and
    the VAPID *private* key are NOT carried in this dataclass
    by design (§11.6.5 — raw endpoint and keys never leave
    the store; §3-D — only the public VAPID key may surface
    via /api/*).
    """

    subscription_count: int
    vapid_public_key: str | None
    file_present: bool = field(default=False)


_EMPTY_STATE = PushStoreState(
    subscription_count=0,
    vapid_public_key=None,
    file_present=False,
)


def read_push_store(path: Path) -> PushStoreState:
    """Read the push store at ``path`` and project it for the UI.

    If the file does not exist (first start, or operator has
    not configured push at all), returns the empty-state
    sentinel. This is NOT an error — UI-12a's contract is
    that the surface works against an absent store.

    Malformed JSON or a non-object root raises
    ``PushStoreError``. The operator's recourse is to delete
    the file and let UI-12b re-bootstrap a fresh subscription
    set; silently coercing garbage would mask a real
    corruption.

    Filesystem errors (the file exists but cannot be read —
    permission denied, the path is a directory, the device
    disappeared) also raise ``PushStoreError`` so the
    ``/api/push`` handler folds them into the same structured
    500 contract instead of letting the bare ``OSError`` reach
    the wire. UI-12b will create the writer side as a 0600
    file; this guard keeps the read path symmetric on the day
    file mode trips for any reason. Codex P2 on PR #98 round 1.

    Sub-objects with the wrong shape (``vapid`` missing
    ``public``, ``subscriptions`` not a list) degrade to the
    empty-state defaults for that field rather than raising,
    so a partial store still surfaces a usable count + null
    public key.
    """
    if not path.exists():
        return _EMPTY_STATE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PushStoreError(
            f"push store at {path} could not be read: {exc}"
        ) from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PushStoreError(
            f"push store at {path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise PushStoreError(
            f"push store at {path} is not a JSON object "
            f"(got {type(raw).__name__})"
        )

    subscriptions = raw.get("subscriptions")
    count = (
        len(subscriptions)
        if isinstance(subscriptions, list)
        else 0
    )

    vapid = raw.get("vapid")
    public_key: str | None = None
    if isinstance(vapid, dict):
        candidate = vapid.get("public")
        if isinstance(candidate, str) and candidate:
            public_key = candidate

    return PushStoreState(
        subscription_count=count,
        vapid_public_key=public_key,
        file_present=True,
    )


class PushStoreError(Exception):
    """Raised when the push store is present but unreadable."""


# UI-12 brief §3-G binding — the documented category enum.
# Closed for UI-12; future categories earn their own brief.
PUSH_CATEGORIES: tuple[str, ...] = (
    "attention",
    "errors",
    "corrections",
)


def project_push_state_payload(
    state: PushStoreState,
) -> dict[str, Any]:
    """Project a :class:`PushStoreState` into the /api/push
    response body.

    Pin §11.6.5 + §11.6.16: raw endpoint / keys / private key
    NEVER appear in the projection. Only ``subscription_count``
    and ``vapid_public_key`` (the public half) surface. The
    ``state`` field is fixed to ``"supported"`` from the
    server's perspective; the client decides
    "unsupported" / "denied" via browser feature detection
    per UI-12 brief §10.9.
    """
    return {
        "state": "supported",
        "categories": list(PUSH_CATEGORIES),
        "subscription_count": state.subscription_count,
        "vapid_public_key": state.vapid_public_key,
    }
