# Next Session Entry Point

## Goal

**UI-9 — server tests + Lighthouse pass.** The chunk that
closes the UI MVP. HTTP-level pytest pinning the
`/api/events` / `/api/health` / `/api/meta` shapes against
the bus schema, plus a Lighthouse run on the live shell
hitting Performance ≥95, Accessibility ≥95, Best Practices
≥95, SEO ≥90. WCAG AA verified, reduced-motion verified.

After UI-9, UI-1..UI-9 ship the read-only watchtower MVP
end to end. UI-10+ adds write paths (scar revoke, trust
adjust, push notifications) and earns its own brief.

## Binding constraints carried forward (P0)

UI-8 audit added FIVE additional pins for UI-9 (Codex,
2026-05-04, PR #80 APPROVED-with-observations). Verbatim:

```text
1. UI-9 should validate the PWA contracts with tests where
   feasible: /api/* network-only, /assets/sw.js
   Service-Worker-Allowed header, /offline.html route,
   manifest colors.
2. Lighthouse is allowed as verification, not as design
   driver. Do not chase generic PWA / UI suggestions that
   would add chrome.
3. Keep SW cache behavior boring: explicit version,
   explicit precache, no runtime caching for live
   projections.
4. If tests touch service-worker behavior, prefer
   deterministic assertions over browser-state magic.
5. Do not add install banners, update toasts, connection
   badges, or "offline mode" dashboard furniture.
```

Pin #2 is the load-bearing one for the Lighthouse work: the
report tells us what's measurable, NOT what's right. A
Lighthouse "improve PWA" suggestion that asks for an install
prompt component IS NOT a UI-9 finding to action — it's a
recommendation to ignore in writing in the lighthouse README.
Pin #1 + #3 + #4 shape the test surface; pin #5 is the
editorial guardrail (UI-9 ships zero new shell affordances).

UI-2..UI-7 audits + the UI-8 design review + the UI-8
implementation audit locked seventeen binding pins so far.
UI-9 honours them all by NOT touching any visual surface —
the chunk is pure test + audit infrastructure. The ones
that matter most for this chunk:

```text
1. /api/events / /api/health / /api/meta projection shapes
   are CONTRACT. UI-9 pins them with HTTP-level pytest;
   any future projection change must update the tests in
   the same PR (this is the pin C lesson from UI-5 / UI-6
   audits taken to its endpoint).

2. Reduced motion verification is mandatory. The chromatic
   whitelist in reset.css covers transform / opacity /
   non-colour properties; UI-9 exercises the contract via
   a Playwright run with prefers-reduced-motion: reduce
   forced and asserts that every UI-2..UI-8 PNG state is
   reachable without motion-derived layout instability.

3. Lighthouse thresholds:
     Performance      >= 95
     Accessibility    >= 95
     Best Practices   >= 95
     SEO              >= 90 (lower bar — operator surface,
                              no public marketing copy)
   Failing thresholds are P0 for UI-9. Workarounds (skip
   PWA-only audits, etc.) need to be documented in the
   screenshots README.

4. WCAG AA verification — colour contrast on every shipped
   token combination, focus ring visible against every
   surface, keyboard nav on timeline / map / drawer
   covered. UI-2 documented contrast ratios; UI-9 verifies
   the documentation against the live render.

5. Stacked-PR mechanics. UI-9 branches from main once
   UI-6 / UI-7 / UI-8 land; if UI-8 still has open
   observations, UI-9 stacks on feat/ui-8-pwa.
```

The UI-8 design review pins (P1 + P2) and the UI-7 audit
pins (A-E) all stay binding through UI-9 — UI-9 introduces
no new motion, no new endpoint, no new shell affordance.
The chunk is verification work over the existing surface.

## What ships in UI-9

```text
tests/test_ui_server_http.py                      NEW.
  - HTTP-level pytest pinning /api/events,
    /api/health, /api/meta projection shapes against
    the bus schema.
  - Each endpoint gets a "shape lock" test: known synthetic
    event written to a temp bus → response JSON matches a
    declared schema (fields present, types correct, no
    drift from UI-1..UI-8).
  - Reduced-motion smoke: Playwright with
    `extra_http_headers={'Sec-CH-Prefers-Reduced-Motion':
    'reduce'}` OR `emulate_media(reduced_motion='reduce')`
    visits each UI-N capture URL and asserts no JS error
    in console + the empty-state hero is visible without
    layout shift.

scripts/ui_lighthouse.py                          NEW.
  - Lighthouse CLI runner. Spins up the server, runs
    `lighthouse http://127.0.0.1:8787/ --output=json` for
    Performance / Accessibility / Best Practices / SEO,
    parses the report, asserts thresholds.
  - Failure mode: print the failing audit IDs + their
    impact so the operator knows which audit failed
    without re-running Lighthouse manually.
  - Writes a JSON report under docs/ui/lighthouse/<date>.json
    so the PR commits the baseline.

docs/ui/lighthouse/                               NEW.
  - <date>.json — full Lighthouse report.
  - README.md — threshold contract + how to re-run + the
    SEO 90 bar rationale.

docs/ui/screenshots/UI-9-tests/                   NEW.
  - PNGs for the reduced-motion smoke pass (each UI-N
    capture URL repeated under reduced-motion media query
    so the auditor can compare against the original).
  - README.md walking the test surface and the
    pytest / Lighthouse contracts.

docs/memory/current-state.md  (extension)
  - UI-9 marked open + the test surface / Lighthouse
    baseline summarised in the system status section.

(no production-code changes are expected; UI-9 is
verification-only)
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-9 introduces no new endpoint, no
  bus mutation.
- Frozen contracts: every projection from UI-1..UI-8 is
  CONTRACT post-UI-9.
- Reduced motion: clamping rules from UI-2 / UI-7 / UI-8
  honoured.
- Lighthouse thresholds: 95 / 95 / 95 / 90.
- No new runtime dependency. Lighthouse runs from the
  Node.js CLI (operator-installed); pytest stays stdlib +
  Playwright.
```

## Open questions to resolve while planning

```text
1. Lighthouse PWA category — installable + service worker
   audits depend on HTTPS. The local dev server is HTTP.
   Lean: skip the PWA category in CI and document the
   manual verification path (load via a local HTTPS proxy
   or via the operator's deployed surface). This stays
   consistent with the manual SW verification UI-8 already
   ships.

2. Performance threshold — 95 is high for a stdlib
   ThreadingHTTPServer with no compression / caching
   headers. Lean: enable gzip in the static asset handler
   for text/css and text/html (not images / fonts / JSON);
   this is a 1-line server change but it's the only
   production-code touch the chunk would carry. Confirm
   with operator before implementing.

3. Accessibility colour-contrast — UI-2 documented ratios
   on --bg-0; --bg-1 panels (header / footer / drawer /
   live-map) need their own contrast confirmation. Lean:
   add a contrast-pair table to docs/ui/lighthouse/
   README.md derived from the actual rendered colours,
   not just the token values.

4. Reduced-motion smoke — assert "no layout shift" via
   CLS measurement OR via comparing screenshot pixel
   diff between motion / no-motion captures. Lean: pixel
   diff at the empty-state hero (the only motion-bearing
   element on the empty surface) and skip the rest as
   covered by the static-PNG audit pattern.

5. Test split — keep test_ui_server.py for the unit-level
   _crow_state / _flight_route precedence + the new
   test_ui_server_http.py for the HTTP-level shape locks?
   Lean: yes, the file split mirrors the conceptual split
   between projection unit tests and contract tests.
```

## Audit cadence reminder

```text
1. PNGs for each reduced-motion capture under
   docs/ui/screenshots/UI-9-tests/.
2. JSON Lighthouse report committed under
   docs/ui/lighthouse/.
3. README walking the test surface + threshold rationale.
4. The diff itself.
5. Audit prompt for Codex out-of-band via ChatGPT.
6. Editorial check: pin "no new motion / chrome / projection
   in UI-9" — verification-only chunk.
7. Test surface check: HTTP-level shape locks land in the
   same PR as the projection contract they pin.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §6 (UI-9 roadmap entry) +
   §10 (Definition of "done" for the UI MVP).
2. docs/ui/screenshots/UI-8-pwa/README.md — the precedent
   for bump rule + manual verification structure.
3. tests/test_ui_server.py — the unit-level pattern UI-9
   builds on.
4. src/karasu/ui/server.py — the projection surface UI-9
   pins.
5. docs/event-schema.md — the bus schema the projection
   shapes derive from.
```

## Chunk size estimate

```text
Code:       ~150 LOC (test_ui_server_http.py + scripts/
            ui_lighthouse.py + optional gzip-on-text
            server line)
Assets:     reduced-motion PNGs (4-6) + 1 Lighthouse JSON
Docs:       ~120 LOC (lighthouse README + screenshots
            README + memory closeout)
Tests:      shape locks for /api/events, /api/health,
            /api/meta + reduced-motion smoke
Total:      under the 400 LOC budget.
```

## Do NOT do yet

```text
- Do NOT add a new endpoint, projection, bus event type,
  or shell affordance. UI-9 is verification.
- Do NOT lower the Lighthouse thresholds without operator
  sign-off documented in the lighthouse README.
- Do NOT skip the reduced-motion smoke. Pin from UI-2.
- Do NOT introduce write paths to the bus.
- Do NOT tag @codex review.
- Do NOT introduce a build step. Lighthouse runs from
  the Node CLI separately.
```

## Anchor for the previous sessions

- **UI-8 (PWA shell + offline page) PR open**
  (`feat/ui-8-pwa`, stacked on `feat/ui-7-detail`). Web
  App Manifest + vanilla service worker (FIRST-BRANCH
  `/api/*` network-only, then navigate fallback to
  offline.html, then static cache-first — Codex P1) +
  offline.html with last-known bus_path from
  localStorage (em-dash placeholder when empty — Codex
  P1) + `.crow.offline` posture (`rotate(4deg) + opacity
  0.7`, `animation: none`, signal-lost not injured —
  Codex P2). Manifest hex matches tokens.css exactly
  (`#0a0a0b` / `#131316` — Codex P2). 4 PNGs, NO .webm
  (first chunk after UI-5 to legitimately skip
  recording — Codex P2). `Service-Worker-Allowed: /`
  header on `/assets/sw.js` so the SW scopes to root.
  PWA icons (192 + 512) generated from crow.svg via
  Playwright rasteriser (no new runtime dep).
- **UI-7 (Detail panel)** PR open. 6 PNGs + .webm 336
  KB. Read-only drawer + 5-class JSON highlighter.
- **UI-6 (Live Map + crow flight)** PR open. APPROVED-
  with-observations + P2 follow-up. 8 PNGs + .webm 242
  KB.
- UI-5 merged 2026-05-04 via PR #74.
- UI-4 merged 2026-05-03 via PR #72.
- UI-3 merged 2026-05-03 via PR #70.
- 421/422 pytest on Windows local. The same single
  preexisting failure
  (`test_valid_asset_under_static_dir_is_served`,
  Windows CRLF) remains; CI Linux green.
- Karasu HEAD post-merge: TBD (UI-6 + UI-7 + UI-8 PRs
  stacked, awaiting audit + merge).
