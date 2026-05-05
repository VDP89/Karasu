# Next Session Entry Point

## Status: UI MVP closeout

UI-1 through UI-9 PRs are all open and mergeable. The
read-only watchtower MVP per UI-0 §10 is complete. UI-9
shipped the test surface that closes Codex pin C ("every
/api/health-derived state requires unit tests"); every
projection on the wire is now structurally locked.

The "next session" is no longer about another UI-N chunk in
the brief. It's about:

  1. The merge sequence — landing UI-6 / UI-7 / UI-8 / UI-9
     in stacked-PR order to main.
  2. (Optional) Running the Lighthouse runner to commit a
     baseline report under docs/ui/lighthouse/<date>.json.
  3. The first UI-10+ chunk — write paths, scar revoke,
     trust adjust, push notifications. Each earns its own
     brief per UI-0 §6.

## 2026-05-04 — Lighthouse baseline already ran

`scripts/ui_lighthouse.py` ran against the UI-9 stack
(committed in the same PR follow-up):

```text
performance      81 / 95   FAIL
accessibility    95 / 95   PASS
best-practices   96 / 95   PASS
seo              90 / 90   PASS
```

The performance miss splits into editorial (do NOT fix:
unminified CSS / JS, render-blocking <link>s, hero is the
crow itself) and server-side (gzip + Cache-Control on
/assets/*). The server-side fix is pin-aligned (no chrome,
1-line change in server.py) but UI-9 charter is verification-
only AND Pin #1 from UI-9 audit gates UI-10+ behind an
operator-signed brief. So the choice is:

```text
A1. Apply gzip + Cache-Control as a UI-9 follow-up
    (next-session.md flagged it as an option pre-run, and
    Codex's UI-9 audit was clean on the verification charter).
    Estimated lift: Performance ≈ 92-95.
A2. Open a dedicated micro-chunk (UI-9.1 server perf) with
    its own brief + audit.
A3. Accept Performance 81 with a documented exception in
    docs/ui/lighthouse/README.md.
```

Lean: A1 is the cleanest. The change is two lines in
``UIHandler._send`` (gzip the body when content-type is
text/css / text/html, set Cache-Control on /assets/* with a
short TTL like 3600s), it does not add chrome, and the
threshold contract gets met without a new chunk. But A1 is
operator-decision because it touches production code.

## Goal options for the next session

```text
A. Merge sequence + apply the Lighthouse fix (A1 above).
   Land #78 → #79 → #80 → #81 (UI-9). Each PR rebases onto
   the post-merge main; --delete-branch only on the leaf
   (#81). Then apply A1 (gzip + Cache-Control on
   /assets/*) as a tiny PR against main, re-run Lighthouse
   to confirm Performance ≥ 95, commit the new
   <date>.json.

B. UI-10 design brief.
   First write-path chunk. Likely candidate: scar revoke
   (read existing scars + select one + emit a human_decision
   event with the revoke). Needs:
     - operator-confirmed UX (drawer extension? new route?)
     - new bus event schema (revoke = human_decision with
       data.action = "scar_revoke" + scar_id)
     - SW cache contract revisited (the new POST endpoint
       MUST be network-only)
     - confirm dialog before mutation (Karasu's first
       destructive-ish UI)
   Out of scope until the operator signs off the brief.

C. Defer UI-10 + run dogfood on the merged MVP.
   Use Karasu against a real workflow for a week, file
   findings as issues, return to UI-10 with operator-driven
   priorities instead of brief-driven ones.
```

Lean: A is mechanical and unlocks the rest. B + C are
operator-driven decisions; do not start without sign-off.

## Binding constraints carried into UI-10+

UI-9 audit added SIX additional pins for UI-10+ (Codex,
2026-05-04, PR #81 APPROVED-with-observations). Verbatim:

```text
1. UI-10+ introduces write paths, so it must earn a new
   brief before code.
2. Every write path needs explicit confirmation semantics:
   what mutates, where, and how the operator can verify it.
3. Read-only watchtower contracts remain frozen unless the
   new brief explicitly supersedes them.
4. Do not let Lighthouse, PWA, or accessibility tooling
   drive new chrome.
5. Every server projection or mutation that affects visual
   state must ship deterministic tests before screenshots.
6. Reduced-motion remains a release gate for every new
   moving surface.
```

Pin #1 is the gating one: UI-10+ does NOT open until an
operator-signed brief exists, parallel to how UI-0 sealed
the visual direction before UI-1 opened. Pin #2 + #5 are
the structural gates for any write surface; pin #3 + #4 +
#6 are the editorial guardrails that prevent the watchtower
from drifting toward dashboard.

UI-2..UI-8 audits + the UI-8 design review + the UI-9
verification chunk locked **22 binding pins** so far:

- 7 pins from UI-3 / UI-4 / UI-5 audits (shell still,
  transform isolation, second asset, beak-leading rotation,
  full-shell .webm, no node performance, /api/health-state
  unit-tested).
- 5 pins (A-E) from the UI-6 audit (map = orientation,
  no node motion, /api/health-state needs tests, latest-
  event semantics, drawer/inspector does not compete).
- 5 pins from the UI-7 audit (PWA shell no excitement,
  offline pose only, SW no stale bus JSON, new state needs
  test or manual path, no install/toast/badge chrome).
- 3 P1 + 3 P2 from the UI-8 design review locked pre-
  implementation (api/* first-branch network-only, empty
  localStorage muted placeholder, CACHE_NAME explicit + bump
  rule documented, signal-lost not injured pose, no .webm
  for static infra, manifest hex matching tokens.css).
- 5 pins from the UI-8 implementation audit (PWA contracts
  validated by tests where feasible, Lighthouse as
  verification not design driver, SW cache boring,
  deterministic assertions over browser-state magic, no
  install/toast/badge/dashboard furniture).

UI-10+ inherits all 22. Any chunk that introduces a
write path adds at least:

```text
- Mutation confirmation flow (confirm dialog or two-step).
- Bus mutation goes through ScarEngine / human_decision
  events, NEVER direct bus mutation from the UI.
- SW caches are revisited: the new POST endpoint is
  network-only; its idempotency / safety surface is unit-
  tested before the visual code lands.
- Audit cadence still applies: PNG + .webm if motion +
  README + audit prompt for Codex.
```

## Surface contract — must respect

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol, the bus event schema (additive
  only) — all frozen.
- The UI is read-only against the bus until a UI-10+ chunk
  opens write paths through ScarEngine / human_decision
  events.
- The 20-key /api/events projection shape is now CONTRACT
  (pinned by tests/test_ui_server_http.py). Adding a field
  requires updating EVENTS_PROJECTION_KEYS in the same PR.
- Lighthouse thresholds 95 / 95 / 95 / 90 are CONTRACT.
  Bumping down requires operator-signed rationale in
  docs/ui/lighthouse/README.md.
```

## Audit cadence reminder

UI-10+ chunks introducing write paths will tighten the audit
cadence. Per UI-0 §6:

```text
1. PNG + .webm (motion) for every visible state.
2. Unit tests for any projection the UI consumes.
3. HTTP-level shape lock if a new endpoint ships.
4. Confirmation flow screenshots (Karasu's first
   destructive UI is also its first place where the
   operator must explicitly opt in to mutating state).
5. Audit prompt for Codex out-of-band via ChatGPT.
6. Editorial check: pin #5 from UI-7 audit and pin E from
   UI-6 audit converge here — write affordances must NOT
   become dashboard chrome.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §6 (UI-10+ roadmap entry)
   + §10 (Definition of "done" for the UI MVP — verify
   each item ticks off post-merge).
2. docs/ui/screenshots/UI-9-tests/README.md — the
   verification-only pattern UI-9 established.
3. docs/ui/lighthouse/README.md — threshold contract +
   ignore list.
4. tests/test_ui_server_http.py — the shape-lock pattern
   UI-10+ extends when new endpoints ship.
5. src/karasu/eventbus.py + docs/event-schema.md — the
   contract any UI-10 write path must respect.
```

## Chunk size estimate (if starting UI-10)

```text
Code:    ~300 LOC (new endpoint + revoke flow + confirm
         dialog + state management + tests for the new
         projection)
Assets:  no new SVG (existing palette covers confirm states)
Docs:    ~120 LOC (screenshots README + audit prompt +
         memory closeout)
Tests:   shape locks for the new endpoint + unit tests for
         the revoke flow precedence
Total:   under the 400 LOC budget.
```

## Do NOT do yet

```text
- Do NOT open a UI-10+ branch without an operator-signed
  brief — the previous chunks landed under brief sign-off
  (UI-0); UI-10 needs its own.
- Do NOT cache /api/* under any circumstances. Pin #3 from
  UI-7 + Pin P1#1 from UI-8 design review carry forward.
- Do NOT add install banners, update toasts, connection
  badges, or "offline mode" dashboard furniture (Pin #5
  UI-8 audit binding).
- Do NOT lower the Lighthouse thresholds.
- Do NOT introduce a build step.
- Do NOT tag @codex review.
```

## Anchor for the previous sessions

- **UI-9 (server tests + Lighthouse pass) PR open**
  (`feat/ui-9-tests-lighthouse`, stacked on
  `feat/ui-8-pwa`). 10 HTTP-level shape lock tests pin
  every projection on the wire (/api/events 20-key
  projection, /api/health 4-key + flight sub-shape,
  /api/meta 2-key, /assets/sw.js Service-Worker-Allowed
  header, /offline.html route + body + class,
  /assets/manifest.json colours matching tokens.css +
  top-level shape). scripts/ui_lighthouse.py optional CLI
  runner with thresholds 95/95/95/90 + ignore list. 5
  reduced-motion smoke PNGs verify the chromatic
  whitelist contract. Pin C ("every /api/health-derived
  state requires unit tests") reaches its endpoint —
  every wire shape now has a structural lock that fails
  BEFORE a future visual change can drift it.
- **UI-8 (PWA shell + offline page) PR open**. 4 PNGs +
  no .webm + manifest + SW + offline.
- **UI-7 (Detail panel) PR open**. 6 PNGs + .webm 336 KB
  + drawer + 5-class JSON highlighter.
- **UI-6 (Live Map + crow flight) PR open**. 8 PNGs +
  .webm 242 KB + 22 unit tests for _flight_route.
- UI-5 merged 2026-05-04 via PR #74.
- UI-4 merged 2026-05-03 via PR #72.
- UI-3 merged 2026-05-03 via PR #70.
- 432/434 pytest on Windows local (10 new HTTP shape
  locks added; the same two preexisting failures
  (`test_git_tree_path_exists_passes_cwd_through` and
  `test_valid_asset_under_static_dir_is_served`,
  Windows CRLF + cwd quirks) remain — CI Linux green.
- Karasu HEAD post-merge: TBD (UI-6/7/8/9 stacked,
  awaiting audit + merge).
