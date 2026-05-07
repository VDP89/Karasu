# Karasu Phase 4 — Deployed Operator Surface (macro brief)

> Doc-only seal of the Phase 4 frame. Written deliberately
> SHORT and VINCULANT — roadmap + threat model + first
> chunk seal, no tractatus. Each child chunk (UI-13 / UI-14
> / UI-15+) earns its own chunk-level brief on top.
>
> Audited and merged BEFORE any UI-13 code branch opens.
>
> Parallel to:
> - `ui-0-design-brief.md`   (UI-1..UI-9 read-only MVP)
> - `ui-10-design-brief.md`  (UI-10 scar revoke)
> - `ui-11-design-brief.md`  (UI-11 trust adjust)
> - `ui-12-design-brief.md`  (UI-12 push notifications family)
> - `ui-12c-design-brief.md` (UI-12c server-side push emit)
>
> The UI-0 macro brief opened the UI-1..UI-12c family with a
> sealed editorial frame. This brief plays the same role for
> the UI-13..UI-15+ family.
>
> **STATUS:** APPROVED-with-observations — mergeable.
> Operator sign-off complete (Victor, 2026-05-07:
> "avanzar nomas"; every §3 (A-F) + §3.5 + §10 marker
> flipped to [CONFIRMED 2026-05-07]). Codex audit closed
> at round 2 of 5: round 1 CHANGES-REQUIRED (4 P1 + 2 P2,
> no P0 — all six closed in-branch); round 2
> APPROVED-with-observations (2 P2 wording cleanups
> applied in-branch). Loop budget: 2/5.

## 0 · Why this brief exists

Phase 1-3 sealed Karasu as a **localhost prototype**:

```text
Phase 1A/1B/1C — Local daemon + Telegram                ✔ CLOSED
Phase 2        — Git-aware + A2A discovery              ✔ CLOSED
Phase 3        — PWA + Advanced (UI-0..UI-12c)          ✔ CLOSED
                  Exit criteria CLOSED 2026-05-07 by UI-12c.
                  Telegram is no longer the only push channel;
                  the PWA push delivery surface (footer + modal +
                  VAPID-signed RFC 8291 aes128gcm POSTs) is the
                  operator-facing notification path.
```

Phase 4 turns Karasu from a localhost prototype into Victor's
**first real deployed operator surface** — reachable from
Chrome / mobile over HTTPS, authenticated, installable as a
web app, and safe enough for daily dogfood.

Phase 4 touches decisions that are **expensive to reverse**:
TLS termination, trust boundary, auth / session model,
secret handling, CSRF posture, deployment topology. A
chunk-first approach without an architectural seal would let
the first chunk smuggle deployment assumptions that
condition everything that follows. A macro brief now is the
cheapest insurance against that drift.

This brief is intentionally short. It seals the FRAME (what
Phase 4 is, what it is NOT, what the first chunk earns) and
defers IMPLEMENTATION DETAIL to the chunk-level briefs that
follow.

## 1 · Phase 4 product frame (binding)

> Phase 4 turns Karasu from a localhost prototype into
> Victor's first real deployed operator surface: reachable
> from Chrome / mobile over HTTPS, authenticated, installable
> as a web app, and safe enough for daily dogfood.
> Multi-operator, HA, A2A peer topology, and app-store native
> packaging are future chunks unless the first deployment
> proves they are needed.

This is the editorial line. Every Phase 4 chunk MUST be
defensible against this sentence. If a chunk does not move
the needle on "Victor opens Karasu from Chrome / mobile,
authenticates, controls the system from the web, receives
push, uses it day-to-day", it earns a separate brief or
defers to Phase 5.

## 2 · Visual references (anchors held)

UI-12c was the last chunk in the localhost-prototype era.
Phase 4 inherits its visual language verbatim:

```text
- Editorial silence by default. The PWA shell is the surface;
  notifications are the operator's deliberate exception to
  silence (UI-12 §3.5 carry-forward).
- Crow as state signal. Idle / processing / waiting / error
  precedence held (UI-5 + audit pin "el crow puede tener
  vida; la superficie no puede perder calma").
- Footer is the affordance shelf. Notifications, version,
  bus path, last event time — no toolbar, no settings panel,
  no install banner.
- Singular voice. Fresh push REPLACES pending notifications
  (tag = "karasu" singular per UI-12 §3-H).
```

Phase 4 adds NO new visual primitives. UI-13 may add a login
screen (its own chunk-level brief specifies the shape) and
UI-14 may add an install prompt posture (chunk brief
specifies) — but the design system + crow + footer
primitives are frozen.

