# Phase 4 dogfood log

> Empirical friction notes from real-use of Karasu after
> UI-13 + UI-14 land. This log is captura de materia prima,
> not a brief. Findings get triaged here; once they mature
> into actionable scope they leave the log as a chunk-level
> brief or a hygiene PR.
>
> Started 2026-05-09 by Victor. Setup: Karasu running on
> Windows desktop via `python -m karasu ui --no-auth`,
> dogfood window installed via Chrome footer
> `Install: available` click. PWA standalone window persists
> in launcher under `Karasu UI`.

## Validation runtime — UI-14 against Chrome + Windows

The 2026-05-09 session validated UI-14 contracts in real
runtime, not headless tests:

- **Manifest body §3-A SEALED** parsed correct by Chrome
  (Identity / Presentation panes in DevTools Application
  match the 5 sealed props: name + short_name `Karasu`,
  start_url + scope `/`, display `standalone`, orientation
  `any`, theme + background `#0a0a0b`, full icons array).
- **Install affordance §3-B end-to-end:** footer slot
  rendered `Install: available` with the × dismiss button
  after Chrome dispatched `beforeinstallprompt`; click on
  the line opened the OS install dialog; confirm transitioned
  the slot to `Install: installed` and Chrome opened a
  standalone window with title bar `Karasu UI` (no address
  bar — `display: standalone` honoured by Windows OS).
- **SW lifecycle §3-F:** install + activate cycles ran
  clean, status `#4098 activated and is running` in the
  Service Workers pane, fetch interception observed via
  Network tab (`Initiator: sw.js:250` for the polling
  `/api/health`, `/api/events`, `/api/agents` requests).
- **`/api/*` network-only ordering** preserved (UI-13 §3-H +
  UI-12b §11.6.4) — every poll request had non-zero network
  time and status 200, no cache hits.
