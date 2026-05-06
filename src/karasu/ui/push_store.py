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

import hashlib
import json
import logging
import os
import stat
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_log = logging.getLogger(__name__)


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

    Invalid UTF-8 bytes in a present store (operator
    hand-edited with the wrong codepage, partial write, etc.)
    raise ``UnicodeDecodeError`` from ``read_text`` BEFORE
    ``json.loads`` ever sees the input. That is a ``ValueError``
    subclass, not an ``OSError``, so it would escape the
    OSError catch and reach the wire as a bare trace. We catch
    it alongside the read step and surface it as a malformed
    store so the operator gets the same generic 500 body.
    Codex P2 on PR #98 round 2.

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
    except UnicodeDecodeError as exc:
        raise PushStoreError(
            f"push store at {path} is not valid UTF-8: {exc}"
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


# ---------------------------------------------------------------------------
# UI-12b — writer side
# ---------------------------------------------------------------------------
#
# UI-12b earns the WRITER. The reader above is unchanged from
# UI-12a; the writer is strictly additive.
#
# Three pins drive this module:
#
#   §11.6.7 — atomic write via tmp + rename, mode 0600 on POSIX,
#             loud-stderr warning on looser observed mode (no
#             silent re-mode of an existing file).
#   §11.6.13 — browser/store two-phase mutation rollback (the
#              store WRITER side; the browser side lives in the
#              push.js front end).
#   §11.6.15 — module-level threading.Lock held across the FULL
#              read-modify-write transaction, NOT released
#              between read and write. The atomic tmp+rename
#              alone does NOT prevent lost updates under
#              concurrent server threads; the lock does.


class PushStoreNotFound(Exception):
    """Raised when ``remove_subscription`` cannot find the
    requested endpoint in the store.

    The POST /api/push/unsubscribe handler maps this to a 404 so
    the operator-facing contract distinguishes "endpoint absent"
    (recoverable browser-side) from "store malformed" (operator
    must intervene; that path raises ``PushStoreError``).
    """


# Pin §11.6.15 binding — module-level Lock held across the FULL
# read-modify-write transaction (read + mutate + write + rename).
# The atomic tmp+rename guarantees the FILE on disk is never
# partially written, but it does NOT serialise concurrent
# read-modify-write transactions — without this lock, two
# threads both reading the same old store and writing diverging
# tmp files race, and the later rename clobbers the earlier
# mutation (lost-update). One Lock per process is sufficient
# because http.server's ThreadingHTTPServer is the only writer
# in scope; UI-12c re-audits the boundary if a second writer
# process appears (filesystem lockfile graduation).
_STORE_LOCK = threading.Lock()


def compute_endpoint_hash(endpoint: str) -> str:
    """Return the audit-only ``endpoint_hash`` for a Web Push
    endpoint URL.

    SHA-256 hex of the UTF-8-encoded endpoint. The hash is
    stable across subscribe / unsubscribe pairs for the same
    endpoint, so an audit can correlate "operator unsubscribed
    the same browser they subscribed".

    Pin §11.6.6 + §11.6.16 binding: the hash is audit metadata
    ONLY. Callers MUST NOT use it as a store lookup key
    (subscriptions are keyed by the raw endpoint URL inside the
    store). The hash exists for bus emission correlation; it
    never replaces the raw endpoint in any operational path.
    """
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def append_subscription(
    store_path: Path,
    *,
    subscription: dict[str, Any],
    categories: list[str],
) -> None:
    """Append a new subscription or UPDATE the existing entry
    for the same endpoint.

    ``subscription`` must carry the keys ``endpoint`` (raw URL)
    and ``keys`` ({p256dh, auth}). ``categories`` is the
    validated, closed-enum subset (caller has already enforced
    the §3-B validation matrix; this writer trusts the inputs).

    Idempotent semantics (UI-12b §10.2): if the endpoint is
    already in the store, the existing entry's ``categories``
    are overwritten with the new validated set, ``updated_at``
    refreshes to the current iso8601 UTC, and ``created_at``
    is preserved. New entries get the same ``created_at`` and
    ``updated_at`` on first append.

    Held under :data:`_STORE_LOCK` for the full transaction
    (pin §11.6.15). The atomic tmp+rename inside
    :func:`_atomic_write` keeps the file integrity guarantee;
    the lock keeps the read-modify-write atomicity guarantee.
    """
    endpoint = subscription["endpoint"]
    endpoint_hash = compute_endpoint_hash(endpoint)
    keys = subscription["keys"]
    now = _utc_now_iso8601()

    with _STORE_LOCK:
        store = _read_or_empty_store(store_path)
        subs = store.setdefault("subscriptions", [])
        if not isinstance(subs, list):
            # The reader degrades a bad shape to count=0; the
            # writer normalises to an empty list before append
            # so a future read does not surface garbage.
            subs = []
            store["subscriptions"] = subs

        existing_idx = _find_subscription_index(subs, endpoint)
        if existing_idx is not None:
            existing = subs[existing_idx]
            if not isinstance(existing, dict):
                # Garbage at this index; replace it wholesale.
                subs[existing_idx] = _new_subscription_entry(
                    endpoint=endpoint,
                    endpoint_hash=endpoint_hash,
                    keys=keys,
                    categories=categories,
                    created_at=now,
                    updated_at=now,
                )
            else:
                existing["categories"] = list(categories)
                existing["updated_at"] = now
                # Preserve created_at if present + valid; backfill
                # with `now` if missing or wrong type.
                if not isinstance(existing.get("created_at"), str):
                    existing["created_at"] = now
                # Refresh keys + endpoint_hash too — the same
                # browser may have rolled its keys.
                existing["keys"] = dict(keys)
                existing["endpoint_hash"] = endpoint_hash
        else:
            subs.append(
                _new_subscription_entry(
                    endpoint=endpoint,
                    endpoint_hash=endpoint_hash,
                    keys=keys,
                    categories=categories,
                    created_at=now,
                    updated_at=now,
                )
            )

        _atomic_write(store_path, store)

    _log.info(
        "push_store: subscribed %s [%s]",
        endpoint_hash,
        ",".join(categories),
    )


def remove_subscription(store_path: Path, *, endpoint: str) -> None:
    """Remove the subscription matching ``endpoint`` exactly.

    Raises :class:`PushStoreNotFound` if no entry matches; the
    POST /api/push/unsubscribe handler maps that to a 404 with
    a generic body that does NOT echo the supplied endpoint
    (pin §11.6.16).

    Held under :data:`_STORE_LOCK` for the full read-modify-
    write transaction (pin §11.6.15).
    """
    endpoint_hash = compute_endpoint_hash(endpoint)

    with _STORE_LOCK:
        store = _read_or_empty_store(store_path)
        subs = store.get("subscriptions")
        if not isinstance(subs, list):
            raise PushStoreNotFound("subscription not found")

        existing_idx = _find_subscription_index(subs, endpoint)
        if existing_idx is None:
            raise PushStoreNotFound("subscription not found")

        del subs[existing_idx]
        _atomic_write(store_path, store)

    _log.info("push_store: unsubscribed %s", endpoint_hash)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now_iso8601() -> str:
    """Naive Z-suffix iso8601 UTC, matching events.jsonl timestamp
    convention. Centralised so tests can mock the moment if needed
    in future without re-discovering the format string."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_subscription_index(
    subs: list[Any], endpoint: str
) -> int | None:
    """Return the index of the entry whose ``endpoint`` matches
    exactly, or ``None`` if no match. Skips malformed entries
    (non-dict, missing endpoint) so a partially-corrupted store
    does not block a fresh write."""
    for idx, entry in enumerate(subs):
        if not isinstance(entry, dict):
            continue
        if entry.get("endpoint") == endpoint:
            return idx
    return None


def _new_subscription_entry(
    *,
    endpoint: str,
    endpoint_hash: str,
    keys: dict[str, Any],
    categories: list[str],
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "endpoint_hash": endpoint_hash,
        "keys": dict(keys),
        "categories": list(categories),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _read_or_empty_store(store_path: Path) -> dict[str, Any]:
    """Read the store as a mutable dict for the writer.

    Reuses the read path's parse + decode discipline (so a
    malformed file surfaces as ``PushStoreError``) but returns
    the raw dict instead of the public :class:`PushStoreState`.
    The reader's projection drops fields the writer needs to
    preserve (e.g. ``vapid``); reading the raw dict here keeps
    the writer faithful to whatever sections the operator's
    manual VAPID seed produced.

    Returns an empty dict ``{}`` when the file is absent — the
    caller is about to fill it. ``setdefault('subscriptions', [])``
    in :func:`append_subscription` then takes over.
    """
    if not store_path.exists():
        return {}
    try:
        text = store_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PushStoreError(
            f"push store at {store_path} could not be read: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise PushStoreError(
            f"push store at {store_path} is not valid UTF-8: {exc}"
        ) from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PushStoreError(
            f"push store at {store_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise PushStoreError(
            f"push store at {store_path} is not a JSON object "
            f"(got {type(raw).__name__})"
        )
    return raw


def _atomic_write(store_path: Path, content: dict[str, Any]) -> None:
    """Write ``content`` to ``store_path`` via tmp + rename.

    Pin §11.6.7 + §3-E binding:

      * Open ``<store_path>.tmp`` with mode 0o600 on POSIX via
        ``os.open(..., O_CREAT|O_WRONLY|O_EXCL, 0o600)``. EXCL
        fails if the .tmp already exists (a previous partial
        write or a concurrent writer outside the in-process
        Lock); we surface that as ``PushStoreError`` with the
        "partial write recovery needed" message so the operator
        knows to remove the .tmp manually. No automatic cleanup.
      * Write JSON, fsync, close.
      * ``os.replace(tmp, store_path)`` — atomic on POSIX (POSIX
        rename) and on Windows when both files are on the same
        volume.
      * If the destination file already exists with a looser
        mode than 0o600 on POSIX, log a loud-stderr warning
        citing the path + observed mode + remediation. The
        writer does NOT silently re-mode an existing file
        (pin §3-E binding — silent re-mode would be a quiet
        privilege change if the parent directory was open).
        The replacement file IS 0o600 because we wrote the
        .tmp under that mode and rename preserves the source
        file's mode on POSIX.
    """
    store_path.parent.mkdir(parents=True, exist_ok=True)
    _warn_if_existing_mode_loose(store_path)

    tmp_path = store_path.with_name(store_path.name + ".tmp")
    if tmp_path.exists():
        raise PushStoreError(
            f"push store tmp {tmp_path} already exists — "
            "partial write recovery needed (remove the .tmp "
            "manually after confirming no concurrent writer)"
        )

    flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL
    if hasattr(os, "O_BINARY"):  # pragma: no cover — Windows only
        flags |= os.O_BINARY
    fd = os.open(str(tmp_path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as fh:
            payload = json.dumps(content, ensure_ascii=False, indent=2)
            fh.write(payload.encode("utf-8"))
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:  # pragma: no cover — fsync unsupported
                # Some filesystems / platforms (notably some
                # Windows filesystem combinations) refuse fsync
                # on a writable handle. The replacement is still
                # atomic via os.replace; fsync is the
                # belt-and-suspenders durability layer.
                pass
    except BaseException:
        # If the write blew up, drop the .tmp so the next call
        # does not hit the "partial write recovery needed"
        # branch with a stale empty file.
        try:
            tmp_path.unlink()
        except OSError:  # pragma: no cover
            pass
        raise

    os.replace(str(tmp_path), str(store_path))


def _warn_if_existing_mode_loose(store_path: Path) -> None:
    """On POSIX, warn (loud-stderr) when the existing store
    file has a mode looser than 0o600.

    The writer does NOT chmod the file silently — that would be
    a quiet privilege change if the parent directory was
    world-readable. The existing file gets atomically replaced
    by the .tmp we just wrote at 0o600, so the END STATE is
    correct; this warning is the operator's signal to
    investigate why the file ever had a looser mode.

    Windows file modes are advisory and Win32 does not honour
    POSIX mode bits, so the warning is suppressed there.
    """
    if sys.platform.startswith("win"):  # pragma: no cover — Windows
        return
    if not store_path.exists():
        return
    try:
        observed = stat.S_IMODE(store_path.stat().st_mode)
    except OSError:  # pragma: no cover
        return
    # 0o600 is the strict ceiling; anything looser (group / world
    # readable, group / world writable) earns the warning.
    if observed & ~0o600:
        sys.stderr.write(
            f"WARNING: karasu push store {store_path} mode is "
            f"0o{observed:o}; expected 0o600. "
            f"Run `chmod 600 {store_path}`.\n"
        )
        sys.stderr.flush()