## 3 · Confirmed decisions (operator sign-off complete 2026-05-07)

### A) Deployment shape — single instance, self-hosted

PROPOSAL — Phase 4 ships against ONE deployment shape:

```text
- Self-hosted single instance.
- VPS or operator-controlled machine.
- TLS terminated on the same instance (no separate
  reverse-proxy tier required, but compatible with one if
  the operator already runs caddy / nginx in front).
- Single FILESYSTEM (the cross-process file lock from
  UI-12c §3-G is sufficient because karasu ui + karasu
  watch + karasu serve all live on the same box).
```

Multi-instance HA (load-balanced karasu watch + shared push
store across hosts) is **explicitly DEFERRED** to Phase 4.x
or later.

The corollary: the UI-12c §3-G file lock REMAINS the single
writer-concurrency primitive in scope. No NFS-safe primitive
in Phase 4. If dogfood proves the single instance is
insufficient, a Phase 4.x brief earns the multi-host
contract.

[CONFIRMED 2026-05-07]

### B) Auth model — single-operator with credentials

PROPOSAL — Phase 4 auth is intentionally minimal:

```text
- Single operator (Victor).
- Credentials = (username, password) OR (operator key
  passphrase). The chunk-level UI-13 brief picks ONE +
  documents the threat model.
- Session = signed cookie OR DB-backed session token. The
  chunk-level UI-13 brief picks ONE + justifies.
- No registration flow (ops-side bootstrap only).
- No password reset flow (ops-side reset only — operator
  edits the credentials file + restarts).
- No OAuth / OIDC / federated identity.
- No multi-operator authorization tiers.
```

The auth shape is a single sentence: **the surface is
locked behind one set of credentials Victor owns; if the
credentials are compromised, the operator rotates them by
editing a file and restarting**. Anything more sophisticated
re-opens the brief.

Multi-operator collaboration / per-user trust gradient
filtering / operator-scoped audit log is **explicitly
DEFERRED** to Phase 4.y or later.

[CONFIRMED 2026-05-07]

### C) Threat model (binding)

PROPOSAL — Phase 4 trust boundary moves from "localhost is
inherently trusted" to "the network is not". The implications:

```text
1. EVERY route or transport that reads or mutates operator
   state — bus, scars, trust gradient, push subscriptions,
   auth/session metadata, dispatch state, agent metadata,
   or any future operator-private surface — MUST require
   an authenticated session in the deployed posture. This
   pin is PATH-INDEPENDENT: applies to /api/*, any future
   SSE / WebSocket transport, debug or diagnostic
   surfaces, static JSON dumps that project operator
   state, and any helper route a chunk introduces. The
   UI-12a /api/push read shape is no longer safe to leak
   to anonymous callers — push subscription counts +
   VAPID public keys are operator-private metadata on a
   deployed surface (Codex round 1 P1 binding,
   2026-05-07).

2. Unauthenticated `/` MUST render ONLY the login surface.
   Inert assets strictly required to render the login
   screen (login.css, login fonts that aren't already
   under /assets/fonts/, favicon) MAY be anonymous; every
   other path — /api/*, the design-system page, debug or
   diagnostic surfaces, the PWA shell with bus-capable
   JS, sw.js when registered under an authenticated
   scope, and any future static JSON that projects
   operator state — MUST be auth-gated in the deployed
   posture. The web app manifest itself may remain
   anonymous for browser discovery (the install posture
   needs it pre-auth for the PWA prompt to fire); UI-13
   chunk brief specifies sw.js / manifest reachability
   explicitly, including SW scope discipline so a
   registered SW behind login does not become a leak
   vector. (Codex round 1 P1 binding, 2026-05-07.)

3. CSRF / origin protection MUST cover every mutating
   route on every transport (POST / PUT / DELETE on
   /api/*, plus any future mutating SSE / WebSocket
   message). Candidates (double-submit cookie, signed
   header token, SameSite=Strict + origin check) are
   chunk-level decisions. The macro pin is "no
   non-idempotent route on any transport is reachable
   without a per-session CSRF guard or equivalent
   origin assertion".

4. Online-guessing protection. Login failure responses
   MUST be generic — no username / account enumeration
   distinction, no "user exists vs password wrong"
   information leak via response shape OR timing.
   Rate-limit / exponential backoff on failed auth
   attempts (chunk brief picks the mechanism + per-IP /
   per-credentials granularity); the macro pin is "the
   surface MUST NOT be a public oracle for credential
   guessing". Brute-force resistance lives at this layer
   AND at the password-hash layer (scrypt cost
   parameters; chunk brief specifies). (Codex round 1
   P1 binding, 2026-05-07.)

5. Cookie hardening. Session cookies MUST set HttpOnly,
   Secure (when TLS is on; chunk brief documents the
   localhost-dev path for cert-less testing), and
   SameSite=Strict (or Lax if a deliberate cross-site
   redirect flow demands it; chunk brief justifies).
   NO session material in localStorage /
   sessionStorage / DOM-readable JS — the session
   ID lives in the cookie only. (Codex round 1 P1
   binding, 2026-05-07.)

6. Session lifecycle. Sessions expire after a bounded
   period (chunk brief picks the duration; 7-30 day
   range is reasonable for daily-dogfood single
   operator). Session rotation on credential rotation
   AND on explicit logout. Ops-side credential rotation
   (operator edits the credentials file + restarts) MUST
   invalidate ALL existing sessions — restart-clears the
   in-memory session table for signed-cookie schemes,
   or wipes the DB-backed table for that scheme. (Codex
   round 1 P1 binding, 2026-05-07.)

7. Credential / session material in logs. NEVER.
   Carries forward pin §11.6.16 raw-endpoint privacy
   discipline verbatim: passwords, password hashes,
   session tokens, session IDs, signing secrets, TLS
   private keys, VAPID private keys — none of these
   materialise in log lines, bus events, error response
   bodies, HTTP response headers (other than the
   intended Set-Cookie), or debug surfaces. Failed-auth
   log lines MAY carry the request IP + a generic
   "auth failed" marker; nothing more. Exception
   handlers around auth code follow the
   `endpoint_hash + type(exc).__name__` pattern UI-12c
   round 1 P1 sealed for transport failures. (Codex
   round 1 P1 binding, 2026-05-07.)

8. Push subscriptions remain operator-private secret
   material (pin §11.6.16 carry-forward from UI-12c).
   The raw endpoint MUST NOT leak via auth-failure
   error bodies, session-debug surfaces, or any new
   diagnostic page Phase 4 introduces.

9. The trust gradient (`autonomous` adapters, trust>=2)
   keeps its existing semantics. Phase 4 does NOT add
   per-operator trust scoping; trust is system-wide.

10. Secret handling — complete inventory binding for
    Phase 4 (Codex round 1 P2 binding, 2026-05-07):
      * UI-12c VAPID private key (existing, in
        karasu-push.json mode 0600).
      * Phase 4 auth credentials / verifier (NEW;
        karasu-auth.json mode 0600).
      * Session signing secret (NEW; same file or a
        dedicated karasu-session-key — chunk brief
        decides).
      * TLS private key WHEN karasu owns TLS
        termination (NEW; chunk brief specifies path;
        mode 0600).
      * Any future operator API tokens.
    All secrets live in mode-0600 files (POSIX; Windows
    advisory-mode equivalent per UI-12b loud-stderr
    warning shape). NEVER in environment variables
    visible to subprocesses, NEVER in command-line
    args, NEVER in logs, NEVER in HTTP response bodies.
    Test fixtures use sentinel patterns; production-side
    defaults are absent — the operator MUST explicitly
    seed. The chunk-level UI-13 brief specifies the
    exact file formats + provisioning ergonomics.

11. The bus + scar log + dispatch state remain
    operator-private. They were already not exposed
    anonymously in Phase 3 (UI-12a /api/events requires
    no auth today because the surface was
    localhost-only; Phase 4 closes that door under
    item 1).
```

The single-instance + single-operator deployment shape
collapses many threat model variables. This brief does NOT
attempt a full deployed-software threat model; it pins the
eleven items above as binding for every Phase 4 chunk.

[CONFIRMED 2026-05-07]

### D) Roadmap (binding sequence)

PROPOSAL — three chunks in this order:

```text
UI-13 — Remote operator surface (FIRST CHUNK)
  Earns the first remote frontier:
    * HTTPS termination on the karasu ui server (or
      compatible with caddy / nginx termination).
    * Single-operator credentials + session.
    * CSRF guard on all non-idempotent /api/* routes.
    * Auth gating per §3-C item 1 (transport-agnostic:
      every route or transport that reads / mutates
      operator state requires session). Only inert login
      assets + manifest may remain anonymous; UI-13
      decides exact reachability per §3-C item 2,
      including SW scope discipline.
    * Secret handling per §3-C item 10 (full inventory:
      VAPID + auth + session + TLS + future tokens, all
      mode-0600).
    * Login screen UX (single primitive added to the
      design system; no other visual delta).
    * Logout flow.
    * "karasu deploy" CLI helper (or equivalent) so the
      operator can flip the surface from localhost-dev
      to deployed-dogfood without editing N config files.
  Estimated scope: ~1500-2500 LOC including tests + docs.

UI-14 — PWA installable
  Earns the "app-like" experience:
    * Web app manifest with proper icons / theme color /
      orientation / display mode.
    * Install prompt posture (deliberate, not nagging —
      pin "no install banners" from UI-8 audit pin #5
      carries forward; the install affordance is in the
      footer or a deliberate first-visit hint).
    * Mobile layout passes (the existing CSS already
      holds at narrow viewports per UI-4 / UI-7
      breakpoints; UI-14 audits + tightens).
    * iOS / Safari + Android / Chrome push compatibility
      checks (UI-12c shipped against desktop Chrome
      headless; mobile push has known UA quirks).
    * Service worker update strategy on a deployed
      surface (the current "skipWaiting + clients.claim"
      from UI-8 may need adjustment when the operator's
      browser holds long-running tabs).
  Estimated scope: ~800-1500 LOC including tests + docs.

UI-15+ — Native packaging (CONDITIONAL)
  Only earned IF dogfood after UI-13 + UI-14 proves the
  PWA cannot do something the operator needs (the typical
  candidates are: iOS background push reliability,
  Android background sync, App Store distribution to
  non-Victor operators if Phase 4.y multi-operator ever
  lands).
  Default disposition: NOT in Phase 4 scope. The chunk
  brief is a deferral note unless dogfood opens it.
```

The sequence is binding. UI-13 ships first because the
remote frontier is the load-bearing decision; UI-14 layers
"app-like polish" on top of an already-secure surface.
Inverting the order (PWA first, auth second) would let the
operator install a Karasu app over plain HTTP and then
break the install state when the auth boundary lands.

[CONFIRMED 2026-05-07]

### E) "Done" definition for Phase 4

PROPOSAL — Phase 4 closes when:

```text
1. Victor can open Karasu from Chrome (desktop) or his
   phone over HTTPS at a public hostname.
2. He authenticates with the single-operator credentials.
3. The surface controls the system end-to-end:
     * the bus is observable (existing /api/events shape
       behind auth);
     * scars can be revoked + trust adjusted (UI-10 +
       UI-11 surfaces, now auth-gated);
     * push notifications arrive on his device (UI-12c
       pipeline still works — the dispatcher's outbound
       VAPID flow is unchanged by Phase 4 deployment);
     * /scar from Telegram still loops back through the
       controller (UI-13 does not break the Telegram
       interface — it adds the web one alongside).
4. The PWA installs on at least Chrome desktop + one
   mobile browser (Safari iOS or Chrome Android), with
   working push.
5. The deployment is documented end-to-end in a Phase 4
   "ops runbook" (likely under
   `docs/local-dogfood.md` or a new
   `docs/deploy-runbook.md`) so a future operator can
   reproduce the bring-up from scratch.
```

UI-15+ native packaging is OUT of the Phase 4 close
criteria. Phase 4 is "real platform, web-first"; native is
the polish frontier.

[CONFIRMED 2026-05-07]

### F) Loop budget per chunk