- **Push modal UI-12b sealed shape** rendered with the three
  §3-H title categories (`attention`, `errors`,
  `corrections`) + their sealed editorial copy + accent-
  coloured checkboxes; the VAPID warning surfaced inline
  (Finding #3 below).

## Findings

### Finding #1 (RETRACTED 2026-05-09)

Operator default browser misread on initial screenshot;
Karasu was already running in Chrome. No real friction.

### Finding #2 — `<title>` "Karasu UI" vs manifest name "Karasu"

**Severity:** Cosmetic — Low.

**Surface:** `src/karasu/ui/static/index.html` (the
`<title>` element).

**Symptom:** The PWA standalone window's title bar reads
`Karasu UI`, but the manifest `name` and `short_name` are
both sealed at `Karasu` (§3-A). Inconsistency between the
window chrome (HTML title) and the sealed identity (manifest).

**Decision:** Archivable. Two paths if addressed:

1. Drop the `UI` suffix from `<title>` so both surfaces
   read `Karasu`.
2. Keep the suffix and document the intent (e.g., to
   distinguish from the CLI core).

Brief amendment optional; either path is non-breaking.

**→ Resolved 2026-05-16 by branch
`fix/ui-14-title-unify-with-manifest` (path 1).** Operator
chose unified identity. `src/karasu/ui/static/index.html`
line 8 now reads `<title>Karasu</title>`; the existing
route-wired assertion in `test_ui_server.py` was updated
in lockstep; a new `test_index_html_title_matches_manifest_name`
in `test_ui_manifest.py` (Layer 2 identity grouping)
parses index.html and asserts the title equals
`manifest["name"]` so future drift between the OS window
chrome and the launcher tile gets caught at test time. No
brief amendment needed — the UI-14 brief never sealed
`<title>`. Other static HTML titles (`login.html`,
`design-system.html`, `offline.html`) were already
consistent with the manifest identity convention.

### Finding #3 — VAPID keys not provisioned + docs gap

**Severity:** Operational — Medium.

**Surface:** UI-12c (push delivery pipeline) bootstrap;
`docs/pwa-install.md` + `docs/deploy-runbook.md`
documentation gap.

**Symptom:** Click `Notifications: off` in the PWA shell
opens the UI-12b modal correctly, but the modal flags
*"VAPID keys not provisioned. See docs/local-dogfood.md
for manual setup."* Pressing `Enable notifications` would
fail because no public key is available for subscribe.

**Sub-frictions:**

1. The warning points to `docs/local-dogfood.md`, but the
   operator-facing UI-14 walkthrough `docs/pwa-install.md`
   does NOT mention the VAPID bootstrap step. An operator
   who reads only the new walkthrough hits the warning
   blind.
2. `docs/deploy-runbook.md` (the deploy bring-up doc) does
   NOT cover VAPID provisioning either. A deployed-posture
   operator needs the same bootstrap for push to work.
3. From inside the PWA window the operator does not have a
   terminal handy; the modal points at a doc but does not
   surface the CLI command.

**Decision archivable:** mini-brief for doc consolidation
(`docs/pwa-install.md` and/or `docs/deploy-runbook.md`
extension covering VAPID bootstrap) + optional UX flow
("first-time push opt-in walks the operator through VAPID
generation"). Belongs to UI-12c follow-up territory, not
UI-14.

### Finding #4 — Manifest missing `screenshots[]`

**Severity:** UX cosmetic — Low.

**Surface:** `src/karasu/ui/static/manifest.json`.

**Symptom:** Chrome DevTools Application → Manifest flags:

> *"Richer PWA Install UI won't be available on desktop.
> Please add at least one screenshot with the form_factor
> set to wide."*
>
> *"Richer PWA Install UI won't be available on mobile.
> Please add at least one screenshot for which form_factor
> is not set or set to a value other than wide."*

**Context:** Standard install dialog works (validated end-
to-end above). The richer dialog (with previews of the
running app) requires 1–2 declared screenshots in the
manifest with form_factor + sizes. UI-14 §3-A did NOT
seal `screenshots[]`. Brief amendment needed if pursued.

**Decision:** Defer until the shell has visuals worth
previewing. The empty-state is minimalist; the preview
value is currently low. Revisit when timeline is dense or
the operator has a screen-grab worth showing in the
install pitch.

### Finding #5 — Manifest missing `id: "/"`

**Severity:** Identity drift — **P1 before path C (VPS deploy).**

**Surface:** `src/karasu/ui/static/manifest.json`.

**Symptom:** Chrome DevTools Application → Manifest flags:

> *"id is not specified in the manifest, start_url is
> used instead. To specify an App ID that matches the
> current identity, set the id field to /."*

**Risk:** Without `id`, Chrome derives the App ID from
`start_url` (currently `http://localhost:8787/`). When the
deploy origin changes (e.g., from localhost to
`https://karasu.<host>`), the Computed App ID changes too
and Chrome treats the PWA as a different app — the
operator's install duplicates in the launcher and the
previous install is orphaned.

**Fix:** Add `"id": "/"` to manifest.json. The literal `/`
decouples identity from origin while keeping it inside the
manifest scope. UI-14 §3-A did not seal `id`.

**Decision:** Brief amendment to §3-A + one-line manifest
fix + test pin in `tests/test_ui_manifest.py`. Promote to
P1 if path C VPS deploy is on the sprint horizon.

## Bug — Could not sign in (auth ON path)

**Surface:** `python -m karasu ui` (without `--no-auth`)
plus login form POST.

**Repro:**

1. Bootstrap creds via
   `python -m karasu auth set-credentials --username victor`.
2. Start `python -m karasu ui` (auth enabled, default).
3. Open `http://localhost:8787/` in Chrome.
4. Submit the login form with the same username + password
   used in step 1.

**Observed:** Login form re-renders with the red chip
`Could not sign in.` regardless of how many times the creds
are reset. Browser side (Chrome) re-render is consistent.

**Diagnostic gap:** No server-side log was captured during
the failed attempts on 2026-05-09. The next debug session
MUST capture the `karasu ui` terminal output between
server boot and the login submission rejection. UI-13 §3-D
logs the auth rejection reason explicitly (cred mismatch /
rate limit / origin / CSRF), so a single attempt with
logs visible should localise the cause.

**Working hypotheses (not validated):**

1. Rate limit accumulated from earlier failed attempts; in-
   memory state would clear on server restart.
2. Password mismatch between set-credentials prompt and
   login form (no echo on either side; easy to mistype).
3. Multiple `karasu ui` processes contending for port 8787
   without surfaced collision; the live process serves
   creds different from the on-disk file the operator just
   wrote.

**Workaround used 2026-05-09:** Started with `--no-auth` to
keep dogfood moving. UI-14 validation completed against the
unauthenticated shell; the deployed-auth path remains
untested in real runtime.

**Severity:** **Blocker for path C VPS deploy** (deploy
posture cannot use `--no-auth` — UI-13 §3-D startup refuses
the combination). Medium for localhost dogfood
(workaroundable via `--no-auth`).

## Outstanding sprint items (operator decision required)

1. **Address Finding #5** before path C deploy — one-line
   manifest fix + test pin + brief amendment to §3-A.
2. **Capture the auth login bug log** — re-run with the
   `karasu ui` terminal in foreground and attempt one
   login; paste the server output to debug.
3. **Address Finding #3 docs gap** — consolidate VAPID
   bootstrap mention into `docs/pwa-install.md` or
   `docs/deploy-runbook.md` (operator preference). Optional
   auto-gen on startup is a separate decision.
4. **Decide on Findings #2 and #4** — both archivable;
   neither blocks deploy or daily use.

## Update protocol

Add new findings inline as they surface in subsequent
dogfood sessions. Once a finding matures into a chunk-level
brief or hygiene PR, leave a `→ resolved by PR #NN` line
under it instead of removing it — the log is a historical
record, not a TODO list. Closed-out findings stay for
future operator audit trace.
