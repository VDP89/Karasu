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

**→ Sub-frictions 1 & 2 resolved 2026-05-16 by branch
`docs/vapid-bootstrap-consolidation`.**

- `docs/pwa-install.md` gained a §3.0 "Prerequisite — VAPID
  provisioning" sub-section before §3.1, explaining that
  `karasu watch` (not `karasu ui`) is what bootstraps the
  keypair on first start. A troubleshooting bullet in §5
  surfaces the exact modal text ("VAPID keys not
  provisioned") and points back to §3.0. Operators reading
  only the UI-14 walkthrough now find the bootstrap step
  inline.
- `docs/deploy-runbook.md` gained a §1.6 "Provision VAPID
  push keys" between the listener start (§1.5) and the
  mkcert dev flow (§2). Covers first-time provisioning,
  service supervisor placement, `push.contact_email` for
  deployed posture (so the JWT `mailto:` claim is not the
  invalid-TLD default), rotation discipline, and a cross-
  reference to the §6 NTFS ACL posture for `karasu-push.json`.

**Sub-friction 3 (modal does not surface CLI command) →
deferred to a separate UX PR.** The fix is a UI-12b modal
copy change: when `vapid_provisioned == False`, show
`karasu watch` as a runnable hint instead of (or alongside)
the doc pointer. Out of scope for this docs PR — touches
UI-12b code + brief amendment + test, not pure docs.

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

**→ Resolved 2026-05-16 by branch
`fix/ui-14-manifest-id-slash`.** Manifest gained
`"id": "/"` (added at the top of the body); brief §3-A
first SEALED block extended to include `id` with a
reasoning bullet citing this finding; new
`test_manifest_id_sealed` in `tests/test_ui_manifest.py`
under a Layer 2.5 grouping pins the value. The fix
unblocks path C: a deploy origin change now preserves
App ID identity, so the operator's pre-deploy install
will migrate cleanly rather than orphan.

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

**→ Resolved 2026-05-16 by branch
`fix/ui-13-origin-matches-dev-permissive`.**

Root cause: NONE of the three working hypotheses. Real
cause was `origin_matches` in `_auth.py:616` rejecting
browser POSTs in dev posture. Diagnosis sequence:

1. Reset credentials with a known password +
   `verify_password` test → `True`. Hypothesis 2 (password
   mismatch) ruled out.
2. No `karasu ui` processes running, port 8787 free.
   Hypothesis 3 (zombie process) ruled out.
3. Browser login → "could not sign in" chip with no log
   line on the server. That absence was diagnostic on its
   own — `BaseHTTPRequestHandler` always logs requests, so
   the POST never reached the server in those attempts
   (likely a stale rendered chip from a previous attempt;
   the actual subsequent attempts did reach).
4. `curl -X POST /auth/login` with `password=wrong` →
   `HTTP 401 {"error":"could not sign in"}` + log line
   `login failed (ip=!unknown:127.0.0.1)`. Endpoint works.
5. Chrome DevTools Network on a real browser submit →
   `POST /auth/login` returned `HTTP 403`. Initiator
   chain showed both `index:96` (form fetch) and
   `sw.js:272` (SW passthrough). The SW was not caching;
   the 403 came from the server.

Code path: `_handle_login_post` (server.py:1627) →
`origin_matches`. With empty `expected_origins` and a
browser-sent `Origin: http://127.0.0.1:8787` header, the
function short-circuited on `request_origin in ()` →
`False` → 403. The dev fallback (`return not deployed`)
only fired when BOTH Origin and Referer were absent. Curl
worked because it doesn't send Origin by default; browsers
always do (same-origin POSTs included). Hypothesis 1 (rate
limit) was structurally impossible because
`LoginRateLimit.check` bypasses loopback IPs — the request
never reached the rate-limit check.

Fix: `origin_matches` short-circuits to `True` when
`deployed=False AND expected_origins=()`. Brief §3-F
amended to seal the new dev-permissive semantics. Tests:
4 new cases in `test_auth_session.py` covering the bug
shape, the Referer-only variant, the strict-when-
configured invariant, and the deployed-always-strict
invariant.

The JS form handler appears to surface a generic "could
not sign in" chip for any 4xx, which is why a 403 looked
identical to a 401 to the operator and biased hypothesis
ordering toward credentials/rate-limit instead of origin.
Hygiene PR territory: differentiate the chip text by
status code so a 403 doesn't masquerade as a credentials
problem. Out of scope for this fix. → **Resolved by PR #122
(`fix/ui-13-login-chip-status-discrimination`).**

**Side observation (separate PR territory):** the server
log shows `login failed (ip=!unknown:127.0.0.1)`. The
`!unknown:` prefix is a sentinel from `_ip_for_rate_limit`
when `derive_client_ip` returns `None`. That branch should
not fire for a direct loopback peer with no forwarded
chain; suggests the §3-G three-layer trusted-IP derivation
has a dev-posture edge case worth auditing. → **Resolved
by PR #121 (`fix/ui-13-derive-client-ip-trusted-loopback`).**

## Sprint items closed 2026-05-16 (operator decisions captured)

All five sprint items below were addressed in a single
session driven by the operator. Each landed as its own
focused PR; this section is the audit trail.

1. **Finding #5 (P1 pre-deploy)** → **PR #117** added
   `"id": "/"` to manifest.json + §3-A amendment + test
   pin. Path C VPS deploy now preserves App ID identity
   across origin changes.
2. ~~**Capture the auth login bug log**~~ → **PR #116**.
   Root cause was NONE of the three working hypotheses
   (rate-limit, password mismatch, zombie process). Real
   cause: `origin_matches` rejected browser POSTs in dev
   posture because the dev fallback only handled
   absent-Origin, but browsers always send Origin on POST.
3. **Finding #3 sub-frictions 1 & 2 (VAPID docs gap)** →
   **PR #118**. `docs/pwa-install.md` gained §3.0
   prerequisite + `docs/deploy-runbook.md` gained §1.6
   provision step.
4. **Finding #2** → **PR #119** (operator picked path 1:
   drop "UI" suffix). HTML `<title>` now matches manifest
   `name` at "Karasu"; new `test_index_html_title_matches_manifest_name`
   pins the cross-surface alignment.
   **Finding #4** → **deferred per original dogfood
   decision** ("Defer until the shell has visuals worth
   previewing"). Honoured.
5. **Hygiene follow-ups from the 2026-05-16 diagnosis**:
   (a) login chip text per status code (403 ≠ 401) →
   **PR #122** (`fix/ui-13-login-chip-status-discrimination`).
   The login JS now renders the server's canonical
   `{"error":...}` phrase per status; the §3-G online-
   guessing invariant for 401 is preserved verbatim.
   (b) `derive_client_ip` dev-posture edge → **PR #121**
   (`fix/ui-13-derive-client-ip-trusted-loopback`). The
   primitive's contract is unchanged; the wrapper
   `_ip_for_rate_limit` is now posture-aware and returns
   the peer verbatim in dev so the loopback bypass at
   LoginRateLimit.check fires for direct dev iteration.
   (c) Finding #3 sub-friction 3 (modal does not surface
   CLI command) → **PR #123**
   (`fix/ui-12b-push-modal-vapid-cli-hint`). The push
   modal's VAPID-null foot copy now reads
   "Run `karasu watch` in a terminal once to bootstrap"
   so the operator inside the standalone PWA window has
   the runnable hint inline.

**Adjacent housekeeping (same session):** the repo was
renamed from `VDP89/Karasu-` (typo) to `VDP89/Karasu` on
2026-05-16. **PR #120** updated all in-repo references
(tests, scripts, docs) to the new name; memory session
logs were intentionally NOT touched (frozen history).

**Path C VPS deploy is now unblocked at the code surface.**
The remaining gate is operational: domain registration +
VPS provisioning + caddy/Let's Encrypt setup. See
`docs/deploy-runbook.md` for the canonical bring-up.

## Update protocol

Add new findings inline as they surface in subsequent
dogfood sessions. Once a finding matures into a chunk-level
brief or hygiene PR, leave a `→ resolved by PR #NN` line
under it instead of removing it — the log is a historical
record, not a TODO list. Closed-out findings stay for
future operator audit trace.