PROPOSAL — Phase 4 inherits the established 5-round loop
budget per Codex audit (UI-9 audit pin #1). The macro brief
itself takes its own audit cycle:

```text
- Macro brief (THIS doc):     loop budget 5; round 1
                              expected to land 2-4 P0/P1
                              against the threat model
                              and roadmap.
- Each chunk-level brief:     loop budget 5.
- Each chunk-level code PR:   loop budget 5.
```

Track loop budget per chunk in the chunk brief's §12
status block (mirror of UI-12c § status pattern).

[CONFIRMED 2026-05-07]

## 3.5 · Operator pin (binding)

PROPOSAL:

```text
Phase 4 must read as Karasu *opening up to Victor*, not
Karasu *opening up to the internet*. Three felt properties:

  1. The surface is locked by default. Anonymous visitors
     get a login screen, not an empty PWA shell with hooks
     into the bus. The "first second" of looking at a
     deployed Karasu must read as "this is mine and you
     are not in".

  2. The operator's daily flow does not regress. Login
     once, stay in. The session UX must be at least as
     boring as logging into Gmail; if the operator hits a
     re-auth prompt mid-day for no reason, the chunk-level
     brief got the session contract wrong.

  3. Failure is loud, not silent. A misconfigured TLS
     cert, an expired session, a CSRF guard rejecting a
     legitimate POST — all surface as visible errors with
     operator-actionable text, not silent 500s. Karasu's
     editorial line is "editorial silence by default" for
     PUSH; for AUTH it is "silence is suspicious".
```

[CONFIRMED 2026-05-07]

## 4 · Tech stack (delta vs Phase 1-3)

Phase 1-3 stack still holds. Phase 4 anticipates:

```text
+ A TLS termination story. Either:
    (a) karasu ui terminates TLS itself (stdlib ssl module
        + cert files; no new runtime dep — chunk brief
        decides feasibility), OR
    (b) karasu ui stays HTTP-only and the operator runs
        caddy / nginx in front. The chunk brief picks one
        OR documents both as supported postures.

+ A password-hashing primitive for the auth credentials.
  Stdlib `hashlib.scrypt` is the leading candidate (no new
  runtime dep). If the chunk brief picks bcrypt or argon2
  it earns a UI-13 §11.6 named scoped exception per the
  UI-12 §11.6.13 precedent.

+ Possibly a JWT library OR signed-cookie helper for the
  session token. Stdlib `hmac` + `secrets` covers a
  signed-cookie scheme without a new dep; PyJWT would be
  the alternative if the chunk brief lands JWT sessions.

+ NO new build step / bundler. UI-0 §4 binding carries
  forward unchanged.

+ NO front-end framework. The login screen + PWA manifest
  ship as plain HTML / CSS / JS, consistent with the
  UI-0..UI-12c surface.

+ The cryptography import scope from UI-12 §11.6.13
  REMAINS the three push_emit files. The default
  password-hashing posture is stdlib `hashlib.scrypt`,
  which does NOT re-open UI-0 §4. The chunk-level UI-13
  brief MAY earn a named scoped extension if it picks
  bcrypt or argon2 instead (those would be runtime
  deps); the same applies to ANY new cryptography-using
  primitive a chunk introduces (JWT signing via PyJWT
  vs stdlib hmac, TLS via a non-stdlib lib, etc.). The
  trigger is the EXACT primitive that needs the dep, not
  Phase 4 generally — each new dep earns its own UI-12
  §11.6.13-style precedent per the "exception does NOT
  generalise" pin.
```

## 5 · Design system (delta vs UI-0..UI-12c)

Phase 4 anticipates exactly two new visual primitives:

```text
- Login screen (UI-13). One primary input (or two —
  username + password), one primary button, one error
  state. The chunk-level brief specifies the shape; the
  macro pin is "no marketing copy, no signup link, no
  password reset link, no third-party auth icons". The
  operator either knows the credentials or doesn't.

- Install prompt posture (UI-14). A footer affordance OR
  a deliberate first-visit hint that does not hijack the
  surface. The chunk-level brief specifies; the macro pin
  is "no install banners" (UI-8 audit pin #5 carries
  forward verbatim).
```

NO toolbar. NO settings panel. NO theme switcher (the
existing dark surface IS the theme). The chunk-level briefs
defend any addition against §3.5 above.

## 6 · Roadmap (chunk index)

```text
UI-13 — Remote operator surface
        Single PR family OR split into UI-13a / UI-13b at
        the chunk-level brief's discretion. Audit cadence
        per the UI-12c §7 pattern.

UI-14 — PWA installable
        Single PR family. Likely smaller than UI-13.

UI-15+ — Native packaging (deferred / conditional)
        Out of Phase 4 scope by default. UI-15 brief is
        written ONLY if dogfood after UI-14 demands it.

Phase 4.x — Multi-instance HA              (deferred)
Phase 4.y — Multi-operator authorization   (deferred)
Phase 4.z — A2A peer push fan-out          (deferred)
```

The deferred items inherit the same brief-before-code
discipline. Each earns its own brief when its time comes.

## 7 · Audit cadence (carries forward from UI-12c §7)

Every Phase 4 PR carries the UI-12c §7 audit obligations
forward:

```text
- PR body documents the brief section it implements.
- Test surface: unit + integration green; existing tests
  green (no regression).
- Visual surface: PNGs + .webm where applicable (UI-13
  login screen + UI-14 install prompt are visual chunks).
- Lighthouse: re-run; thresholds unchanged from UI-9.1
  baseline. Auth-gated routes are excluded from the
  Lighthouse scoring corpus by the chunk brief.
- Operator sign-off marker before code branch opens.
- Codex audit out-of-band; verdict ferried back via
  operator (no @codex review tag, no ChatGPT Codex
  Connector — operator-mediated only per CLAUDE.md
  working agreement).
- Memory sync follow-up PR after each chunk merges
  (mirror of PR #99 / #103 / #106 pattern).
```

## 8 · Frozen contracts (Phase 4 MUST respect)

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.

- The bus event schema (additive only).

- The /api/events / /api/health / /api/meta / /api/scars /
  /api/agents / /api/push projection shapes. Phase 4
  ADDS auth gating ON TOP; the response bodies behind a
  valid session are byte-for-byte the Phase 3 shape.

- The UI-12b POST /api/push/subscribe + /api/push/unsubscribe
  shapes. Phase 4 adds auth gating; the success / error
  matrix is unchanged.

- The UI-12c push_emit pipeline (classifier → rate_limit →
  dispatcher). Phase 4 does NOT change the dispatch
  contract; it only changes WHO can subscribe.

- The cryptography import scope (3 files in push_emit/).
  Phase 4 may EXTEND it for password hashing IFF the
  chunk-level brief earns the named scoped extension; the
  default is no expansion.

- The Lighthouse threshold contract.

- The 126 binding pins inherited (52 base + 6 UI-10 §0.5
  + 12 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6
  + 4 PR #102 round-2 forward-carry + 20 UI-12c §11.6).

- Out-of-band Codex audit (no @codex review tag, no
  ChatGPT Codex Connector — operator-mediated only).
```

## 9 · Out of scope for Phase 4

```text
- Multi-instance HA / load balancing.
- Shared / network filesystem locking (NFS, distributed
  storage).
- A2A peer push fan-out (Karasu instance pushing to
  another Karasu instance).
- Multi-operator authorization, login flows, per-operator
  trust scoping, audit log filtering by operator.
- OAuth / OIDC / federated identity.
- App Store / Google Play distribution.
- Native iOS / Android packaging (UI-15+ conditional;
  default deferred).
- Per-event push opt-in beyond {attention, errors,
  corrections}.
- Scheduled / quiet-hours / DND beyond OS-level.
- Push body content beyond the editorial title.
- VAPID auto-rotation.
- Per-category push debounce env var override
  (KARASU_PUSH_DEBOUNCE_<CATEGORY>_MS).
- Phase 3 hardening F9 / F10 / F11 (parallel ops track;
  may be absorbed into a UI-13 sub-commit if the chunk
  brief argues for it, but NOT a Phase 4 close criterion).
```

## 10 · Open questions (operator sign-off needed)

```text
1. TLS posture.
   PROPOSAL — chunk-level UI-13 brief decides between:
     (a) karasu ui terminates TLS itself (stdlib ssl), OR
     (b) karasu ui stays HTTP and operator runs caddy /
         nginx in front, OR
     (c) supports both with operator-side configuration.
   The macro brief does NOT pre-decide; UI-13 brief
   commits.
   [CONFIRMED 2026-05-07 — deferred to UI-13]

2. Credentials format.
   PROPOSAL — chunk-level UI-13 brief decides between
   (username + password) and (single passphrase). Operator
   intuition says single-passphrase is simpler for one
   user; chunk brief weighs against industry expectations
   when the surface eventually grows.
   [CONFIRMED 2026-05-07 — deferred to UI-13]

3. Session token format.
   PROPOSAL — chunk-level UI-13 brief decides between:
     (a) signed cookie (stdlib hmac + secrets; no DB), OR
     (b) DB-backed session (a tiny JSONL or SQLite table
         keyed by random session id).
   Macro brief does NOT pre-decide.
   [CONFIRMED 2026-05-07 — deferred to UI-13]

4. Login screen visual primitive.
   PROPOSAL — chunk-level UI-13 brief specifies. Macro
   pin: no marketing, no signup link, no third-party auth.
   [CONFIRMED 2026-05-07 — macro pin binding]

5. Phase 3 hardening (F9 / F10 / F11) absorption.
   PROPOSAL — UI-13 chunk brief MAY absorb them as a
   sub-commit if the operator wants to clean the slate
   before Phase 4 ships; otherwise they live as a
   parallel ops track and earn a tiny dedicated PR each.
   [CONFIRMED 2026-05-07 — disposition deferred to UI-13 chunk brief]

6. Native packaging trigger.
   PROPOSAL — UI-15+ is conditional. The macro brief
   commits to NOT writing the UI-15 brief unless dogfood
   after UI-14 surfaces a concrete platform need (iOS
   background push reliability is the leading candidate).
   [CONFIRMED 2026-05-07 — UI-15 deferred until dogfood proves PWA gap]
```

## 11 · §11.6 anticipated pins (Codex audit, pending)

The macro brief earns §11.6 pins from Codex's audit. The
anticipated shape (mirror of UI-12 §11.6 pattern; final
wording lands after Codex's verdict):

```text
1. Phase 4 ships against ONE deployment shape: self-hosted
   single instance. Multi-instance HA / multi-host writer
   concurrency / NFS-safe locking are deferred per §3-A.

2. Phase 4 ships single-operator auth. Multi-operator
   authorization / per-operator trust / OAuth / OIDC /
   federated identity are deferred per §3-B.

3. State privacy is TRANSPORT-AGNOSTIC. Every route or
   transport (REST /api/*, future SSE / WebSocket, debug
   pages, static JSON dumps, helper routes) that reads or
   mutates bus / scars / trust / push / auth-session /
   dispatch / agent / future operator-private state MUST
   require an authenticated session in deployed posture.
   Codex round 1 P1 binding 2026-05-07; supersedes any
   reading of "every /api/* route" as path-bound.

4. Anonymous reachability is narrow: unauthenticated `/`
   renders ONLY the login surface, plus inert assets
   strictly required to render it (login.css, favicon,
   web app manifest). Every other path — /api/*,
   design-system page, debug surfaces, PWA shell with
   bus-capable JS, sw.js — is auth-gated. SW scope
   discipline pinned in UI-13 chunk brief. Codex round
   1 P1 binding 2026-05-07.

5. CSRF / origin protection MUST cover every mutating
   route on every transport (POST/PUT/DELETE on /api/*,
   plus any future mutating SSE / WebSocket message).
   Chunk brief picks the mechanism.

6. Online-guessing protection: generic login failures
   (no enumeration, no timing distinction), rate-limit /
   backoff on failed attempts, scrypt cost parameters at
   the password-hash layer. Codex round 1 P1 binding
   2026-05-07.

7. Cookie hardening: HttpOnly + Secure + SameSite
   (Strict default; Lax with chunk-brief justification).
   No session material in localStorage / sessionStorage /
   DOM-readable JS. Codex round 1 P1 binding 2026-05-07.

8. Session lifecycle: bounded expiry (chunk brief picks
   duration); rotation on credential rotation +
   explicit logout; ops-side credential rotation
   invalidates ALL existing sessions. Codex round 1 P1
   binding 2026-05-07.

9. Push subscription endpoints REMAIN operator-private
   secret material (pin §11.6.16 of UI-12c carry-forward).
   Auth-failure error bodies + session-debug surfaces
   MUST NOT echo the raw endpoint.

10. Trust gradient stays system-wide (NOT per-operator)
    until Phase 4.y multi-operator ever lands.

11. Secret inventory binding (Codex round 1 P2 binding
    2026-05-07): VAPID private key, auth credentials /
    verifier, session signing secret, TLS private key
    when karasu owns TLS, future operator API tokens.
    All in mode-0600 files. NEVER in env vars / args /
    logs / HTTP response bodies. Credential / session /
    key material in logs is FORBIDDEN per pin
    §11.6.16-style carry-forward.

12. Bus + scar + dispatch state remain operator-private.
    /api/events + every state-projecting transport
    behind auth.

13. The cryptography import scope stays at the three
    push_emit files. Default password-hashing posture is
    stdlib hashlib.scrypt (NO new dep). UI-13 chunk
    brief MAY earn a named scoped extension if it picks
    bcrypt / argon2 / a non-stdlib JWT lib / etc.; the
    trigger is the EXACT primitive needing it, not
    Phase 4 generally. Each extension earns its own
    UI-12 §11.6.13-style precedent.

14. UI-15+ native packaging is conditional. Default
    disposition: deferred until dogfood proves PWA gap.

15. Each Phase 4 chunk earns its own chunk-level brief
    BEFORE code (UI-9 audit pin #1 carry-forward).

16. Each chunk merges WITH a memory-sync follow-up PR
    mirroring PR #99 / #103 / #106.

17. Loop budget 5 rounds per audit cycle (macro brief +
    each chunk brief + each chunk code PR).

18. NO @codex review tag, NO ChatGPT Codex Connector —
    audit stays operator-mediated.

19. The first second of looking at a deployed Karasu MUST
    read as locked-by-default — login screen, not an
    empty shell with bus hooks. §3.5 binding.
```

These are anticipated; final wording lands after Codex's
verdict on this brief. Pins flip from anticipated to
verbatim binding once Codex's audit closes.

## 12 · Status

```text
Brief status:        APPROVED-with-observations + operator
                     sign-off complete. Mergeable. Loop
                     budget: 2 of 5 consumed.
Operator sign-off:   COMPLETE (Victor, 2026-05-07: "avanzar
                     nomas"). Every §3 (A-F) + §3.5 + §10
                     marker flipped to [CONFIRMED 2026-05-07].
                     Operator orientation provided 2026-05-07
                     (Path A macro brief; UI-13 remote
                     operator surface as first chunk; UI-14
                     PWA installable; UI-15+ conditional
                     deferred; single instance + single
                     operator + credentials + session;
                     product frame in §1). The macro brief
                     codifies the orientation into vinculant
                     form. §10 sub-questions deferred to the
                     UI-13 chunk-level brief by operator
                     direction.
Codex audit:         Round 1 CHANGES-REQUIRED (4 P1 + 2 P2,
                     no P0). All six findings addressed
                     in-branch:
                       P1 §3 header consistency (§3 header
                          "operator sign-off pending" → "complete
                          2026-05-07"; STATUS + §12 already
                          flipped in commit 2a44e83).
                       P1 §3-C item 2 narrowed: anonymous
                          reachability is now ONLY the login
                          surface + inert login assets +
                          web app manifest; all other paths
                          (PWA shell with bus JS, sw.js,
                          design-system, debug, static
                          state JSON) are auth-gated.
                       P1 §3-C items 4-7 added: online-
                          guessing protection, cookie
                          hardening (HttpOnly + Secure +
                          SameSite), session lifecycle
                          (expiry + rotation), credential /
                          session material privacy in logs.
                       P1 §3-C item 1 generalised to
                          transport-agnostic — every route
                          OR transport reading / mutating
                          operator state requires auth in
                          deployed posture (path-independent
                          across REST, SSE, WS, debug,
                          static JSON, helper routes).
                       P2 §3-C item 10 expanded to a
                          complete secret inventory: VAPID
                          private key, auth credentials,
                          session signing secret, TLS
                          private key when karasu owns
                          TLS, future operator API tokens.
                          All mode-0600.
                       P2 §4 cryptography-scope wording
                          rewritten: trigger is the EXACT
                          primitive (password hashing, JWT,
                          TLS-via-non-stdlib, etc.), not
                          Phase 4 generally; default
                          hashlib.scrypt does NOT re-open
                          UI-0 §4.
                     §11.6 anticipated pins re-numbered
                     and expanded from 15 to 19 to absorb
                     the new bindings.

                     Round 2: APPROVED-with-observations
                     (2 P2 wording cleanups). Both
                     applied in-branch:
                       P2 §6 UI-13 roadmap bullet — last
                          broad "static assets remain
                          anonymous" echo removed; rewritten
                          as "only inert login assets +
                          manifest may remain anonymous;
                          UI-13 decides exact reachability
                          per §3-C item 2, including SW
                          scope discipline". Secret
                          handling reference updated from
                          item 6 to item 10 (post-renumber).
                       P2 §3.5 header "Operator pin
                          (binding when sign-off lands)" →
                          "Operator pin (binding)" since
                          sign-off has landed.

                     Loop budget: 2/5 consumed. Codex audit
                     CLOSED. 19 §11.6 anticipated pins
                     ratified binding for the UI-13..UI-15+
                     family.
Implementation:      BLOCKED on this brief's merge.
                     UI-13 chunk brief does NOT open until
                     this macro brief lands in main.
                     Phase 4 close criteria in §3-E.
```

The brief follows the lifecycle established by
`ui-0-design-brief.md` (PR #62), `ui-10-design-brief.md`
(PR #83), `ui-11-design-brief.md` (PR #87),
`ui-12-design-brief.md` (PR #93),
`ui-12b-design-brief.md` (PR #100), and
`ui-12c-design-brief.md` (PR #104):

```text
1. Implementer drafts the brief as a doc-only PR with
   sign-off markers.
2. Operator reviews and confirms ("avanzar" or
   per-marker). Markers flip to a confirmed-date stamp.
3. Implementer entrega the audit prompt copy-paste to
   the operator immediately.
4. Codex audits the brief; verdict ferried back via the
   operator. Round 1 typically returns 1-2 P0 + a handful
   of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   triggered when Codex round 1 was CHANGES-REQUIRED with
   P0; APPROVED-with-observations + P1/P2 land as
   in-branch follow-ups without a re-audit.
6. Brief PR merges BEFORE the UI-13 chunk-level brief
   opens. Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```
