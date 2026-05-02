# Phase 3 cap shape — design (issue #47)

Design doc closing the outline-plan gate on issue #47. Picks the
cap shape that replaces the current per-originating-id counter so
chunk 4c (review-comment auto-handoff) can land without leaving an
unbounded distributed-loop window open.

This document is **design-only**. Implementation lands in a focused
PR after this doc + audit + NICE-TO-HAVE #3 (startup warning for
`trust_level >= 2`).

## Where the current cap stands

`LoopController` (chunk 3b) bounds resubmits with:

```python
RESUBMIT_CAP = 3  # per originating file_change.id
```

`_resubmit_for(agent_response, bus)` looks up `correlates_id` →
`file_change`, increments `_resubmit_counts[original.id]`, and
skips when the count reaches `RESUBMIT_CAP`.

This bounds **rapid spam on the same agent_response**. Six
`/scar` in succession on the same response → 3 resubmits, 3 cap
warnings, 0 leaks. The Phase 3 dogfood (issue #39) verified this
live.

## Where it does NOT bind

When a chain progresses one resubmit at a time and each resubmit
produces a *new* `agent_response` correlated to a *new*
`file_change.id`, the cap counter is fresh on every link:

```text
/scar #1 → cap[origin=A]=1 → resubmit emits A'
A' processed → response B (correlates A')
/scar #2 (after B is on the bus) → cap[origin=A']=1 → resubmits A''
A'' processed → response C (correlates A'')
/scar #3 → cap[origin=A'']=1 → ...
```

Each link starts a fresh counter. The cap protects per-origin
spam, **not** distributed chains. The Phase 3 audit recorded this
as a real but non-blocking limitation. Chunk 4c (auto-handoff)
makes it more reachable: a hostile PR comment could plausibly
sustain a chain at ~30 s per Claude dispatch.

## Decision — chain cap with origin-aware tracking (Option B)

```text
NEW invariant:
  Any chain of resubmits derived (transitively) from a single
  original event can have at most CHAIN_CAP hops, where
  CHAIN_CAP = 3 by default (same magnitude as the existing
  per-origin cap so behaviour is continuous).

NEW state on LoopController:
  _chain_depth: dict[str, int]
    Keyed by file_change.id. For an event written by the watcher
    (or any other source that didn't flag itself), depth = 0.
    For a controller resubmit, depth = parent's depth + 1, where
    "parent" is the file_change identified by resubmit_origin.

NEW field on the resubmitted file_change event:
  data.controller_chain_depth: int
    Persisted on the bus so analyze can audit chain depths
    post-hoc and so a fresh resubmit can compute its own depth
    from its parent's persisted value.

    NOTE on restart semantics: the persisted depth lets analyze
    reconstruct chain depth ACROSS restarts (the bus is the
    canonical record). It does NOT restore the live cap counter
    _chain_counts after a controller restart — that state is
    in-memory and per-process. After a restart, an operator who
    /scar's a chain that was already at cap pre-restart will
    get one extra shot at the chain. This is the same trade-off
    as F-WH-2 (dedup ring) and is consistent with the explicit
    out-of-scope item below.
```

### Why a chain depth and not a global session cap

Three options were on the table per issue #47:

```text
A) Global session cap
   Single counter per LoopController instance. Resets on restart.
   PRO:  trivially simple.
   CON:  punishes legitimate operators who genuinely correct
         many distinct events. After N legitimate corrections
         the controller refuses fresh, unrelated work.
         Operator confusion: "why did this dispatch never run?"

B) Chain cap with origin-aware tracking  ← chosen
   Track each resubmit's lineage. Cap when a single chain
   reaches CHAIN_CAP hops.
   PRO:  bounds distributed runaway WITHOUT punishing distinct
         corrections. Each genuine /scar starts a fresh chain.
         Lineage is on the bus (data.resubmit_origin → walk back
         to the root) so analyze can audit chain depth post-hoc.
   CON:  marginally more state. The depth dict can grow if the
         operator never restarts, but bounded by total
         file_changes (already capped by the queue + dedup).

C) Hybrid (per-origin cap PLUS soft session cap)
   PRO:  covers both spam-on-same-id AND distributed loops.
   CON:  two parameters to tune; per-origin cap is partly
         redundant once chain cap is in place (a chain length
         of 1 with N retries on the same hop is just per-origin
         spam, which the chain cap also bounds at depth=1
         repeats).

Discarded A and C; B alone is the right shape.
```

### Why depth = 3 (and not bigger)

The Phase 3b dogfood happily survived a CAP=3 per-origin under
real spam. CHAIN_CAP=3 keeps that behaviour for the spam case
(each rejection counts toward the same chain depth on the
originating event). For distributed chains, depth=3 means a single
hostile comment can fan to at most three Claude calls before the
controller refuses. 3 calls × ~30 s = ~90 s of wasted compute per
attack — acceptable as a stop rule.

If operator dogfood shows 3 is too tight, the cap is configurable.

## Behaviour table

```text
Scenario                                    Result
──────────────────────────────────────────  ──────────────────────
Watcher emits file_change A (depth=0)
/scar on response → resubmit A1 (depth=1)   OK, chain[A]=1
A1 processed, /scar → resubmit A2 (depth=2) OK, chain[A]=2
A2 processed, /scar → resubmit A3 (depth=3) OK, chain[A]=3
A3 processed, /scar → would emit A4 (d=4)   SKIP, "chain cap (3) reached for chain root A"

Watcher emits file_change B (depth=0)
/scar on response → resubmit B1 (depth=1)   OK, chain[B]=1
                                             — independent chain, A's cap doesn't apply

Spam: 6 /scar on response correlated to A   3 resubmits fire (depth 1, 1, 1
                                              against the same agent_response;
                                              3rd retry on chain[A] depth 1
                                              hits cap), 3 capped — same as
                                              today's per-origin cap behaviour
```

The third scenario is the trick: when a chain doesn't progress
(operator hammers the same response), every resubmit is at depth
1 of the same chain. The cap counts depth-1 resubmits within a
chain, so spam at the same depth still bounds at 3.

Concretely: `chain[root]` is the **count of resubmits in the
entire chain rooted at `root`**, not the depth of the latest one.
Each `_resubmit_for` increments `chain[root]`. Spam at depth 1
and a real progressing chain both increment the same counter,
both bounded by CHAIN_CAP.

That preserves the Phase 3 dogfood result and adds the
distributed-chain protection.

## Implementation sketch (NOT in this PR)

```python
# Module-level guard against pathological lineage chains.
# CHAIN_CAP bounds resubmits, not walk cost — a forged or cyclic
# lineage could otherwise spin _chain_root forever (F-CAP-5).
MAX_CHAIN_WALK_DEPTH = 64  # 21x the default CHAIN_CAP


# In LoopController._resubmit_for:
correlates_id = agent_response.data.get("correlates")
original = self._find_file_change(bus, correlates_id)
if original is None:
    ...

# Walk the resubmit_origin chain back to the root.
root_id = self._chain_root(original)

with self._chain_lock:
    count = self._chain_counts.get(root_id, 0)
    if count >= self.CHAIN_CAP:
        _log.warning(
            "controller resubmit: chain cap (%d) reached for "
            "chain root %s; skipping",
            self.CHAIN_CAP, root_id,
        )
        return
    self._chain_counts[root_id] = count + 1

# Compute the new event's chain depth.
# Only trust controller_chain_depth on events the controller
# itself emitted (F-CAP-2). For any other source the field is
# untrusted input and the depth resets to 1 (this resubmit is
# the first hop on a chain rooted at `original`).
if (
    original.source == "controller"
    and isinstance(original.data.get("controller_chain_depth"), int)
):
    new_depth = original.data["controller_chain_depth"] + 1
else:
    new_depth = 1

# Emit the resubmit, persist depth on the bus.
new_event = bus.append(Event(
    type="file_change",
    source="controller",
    data={
        **original.data,
        "controller_resubmit": True,
        "resubmit_origin": original.id,
        "controller_chain_depth": new_depth,
    },
))
self.submit(new_event)


def _chain_root(self, file_change: Event) -> str:
    """Walk resubmit_origin back to the root file_change.id.

    Defences:
    - F-CAP-1: missing parent → treat current as root.
    - F-CAP-2: only follow lineage on source="controller" events
      with controller_resubmit=True. External sources can carry
      controller_resubmit / resubmit_origin / controller_chain_depth
      as untrusted strings and we MUST NOT walk through them.
    - F-CAP-5: bounded walk via visited_set (cycle break) AND
      MAX_CHAIN_WALK_DEPTH (forged-deep-lineage break). On either
      trip, treat the current cursor as the root and continue.
    """
    cursor = file_change
    visited: set[str] = set()
    for _ in range(MAX_CHAIN_WALK_DEPTH):
        if cursor.id in visited:
            return cursor.id  # F-CAP-5: cycle detected
        visited.add(cursor.id)
        # F-CAP-2: only follow lineage on controller-emitted events.
        if cursor.source != "controller":
            return cursor.id
        if not cursor.data.get("controller_resubmit"):
            return cursor.id
        parent_id = cursor.data.get("resubmit_origin")
        if not isinstance(parent_id, str) or not parent_id:
            return cursor.id
        parent = self._find_file_change(self.bus, parent_id)
        if parent is None:
            return cursor.id  # F-CAP-1: parent was log-rotated away
        cursor = parent
    # F-CAP-5: walk depth ceiling reached. Treat the deepest reached
    # ancestor as the root rather than continuing forever.
    return cursor.id
```

## Frozen contracts (must NOT change)

```text
- AgentResponse, F3, F7, F8.
- Surface = sink (the surface still only writes human_decision;
  the controller still owns the cap).
- Single-worker invariant.
- Scar = stored correction only.
- I-001..I-006.
- TriggerSource Protocol.
```

The new `controller_chain_depth` field on `file_change.data`
extends the schema additively. Old `analyze` / `tail` continue to
work; they just don't surface the new field unless the operator
asks.

## Failure modes for the implementation chunk

```text
F-CAP-1  Chain root walk hits a missing parent.
         Wrong: traversal raises / returns None and we crash
                inside _resubmit_for.
         Right: when _find_file_change returns None for a
                resubmit_origin (log rotated, bus replayed
                partially), treat the current node as the root
                and continue. Cap binds against that node's id;
                worst case is a chain that lost its true root
                gets its own fresh cap counter. Still bounded.

F-CAP-2  Chain depth / lineage fields on non-controller sources.
         Wrong: an external producer (peer agent, future source,
                webhook payload reflected verbatim) could set
                data.controller_chain_depth, controller_resubmit,
                or resubmit_origin on its own events and either
                (a) inflate the depth so a fresh chain starts at
                cap, or (b) drag the walk through arbitrary ids.
         Right: trust controller_chain_depth ONLY on events with
                source="controller". When emitting a resubmit
                whose parent has any other source, set the new
                event's depth to 1 (this resubmit is the first
                hop). Walks (_chain_root) likewise stop at any
                cursor whose source != "controller", treating it
                as the root regardless of which controller_*
                fields it carries. Mirrored explicitly in the
                implementation sketch above.

F-CAP-3  In-memory chain dict grows unbounded.
         Wrong: every chain root accumulates forever in
                _chain_counts.
         Right: prune entries whose chain has been at cap for
                LONG_ENOUGH (or simpler: cap dict size and evict
                oldest). The cap counter is per-process anyway;
                worst case post-restart we lose the count and the
                operator gets one extra shot at the chain. Same
                trade-off as the F-WH-2 dedup ring.

F-CAP-4  Concurrent resubmits race on the chain dict.
         Wrong: two webhook events on the same chain race and
                both pass the cap check.
         Right: lock the chain-counter read+increment in one
                critical section (mirrors the existing
                _resubmit_lock pattern). Single-worker invariant
                already serialises the worker; the lock covers
                the bus subscription thread + any other
                producer that hits _resubmit_for.

F-CAP-5  Cyclic / forged / pathologically deep lineage.
         Wrong: _chain_root follows resubmit_origin transitively
                with no upper bound on walk depth. A bus that
                contains a forged event A whose resubmit_origin
                points at B, where B's resubmit_origin loops back
                to A (or where the chain is N=10_000 hops deep
                via crafted events), spins the walk forever or
                burns CPU on every resubmit.
         Right: two layered defences in _chain_root:
                  (a) visited_set tracks ids already walked in
                      this call. On revisit, treat the current
                      cursor as the root and stop.
                  (b) MAX_CHAIN_WALK_DEPTH (default 64, ~21x
                      CHAIN_CAP) bounds the loop count even
                      without a cycle. On ceiling, treat the
                      deepest cursor as the root.
                Both are independent: (a) catches cycles
                regardless of length; (b) catches forged-deep
                lineage that never repeats an id. The cap counts
                resubmits emitted by the controller, but the
                walk cost must be bounded BY CONSTRUCTION since
                lineage can be supplied by untrusted producers
                even with F-CAP-2 in place (an attacker who only
                sets the lineage fields once on a single forged
                event, then issues legitimate resubmits chained
                onto it, would otherwise force a deep walk on
                every subsequent _resubmit_for).
```

## Test sketch (NOT in this PR; will land with the implementation)

```text
Core invariants:
- Single chain: 3 resubmits OK, 4th capped with chain-root id.
- Independent chains: chain[A] at cap doesn't block chain[B].
- Spam at depth 1: same response /scar'd N times → 3 resubmits,
  3 capped. Same observable behaviour as today's per-origin cap.
- Mid-chain progressing: /scar on each new response in turn →
  chain depth increments, capped at the configured value.

F-CAP-1 (missing parent):
- _chain_root on missing parent: parent_id present but bus has
  no event with that id → walk treats current cursor as root.

F-CAP-2 (untrusted lineage on non-controller events):
- External file_change with source="watcher" carrying
  data.controller_chain_depth=99 is treated as depth 0 root
  by both _chain_root (stops at the watcher event) and the
  emit path (new resubmit gets depth=1, not 100).
- File_change with source="github_webhook" carrying
  controller_resubmit=True is NOT walked through; treated as
  root.
- File_change with source="controller" but
  controller_resubmit absent / falsy is treated as root.

F-CAP-5 (cyclic / forged-deep lineage):
- Cycle: events A and B, each source="controller", with
  resubmit_origin pointing at the other → _chain_root returns
  on second visit, does not infinite-loop.
- Self-loop: event A with resubmit_origin=A.id → _chain_root
  returns on second visit.
- Pathologically deep but acyclic lineage: chain of N >
  MAX_CHAIN_WALK_DEPTH events, each source="controller" →
  walk stops at the ceiling, treats deepest reached cursor as
  root, _resubmit_for completes in bounded time.

Restart semantics:
- _chain_counts is in-memory, per-process. After a controller
  restart, a chain that was at cap pre-restart admits one
  more resubmit (counter resets). Persisted depth on bus
  events is unaffected — analyze still reports correct depth
  values across the restart boundary.

Eviction (F-CAP-3, NICE-TO-HAVE from audit round 1):
- _chain_counts size never exceeds the configured ceiling.
  When ceiling is hit, oldest entry (insertion-order or
  last-touched) is evicted. After eviction, if a /scar lands
  on the evicted chain root, the operator gets one fresh
  shot — same trade-off as F-WH-10 dedup ring overflow.
```

## Out of scope

- Persisting `_chain_counts` across restarts. The bus persists
  `controller_chain_depth` so analyze can audit chain depth
  across restarts, but the live cap counter is intentionally
  in-memory and per-process. Cross-restart re-fire window is
  the same shape as F-WH-10 dedup ring overflow — narrow and
  acceptable.
- Per-user-id caps for chat-recorded scars. Trust gradient is
  per-agent, not per-user.
- Telemetry on capped chains as a controller_action event. Defer
  until operator dogfood shows we want to track the rate.

## Exit condition for this PR

```text
- This document lands on main.
- Audit accepts the chain-cap shape (or asks for a different
  decision).
- next-session.md notes that one of the two chunk-4c gates is
  now resolved (issue #47 outline). The other gate
  (NICE-TO-HAVE #3 startup warning) still needs to land.
- Issue #47 stays open as the implementation tracker; closes
  when the focused PR implementing this design lands.
```

## Anchor

- Issue #47 surfaced from the Phase 3+ pre-mortem audit (PR #48,
  section 2.3).
- Phase 3 dogfood (issue #39) measured the current per-origin
  cap behaviour at 3-of-6 enforcement under spam.
- Chunk 4c (review-comment auto-handoff) is gated on this design
  outline + NICE-TO-HAVE #3 startup warning. Both can land
  independently after this PR.
