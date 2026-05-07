# Karasu UI — UI-13 Design Brief (remote operator surface)

> Doc-only seal of the visual + structural direction for
> UI-13. Earned per Phase 4 macro brief §10 (PR #107) carry-
> forward: TLS posture, credentials format, session token
> format, login screen primitive, F9/F10/F11 disposition,
> CSRF mechanism, SW scope discipline, deploy ergonomics —
> all deferred to this chunk-level brief by the macro.
>
> Audited and merged BEFORE any UI-13 code chunk opens.
>
> Parallel to:
> - `phase-4-macro-brief.md`  (Phase 4 macro frame, 19 §11.6 pins)
> - `ui-12-design-brief.md`   (UI-12 push notifications family)
> - `ui-12c-design-brief.md`  (UI-12c server-side push emit)
>
> The Phase 4 macro brief sealed the architectural frame
> (deployment shape + auth model + transport-agnostic
> security boundary + secret inventory + crypto-scope
> trigger). UI-13 chunk-level brief earns the IMPLEMENTATION
> contract: exact mechanisms, file shapes, test surface,
> §11.6 pins specific to the remote-frontier code chunk.
>
> **STATUS:** Operator sign-off pending. Codex audit
> round 1 closed (CHANGES-REQUIRED, 6 P1 + 1 P2, no
> P0; all seven addressed in-branch). Round 2 audit
> prompt delivered to operator. Loop budget: 1/5.

## 0 · Why this brief exists

Phase 4 macro brief (`phase-4-macro-brief.md`, PR #107
merged 2026-05-07) sealed the architectural frame:
self-hosted single instance, single-operator credentials,
transport-agnostic security boundary, complete secret
inventory, exact-primitive crypto-scope trigger. The 19
§11.6 pins are now binding for UI-13..UI-15+.

UI-13 is the FIRST CHUNK in the Phase 4 family. It earns
the first remote frontier:

```text
* HTTPS termination posture (caddy/nginx-friendly +
  documented stdlib ssl dev fallback).
* Username + password credentials with scrypt hashing.
* Signed-cookie session via stdlib hmac + secrets.
* CSRF protection via signed double-submit cookie +
  Origin check on every mutating route.
* Service worker scope discipline (pre-auth surface
  limited to login + manifest + inert assets).
* Login screen visual primitive (one new design-system
  primitive, intentionally minimal).
* Logout flow.
* Auth gating middleware in karasu ui that maps
  Phase 4 §3-C item 1 (transport-agnostic) +
  item 2 (anonymous reachability narrow) verbatim.
* Ops runbook documenting bring-up from scratch.
```

UI-13 does NOT earn:

```text
* PWA installable polish (manifest icons / theme color
  / install prompt posture / mobile compat) — UI-14.
* Native packaging — UI-15+ conditional.
* Multi-operator authorization — Phase 4.y.
* Multi-instance HA / multi-host file lock — Phase 4.x.
* A2A peer push fan-out — Phase 4.z.
```

The brief is intentionally short (target <1200 LOC; mirror
of the macro brief's "short and binding" discipline).

## 0.5 · Pins inherited (verbatim, binding)

UI-13 inherits **145 binding pins**:

```text
52  base (UI-0 through UI-9.1)
 6  UI-10 §0.5
12  UI-11 §11.6
16  UI-12 §11.6
16  UI-12b §11.6
 4  PR #102 round-2 forward-carry
20  UI-12c §11.6
19  Phase 4 macro §11.6
```

The Phase 4 macro pins driving UI-13 specifically:

```text
1.  Single-instance deployment shape.
2.  Single-operator auth model.
3.  State privacy is TRANSPORT-AGNOSTIC (every route or
    transport reading / mutating operator state requires
    auth). UI-13 implements this verbatim.
4.  Anonymous reachability narrow (login surface + inert
    login assets + manifest only). UI-13 builds the auth
    middleware that draws the perimeter.
5.  CSRF / origin protection on every mutating route or
    transport. UI-13 picks the mechanism (§3-F below).
6.  Online-guessing protection (generic failures, no
    enumeration, rate-limit / backoff, scrypt cost
    parameters). UI-13 picks the mechanism (§3-B + §3-G).
7.  Cookie hardening (HttpOnly + Secure + SameSite). UI-13
    pins the exact attributes (§3-C).
8.  Session lifecycle (bounded expiry + rotation +
    ops-side credential rotation invalidates all). UI-13
    picks the duration + the invalidation seam (§3-C).
9.  Push subscription endpoints remain operator-private.
    UI-13 brings UI-12a / UI-12b / UI-12c routes behind
    auth — does NOT change their response shapes.
11. Secret inventory (VAPID + auth + session + TLS +
    future tokens, all mode-0600). UI-13 lands the auth +
    session secret files (§3-D).
12. Bus + scar + dispatch state operator-private. /api/*
    behind auth.
13. cryptography import scope: default hashlib.scrypt for
    password hashing does NOT re-open UI-0 §4. UI-13 uses
    stdlib hashlib.scrypt + hmac + secrets exclusively;
    no new runtime dep.
15. Each chunk earns its own brief (THIS doc).
16. Memory-sync follow-up PR after merge (mirror of
    PR #99 / #103 / #106).
17. Loop budget 5 rounds per audit cycle.
18. NO @codex review tag, NO ChatGPT Codex Connector.
19. First-second perception: locked-by-default, login
    screen, not empty shell with bus hooks.
```

## 1 · Positioning

UI-13 is the chunk where **Karasu opens up to Victor over
the network for the first time**. Every prior chunk
(UI-0..UI-12c) ran on `127.0.0.1`; UI-13 puts a TLS
boundary in front and gates everything operator-private
behind a session.

> The first second of looking at a deployed Karasu must
> read as "this is mine and you are not in". The login
> screen is the entire surface for the unauthenticated
> visitor; the operator's daily flow does not regress
> after auth (login once, stay in for ~14 days);
> failures (TLS misconfigured, session expired, CSRF
> rejected) surface visibly with operator-actionable
> text, never silent 500s.

UI-13 adds NO push primitive, NO PWA install polish, NO
multi-operator surface. Those are UI-14 and Phase 4.y.

## 2 · Visual references (anchors held)

UI-13 adds exactly ONE new visual primitive to the design
system: the **login screen**.

```text
- Centered form inside a bounded container (max-width
  ~360 px so it doesn't sprawl on desktop).
- Crow glyph 96 px hero at top (reuses crow.svg from
  UI-5; idle state — no animation, no flight).
- Two inputs (username + password). Same `--focus-ring`
  + spacing tokens as the design-system page.
- One primary button "Enter" (or equivalent — chunk
  brief picks the exact word).
- One error message slot below the button. Uses --warn
  token (same as the failed-state crow) when populated;
  hidden otherwise.
- No "forgot password" link.
- No "create account" link.
- No third-party auth icons.
- No marketing copy.
- No theme switcher (the existing dark surface IS the
  theme).
- Crow glyph stays idle even on auth failure — the error
  text carries the failure signal; the crow doesn't shake
  on a bad password (the shake is for system errors, not
  operator typos).
```

The PWA shell + design-system page + UI-12 push surfaces
remain visually unchanged. UI-13's only design system delta
is `static/css/login.css` (one new feature CSS file
following the UI-4 timeline.css / UI-12b modal.css
pattern).

## 3 · Confirmed decisions (operator sign-off pending)

All decisions below carry **operator-confirmed defaults**
provided 2026-05-07. Markers flip from
`[NEEDS OPERATOR SIGN-OFF]` to
`[CONFIRMED 2026-05-07]` once Victor confirms the brief
en bloc.

### A) TLS posture

PROPOSAL — caddy / nginx termination is the **principal
deployment posture**; stdlib `ssl` is documented as a
**dev/local fallback only**, NOT recommended for production.

```text
PRINCIPAL POSTURE (production):
  * karasu ui binds 127.0.0.1:8787 (existing default).
  * caddy / nginx terminates TLS on the public hostname
    + reverse-proxies to 127.0.0.1:8787.
  * caddy snippet documented in docs/deploy-runbook.md
    (NEW, see §3-H).
  * The `Forwarded` (RFC 7239) and `X-Forwarded-Proto`
    headers are honored to detect "TLS is on" for the
    Cookie `Secure` attribute. Trust is per-config: by
    default, only `Forwarded` from 127.0.0.1 is trusted
    (the reverse-proxy on the same host).

DEV/LOCAL FALLBACK (NOT production):
  * `karasu ui --tls-cert PATH --tls-key PATH` flags use
    stdlib `ssl.SSLContext` to terminate TLS in the
    karasu ui process itself.
  * The startup banner prints a loud-stderr "TLS via
    stdlib ssl: dev/local fallback only — NOT for
    production" warning whenever both flags are set.
  * mkcert + a local hostname is the documented dev
    flow.
  * cryptography import scope is NOT extended; stdlib
    ssl is sufficient.

NEVER:
  * karasu ui terminating TLS in production behind a
    public hostname. The startup banner + docs steer
    operators away; the implementation does NOT block
    it (the dev/local flow needs the same code path),
    but the documentation gradient is unambiguous.
```

[NEEDS OPERATOR SIGN-OFF]

### B) Credentials format

PROPOSAL — **username + password**, hash via
`hashlib.scrypt`. NO passphrase-only.

```text
File: <config_dir>/karasu-auth.json (mode 0600 POSIX;
      Windows advisory-mode equivalent with the UI-12b
      loud-stderr warning shape).

Shape:
{
  "username": "victor",
  "password_hash": "scrypt$N=16384$r=8$p=1$<salt_b64>$<hash_b64>",
  "session_signing_secret": "<32-byte b64>",
  "credentials_generation": <int, monotonic>,
  "created_at": "<iso8601 utc>",
  "rotated_at": "<iso8601 utc>"
}

scrypt parameters (binding):
  N = 16384  (2^14)
  r = 8
  p = 1
  salt = 16 bytes os.urandom
  derived key length = 32 bytes
  Cost ≈ 250 ms on a commodity 2024-era VPS (chunk
  brief's job to verify on the deployment target before
  merge; the parameters are tuned for online-guessing
  hardness without being a DoS vector on legitimate
  login).

`credentials_generation` is the binding seam for
ops-side rotation:
  * Every cookie embeds the `gen` of the credentials
    file at issue time.
  * Auth middleware rejects any cookie whose `gen`
    mismatches the current file `gen`.
  * Rotating credentials = bump `gen` + rewrite hash.
    All existing sessions invalidated atomically.

Bootstrap CLI: `karasu auth set-credentials` (NEW
subcommand). Prompts for username + password (no
echo), generates a fresh signing secret, writes
karasu-auth.json. Default config dir is the same as
karasu-push.json (next to events.jsonl). Stdin-pipe
fallback supported for ops automation without a TTY
(documented in docs/deploy-runbook.md).

FAIL-CLOSED STARTUP CONTRACT (Codex round 1 P1
binding, 2026-05-07):

  When `karasu ui` starts in deployed posture (auth
  enabled is the default; --no-auth dev flag is
  documented for localhost iteration only), the
  startup MUST refuse to bind the listener if any of:

    * karasu-auth.json absent.
    * karasu-auth.json malformed (invalid JSON,
      non-object root, missing required fields).
    * karasu-auth.json present with mode looser than
      0600 on POSIX (Windows advisory-mode warning per
      UI-12b loud-stderr shape; deployed posture on
      Windows STILL refuses to start until the file
      is at least owner-only via icacls).
    * password_hash field absent / wrong shape /
      empty.
    * session_signing_secret absent / decode-fails-
      base64 / shorter than 32 bytes.
    * credentials_generation absent / not an int /
      negative.

  On any failure: print a generic stderr message
  ("error: karasu auth credentials are missing or
  malformed; refusing to start. See
  docs/deploy-runbook.md for bring-up.") + non-zero
  exit code (2). NO secret material in the message.
  NO file path in the message (the operator already
  knows the conventional location). NO fallback
  anonymous shell — the deployed posture refuses
  rather than silently serving the bus to anonymous
  visitors.

  Localhost `--no-auth` dev flag (NEW; chunk brief
  reserves; default OFF) bypasses the auth gate
  entirely for localhost iteration. The flag emits
  a loud-stderr "AUTH DISABLED — dev only, NOT for
  production" warning at startup. NEVER set in any
  documented deploy-runbook.md path.

  Mirrors the UI-12c §3-F bootstrap-fatal pattern
  (PushStoreError → cmd_watch returns 2 with generic
  stderr) — auth is the same shape: malformed-store
  → fatal startup, no quiet fallback.
```

[NEEDS OPERATOR SIGN-OFF]

### C) Session format

PROPOSAL — **signed cookie via stdlib `hmac` + `secrets`**;
NO DB-backed session table for UI-13.

```text
Cookie: karasu_session

Value (b64url-no-pad of the JSON object):
  {
    "user": "<username>",
    "exp": <unix ts seconds>,
    "gen": <credentials_generation int>,
    "nonce": "<16 bytes b64>",
    "sig": "<32 bytes hmac-sha256 b64>"
  }
  where sig = HMAC-SHA256(
    session_signing_secret,
    f"{user}|{exp}|{gen}|{nonce}".encode()
  )

Attributes:
  HttpOnly  yes
  Secure    yes (when TLS detected via Forwarded /
              X-Forwarded-Proto / direct ssl context)
  SameSite  Strict
  Path      /
  Max-Age   1209600 (14 days)

Expiry: 14 days default. CLI flag
  --session-ttl-days <int>
overrides; valid range 1..30.

Rotation seams (see §3-B):
  * Credentials rotation bumps `gen` → all cookies
    rejected at next request.
  * Logout endpoint clears the cookie client-side
    (Set-Cookie: karasu_session=; Max-Age=0).
  * No server-side per-session blacklist (no DB; chunk
    brief defers DB-backed sessions to a future chunk
    if dogfood demands per-session revocation).

Validation order (binding):
  1. Parse cookie value as JSON.
  2. Verify HMAC signature against current
     session_signing_secret. Comparison MUST use
     hmac.compare_digest (constant-time; Codex round 1
     P2 binding 2026-05-07). Plain `==` comparison
     leaks signature timing and is a regression.
  3. Check `gen` matches current credentials_generation.
  4. Check `exp > now` (clock skew margin: 60 s).
  5. If all four pass, request is authenticated as
     `user`.
  Any single failure → unauthenticated path (login
  page for GET /, 401 + generic body for /api/*).

Constant-time compare discipline (binding; Codex
round 1 P2 2026-05-07): every comparison of auth
material in this brief uses hmac.compare_digest:
  * Session cookie HMAC verification (this section).
  * scrypt password hash comparison on login (§3-G).
  * CSRF cookie nonce.sig vs X-Karasu-CSRF header
    comparison + cookie sig re-verification (§3-F).
The brief already pins timing parity for the
no-username branch; constant-time comparisons close
the same class of leak for valid-user wrong-password
+ tampered-cookie + replayed-CSRF paths.
```

[NEEDS OPERATOR SIGN-OFF]

### D) Auth middleware + path perimeter

PROPOSAL — middleware in `src/karasu/ui/server.py` (or a
new `src/karasu/ui/_auth.py` module the chunk picks)
runs BEFORE every request handler:

```text
URL CONTRACT (Codex round 1 P1 binding 2026-05-07):
The brief uses the EXISTING /assets/* namespace from
UI-0..UI-12c verbatim. No new namespace, no aliased
routes. The login page links the SAME tokens.css /
reset.css / base.css under /assets/css/* + adds
/assets/css/login.css. The manifest stays at
/assets/manifest.json. The SW stays at /assets/sw.js.

ANONYMOUS PATHS (whitelisted; transport-agnostic;
EXACT set):
  GET /                          → if no session, render
                                   login.html (inline);
                                   if session, render the
                                   PWA shell (existing
                                   index.html).
  GET /assets/css/login.css      (NEW file UI-13 ships)
  GET /assets/css/tokens.css     (existing UI-2)
  GET /assets/css/reset.css      (existing UI-2)
  GET /assets/css/base.css       (existing UI-2)
  GET /assets/icons/karasu-192.png   (manifest icon;
                                      also rendered as
                                      login crow if
                                      crow.svg disabled)
  GET /assets/crow/crow.svg          (rendered in login
                                      hero)
  GET /assets/fonts/*.woff2          (login uses
                                      design-system
                                      tokens; entire
                                      fonts directory
                                      stays anonymous)
  GET /assets/manifest.json          (browser PWA
                                      install prompt
                                      discovery; macro
                                      §3-C item 2
                                      binding)
  GET /assets/sw.js                  (anonymous BUT see
                                      §3-H SW scope —
                                      pre-auth cache
                                      strictly limited)
  POST /auth/login                   (CSRF-cookie-exempt
                                      per §3-F; Origin
                                      check enforced)
  GET /auth/logout                   (idempotent;
                                      clears cookie +
                                      redirects to /;
                                      see Logout
                                      section below)

NOTE: a favicon route (/favicon.ico OR
/assets/icons/favicon.ico) is NOT in the existing
codebase. UI-13 either ships a favicon at
/assets/icons/favicon.ico (added to the whitelist if
shipped) or omits it (browsers gracefully 404). The
chunk brief picks at code time; the macro pin
enforces the EXACT set, so adding/removing the
favicon path is a brief amendment.

EVERY OTHER PATH:
  Requires a valid session per §3-C.
  GET routes without session → redirect to /
                              (which renders login).
  POST/PUT/DELETE without session → 401 + generic body
                                   {"error":"unauthorized"}.
  POST/PUT/DELETE with session BUT failing CSRF
    (§3-F) → 403 + generic body
                   {"error":"forbidden"}.

LOGOUT split (Codex round 1 P1 binding 2026-05-07):
  GET  /auth/logout — idempotent, anonymous, clears
                      session + csrf cookies via
                      Set-Cookie Max-Age=0 + redirects
                      to /. Safe for browser back-button
                      navigation, link-clicks, and
                      no-session calls.
  POST /auth/logout — auth-required + CSRF-required. For
                      explicit JS-driven logout from the
                      PWA shell. The frontend's logout
                      affordance uses POST so the
                      operator's intent is unambiguous;
                      GET stays as the recovery /
                      idempotent shape.
  Both clear the cookies; only the POST shape requires
  a valid session + CSRF (so a stray GET on a stale tab
  cannot be forced by a malicious link in another tab).

This perimeter implements Phase 4 macro §3-C item 1
(transport-agnostic) + item 2 (anonymous reachability
narrow) verbatim. Future SSE / WebSocket transports
inherit the same default (auth-required unless
explicitly whitelisted by a chunk brief).
```

[NEEDS OPERATOR SIGN-OFF]

### E) Login screen visual primitive

PROPOSAL — `static/login.html` rendered by the same
HTTP server when GET / arrives without a valid session:

```text
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Karasu</title>
    <link rel="stylesheet" href="/assets/css/tokens.css">
    <link rel="stylesheet" href="/assets/css/reset.css">
    <link rel="stylesheet" href="/assets/css/base.css">
    <link rel="stylesheet" href="/assets/css/login.css">
    <link rel="manifest" href="/assets/manifest.json">
  </head>
  <body>
    <main class="login">
      <img src="/assets/crow/crow.svg"
           class="login-crow"
           alt=""
           width="96"
           height="96">
      <form class="login-form"
            method="POST"
            action="/auth/login">
        <label for="username">Username</label>
        <input id="username"
               name="username"
               type="text"
               autocomplete="username"
               required>
        <label for="password">Password</label>
        <input id="password"
               name="password"
               type="password"
               autocomplete="current-password"
               required>
        <button type="submit">Enter</button>
        <div class="login-error" hidden></div>
      </form>
    </main>
  </body>
</html>

Visual constraints (binding):
  * NO marketing copy.
  * NO "create account" link.
  * NO "forgot password" link.
  * NO third-party auth buttons.
  * NO theme switcher.
  * NO password strength meter (single-operator;
    operator already chose the password they wanted).
  * NO "show password" toggle (single-operator; if
    operator wants to verify, they can paste it).
  * Error slot is generic copy ("Could not sign in.")
    per §3-G online-guessing protection — no
    "username not found" vs "wrong password" leak.
  * Crow stays idle; the shake-on-error from UI-5 is
    for system errors, NOT operator typos.

NO JavaScript on the login page beyond a tiny inline
handler that progressively enhances the form submit to
fetch + replace the error slot text without a full
reload. The form MUST work with JS disabled (POST →
302 with cookie set on success; POST → 200 login.html
re-render with error slot populated on failure).
```

[NEEDS OPERATOR SIGN-OFF]

### F) CSRF mechanism

PROPOSAL — **signed double-submit cookie + strict
Origin/Referer check** for every mutating request on
every transport. The "signed" word is intentional and
binding: the cookie carries a value derived from the
session signing secret, NOT just a random token (Codex
round 1 P1 binding 2026-05-07).

```text
On login success, server sets a SECOND cookie:
  Cookie name: karasu_csrf
  Value:       <nonce>.<sig>
                 where:
                   nonce = 32 bytes os.urandom, b64url-
                           no-pad (43 chars)
                   sig   = HMAC-SHA256(
                             session_signing_secret,
                             b"csrf:" + nonce_bytes +
                             b"|user:" +
                             username.encode("utf-8") +
                             b"|gen:" + str(gen).encode()
                           ) → b64url-no-pad
  Attributes:  Secure (when TLS), SameSite=Strict, Path=/
               NOT HttpOnly (the JS layer needs to read
               it to attach as a header).

The signed shape (a) binds the CSRF token to the
current session's signing secret + user + credentials
generation, so a token leaked via JS errors or DOM
inspection cannot be replayed against a different
session, and (b) credentials_generation rotation
invalidates every CSRF token in the wild atomically
along with sessions.

Mutating request validation (POST/PUT/DELETE on every
transport):
  1. Origin header MUST equal the configured public
     origin in deployed posture. Referer fallback ONLY
     if Origin is absent. Both absent → 403, NO
     fallback. Default deployed posture rejects
     absent-Origin; the localhost dev posture
     (--no-auth flag from §3-B OR direct 127.0.0.1
     traffic with no Forwarded) MAY accept absent-
     Origin as the explicit dev/legacy fallback,
     loud-stderr-warned at startup.
  2. The request MUST carry header
       X-Karasu-CSRF: <nonce>.<sig>
     equal to the karasu_csrf cookie value, compared
     via hmac.compare_digest (constant-time, see §3-G
     log discipline + Codex round 1 P2 binding).
  3. The cookie's signature MUST verify against the
     CURRENT session_signing_secret + the session's
     username + gen. Verification uses
     hmac.compare_digest.
  4. The session cookie MUST be valid per §3-C.
  5. All four checks pass → request proceeds.
     Any failure → 403 + generic body.

Bootstrap (login itself is mutating):
  POST /auth/login is exempt from the karasu_csrf
  cookie check (the cookie doesn't exist pre-login)
  but enforces the strict Origin/Referer check above.
  SameSite=Strict on session+csrf cookies after login
  means third-party origins cannot ride existing
  sessions. The login form's HTML submission carries
  Origin natively from same-origin browsers; an
  absent-Origin pre-login POST in deployed posture
  is rejected (matches deployed-posture mutating
  default).

Frontend: the inline JS in static/index.html that
handles fetch()-based POSTs to /api/* (UI-12b push.js
is the canonical example) is updated to read the
karasu_csrf cookie + attach it verbatim as the
X-Karasu-CSRF header.

Frontend regression: every existing UI-10/UI-11/UI-12b
mutating call (scar revoke POST, trust adjust POST,
push subscribe POST, push unsubscribe POST) MUST
attach the header. The chunk brief audits each by
hand + the test surface pins them.
```

[NEEDS OPERATOR SIGN-OFF]

### G) Online-guessing + log discipline

PROPOSAL — per macro pin 6 (online-guessing
protection) + macro pin 7 (cookie hardening) + macro
pin 11 (no credential / session material in logs):

```text
Login failure response (binding):
  Status: 200 (re-render of login.html with error
          slot populated) OR 401 with the same
          generic body for /api/auth/login JSON
          requests.
  Error slot copy: "Could not sign in." (verbatim).
  NO "username not found" branch.
  NO "password wrong" branch.
  NO timing distinction: the no-username branch MUST
    perform a dummy scrypt verification against a
    known-bad hash so the response time is comparable
    to the wrong-password branch (test pinned).

Rate-limit / backoff (binding):
  Per-CLIENT-IP: max 5 failed login attempts per 60 s;
          6th attempt → 429 + generic body
          {"error":"too many attempts"}; backoff
          window doubles on each subsequent burst
          (cap at 1 hour).
  Per-credentials: max 10 failed attempts in 5 min;
          past the cap, even successful credentials
          return 429 for the same backoff window.
  In-memory only; restart-cleared by design (mirror
  of UI-12c pin §11.6.5 dedupe ring).

Trusted-client-IP derivation (Codex round 1 P1
binding 2026-05-07):

  The reverse-proxy production posture (caddy/nginx
  on 127.0.0.1) means the TCP peer address is ALWAYS
  127.0.0.1 in deployed mode. A naive "peer ==
  127.0.0.1 → bypass rate-limit" rule would let
  EVERY public login attempt skip protection. The
  rate-limit MUST derive the client IP correctly:

    1. If the TCP peer is 127.0.0.1 / ::1 AND
       the request carries no Forwarded /
       X-Forwarded-For header → DIRECT LOCALHOST.
       Bypass rate-limit (true dev iteration).
    2. If the TCP peer is in the trusted-proxy
       allowlist (default: 127.0.0.1 / ::1; chunk
       brief allows widening for split-host caddy
       layouts), the client IP is derived from
       the LEFTMOST entry of the Forwarded header's
       `for=` directive (RFC 7239) OR
       X-Forwarded-For. The DERIVED IP is the
       rate-limit key. Bypass applies ONLY if the
       derived IP itself is also localhost
       (127.0.0.1 / ::1) — i.e. the operator is
       running both caddy and a browser on the
       same dev box.
    3. If the TCP peer is anything else (direct
       remote connection, no proxy) → use the
       peer address as the client IP. No bypass.
    4. Malformed Forwarded / X-Forwarded-For (no
       parseable IP) → fail-closed: treat as a
       remote client with NO bypass + a fresh
       rate-limit slot (the conservative posture).

  Trusted-proxy list lives in karasu.yaml under
    auth.trusted_proxies: ["127.0.0.1", "::1"]
  Default is the localhost pair. Operators with a
  remote caddy host add the proxy IP explicitly;
  the chunk brief documents the threat model
  (proxy-host compromise = full bypass).

  Test surface (binding):
    * Direct 127.0.0.1 with no Forwarded → bypass.
    * 127.0.0.1 peer + Forwarded for=192.0.2.5 →
      192.0.2.5 is the rate-limit key; NO bypass.
    * 127.0.0.1 peer + Forwarded for=127.0.0.1 →
      bypass (caddy + browser on same box).
    * Remote peer with no proxy in the trusted
      list → peer address keys; NO bypass.
    * Malformed Forwarded → no bypass; fresh slot.

Log line shape on failed login (binding):
  WARNING karasu.ui.auth: login failed (ip=<ip>)
  No username, no password length, no hash, no headers.

Log line shape on successful login:
  INFO karasu.ui.auth: login ok (user=<username>, ip=<ip>)
  Username IS logged (single-operator; not sensitive
  on its own; needed for ops audit trail).
  Password / hash / session signing secret NEVER.

Log line shape on session validation failure (auth
middleware reject):
  No log line by default (would flood the log on every
  anonymous visit). Chunk brief MAY add a DEBUG line
  with cookie present-but-invalid markers if dogfood
  demands it.
```

[NEEDS OPERATOR SIGN-OFF]

### H) Service worker scope discipline

PROPOSAL — pre-auth SW serves ONLY the login surface +
manifest + inert assets:

```text
Pre-auth SW scope (binding):
  GET /sw.js                       (registered with
                                    scope: '/')
  Cached assets pre-auth:
    /                              (login.html)
    /static/css/login.css
    /static/css/tokens.css
    /static/css/reset.css
    /static/css/base.css
    /assets/crow/crow.svg
    /assets/icons/favicon.ico
    /assets/icons/karasu-192.png
    /assets/fonts/inter-display-*.woff2
    /manifest.webmanifest

  Cached assets MUST NOT include:
    The PWA app shell (static/index.html — it has
    bus-capable JS).
    UI-12b push.js.
    UI-10/UI-11 modal flows.
    /api/* responses (already SW-network-only by
    UI-8 contract; UI-13 reaffirms).

Post-auth SW scope (binding):
  On login success, the page sends a postMessage to
  the SW: {type: "auth:granted"}. The SW then
  swaps to the FULL PWA cache (the existing UI-8
  cache shape, additive).
  On logout, the page sends {type: "auth:revoked"}.
  The SW clears the post-auth cache and reverts to
  the pre-auth cache.

Post-auth cache revocation (Codex round 1 P1 binding
2026-05-07):

  Sessions can become invalid WITHOUT an explicit
  logout postMessage (cookie expiry, credentials_
  generation rotation, ops-side credential rewrite).
  A post-auth cache that survives those events would
  keep serving the bus-capable shell to a browser
  the server already considers unauthenticated.

  Two binding mechanisms:

    1. Navigation network-first for `/`. The SW
       fetch handler MUST treat GET / as
       network-first (hit the server, fall back to
       cache only on offline). The server's auth
       middleware redirects an expired/gen-mismatch
       session to the login render; the network-
       first behaviour means the redirect lands at
       the page rather than being masked by the
       cached app shell.

    2. SW + page revocation on auth-failure
       responses. When ANY fetch from the page
       returns 401 OR a redirect to /auth (i.e. the
       server signals "your session is no longer
       valid"), the page sends
       {type: "auth:revoked"} to the SW. The SW
       clears the post-auth cache + reverts to the
       pre-auth cache. The page reloads to /, which
       now renders login.

    Both layers compose: network-first for / catches
    navigation-time expiry; the auth-failure
    revocation catches mid-session expiry on /api/*
    fetches. Restart of the karasu watch / karasu ui
    process does NOT need to clear post-auth cache
    automatically; the next /api/* fetch on the
    operator's tab triggers the revocation flow.

  Test surface (binding):
    * Cookie present + expired exp → next fetch to
      / network-fetches; server redirects; cache
      reverts.
    * Cookie present + gen mismatch → next /api/*
      call returns 401; page postMessages
      auth:revoked; cache clears.
    * Logout POST → page postMessages auth:revoked
      explicitly + cache clears (existing path).
    * Offline + valid cookie → cache serves
      post-auth shell normally (network-first
      degrades gracefully).

Cache-name discipline:
  CACHE_NAME pre-auth: "karasu-ui-login-v13"
  CACHE_NAME post-auth: existing "karasu-ui-v12b"
  bumped to "karasu-ui-v13".
  Both deleted on cache-version mismatch (existing
  UI-8 shape).

UI-14 explicitly may reopen this contract for the
PWA install posture — the SW scope might need
adjustment for offline-first install ergonomics; the
chunk-level UI-14 brief documents.
```

[NEEDS OPERATOR SIGN-OFF]

## 3.5 · Operator pin (binding when sign-off lands)

PROPOSAL — paralleling UI-12c §3.5 + Phase 4 §3.5:

```text
UI-13 must read as Karasu's first remote door, not as
a generic web app. Three felt properties:

  1. Locked in one frame. The unauthenticated visitor
     sees one screen — login form, crow, nothing else.
     No header navigation, no footer affordances, no
     debug surfaces. The PWA chrome is invisible until
     the operator authenticates.

  2. Daily flow does not regress. Login once, stay in
     for ~14 days. The operator's existing UI-10 /
     UI-11 / UI-12b muscle memory works the SAME after
     auth — no extra clicks, no re-auth prompt, no new
     consent surfaces. Auth is a boundary the operator
     crosses once a fortnight, not a friction layer.

  3. Failures are loud. TLS misconfigured → karasu ui
     refuses to start with a clear stderr message.
     Session expired → redirect to login (the
     operator notices the URL change). CSRF rejected
     → 403 with operator-actionable copy ("Try the
     action again from a fresh tab"). Silent 500s on
     auth-relevant code paths are a regression.
```

[NEEDS OPERATOR SIGN-OFF]

## 4 · Tech stack (delta vs UI-0..UI-12c + Phase 4 macro)

UI-0..UI-12c stack still holds. UI-13 adds:

```text
+ stdlib `hashlib.scrypt` for password hashing. Default
  per Phase 4 §4 + macro pin 13. NO new runtime dep.

+ stdlib `hmac` + `secrets` for session signing +
  CSRF token generation. NO new runtime dep.

+ stdlib `ssl.SSLContext` for the dev/local TLS
  fallback (§3-A). Loaded ONLY when --tls-cert / --tls-key
  flags are present at startup; production caddy/nginx
  posture does not import it.

+ src/karasu/ui/_auth.py (NEW) — credentials
  load/verify, session sign/verify, CSRF token shape,
  the auth middleware. ~400 LOC.

+ src/karasu/ui/static/login.html (NEW).

+ src/karasu/ui/static/css/login.css (NEW; first
  feature CSS for an auth surface).

+ src/karasu/ui/static/sw.js — additive. Pre-auth +
  post-auth cache discipline (§3-H).

+ src/karasu/__main__.py — `karasu auth
  set-credentials` subcommand (NEW); `karasu ui
  --tls-cert / --tls-key / --session-ttl-days` flags
  (NEW).

+ docs/deploy-runbook.md (NEW) — bring-up from
  scratch, caddy + nginx snippets, mkcert dev flow,
  ops-side credential rotation, troubleshooting.

+ tests/test_auth_*.py (NEW) — see §6 file split.

NO new build / framework dep. NO new front-end files
beyond login.html / login.css. The
cryptography import scope (UI-12c §11.6.13) is NOT
extended.
```

## 5 · Design system (delta vs UI-0..UI-12c)

UI-13 adds exactly ONE new feature CSS file:
`static/css/login.css`. The file follows the UI-4
timeline.css / UI-12b modal.css discipline:

```text
- Class-namespaced (.login, .login-form, .login-crow,
  .login-error). No element selectors that could leak
  into the post-auth shell.
- Uses the existing UI-2 tokens exclusively. No new
  custom properties.
- Reduced-motion clamp inherited from reset.css.
```

Login screen primitives (per §3-E):
- `.login` — main container, centered, max-width 360 px.
- `.login-crow` — 96 px crow image, idle state.
- `.login-form` — form wrapper, vertical stack with
  spacing tokens.
- `.login-form > label` — label typography per design system.
- `.login-form > input` — input shape (UI-12b modal
  forms are the closest existing reference).
- `.login-form > button` — primary button per design
  system.
- `.login-error` — generic error slot, --warn token,
  hidden by default.

NO toolbar. NO settings panel. NO theme switcher.

## 6 · Roadmap (single chunk; possible split)

```text
UI-13 — Single PR. ~1500-2500 LOC including tests +
docs. Files:

  Code:
    src/karasu/ui/_auth.py                 ~400 LOC
                                            (credentials
                                            load/verify;
                                            session
                                            sign/verify;
                                            CSRF token
                                            shape;
                                            middleware)
    src/karasu/ui/server.py                +120 LOC
                                            (middleware
                                            integration;
                                            login/logout
                                            handlers;
                                            anonymous-
                                            paths
                                            whitelist)
    src/karasu/__main__.py                 +80 LOC
                                            (auth
                                            set-credentials
                                            subcommand;
                                            ui --tls-cert /
                                            --tls-key /
                                            --session-ttl-days
                                            flags)
    src/karasu/ui/static/login.html        ~50 LOC
    src/karasu/ui/static/css/login.css     ~80 LOC
    src/karasu/ui/static/sw.js             +60 LOC
                                            (pre-auth +
                                            post-auth
                                            cache shapes)
    src/karasu/ui/static/js/push.js        +30 LOC
                                            (CSRF header
                                            attach on
                                            mutating
                                            POSTs)
    src/karasu/ui/static/index.html        +20 LOC
                                            (CSRF cookie
                                            read + attach
                                            inline; SW
                                            register
                                            update)

  Tests:
    tests/test_auth_credentials.py         ~150 LOC
    tests/test_auth_session.py             ~180 LOC
                                            (sign/verify
                                            + tamper +
                                            expiry + gen
                                            mismatch +
                                            timing)
    tests/test_auth_middleware.py          ~250 LOC
                                            (path
                                            whitelist +
                                            redirect /
                                            401 / 403
                                            matrix)
    tests/test_auth_csrf.py                ~120 LOC
                                            (double-submit
                                            cookie + origin
                                            check)
    tests/test_auth_login_flow.py          ~180 LOC
                                            (happy + 200
                                            re-render +
                                            generic
                                            failure +
                                            no-username
                                            timing parity +
                                            429 backoff)
    tests/test_auth_logout.py              ~80 LOC
                                            (cookie clear
                                            + redirect)
    tests/test_auth_sw_scope.py            ~100 LOC
                                            (pre-auth
                                            cache shape;
                                            post-auth
                                            swap)
    tests/test_ui_login_page.py            ~80 LOC
                                            (HTML shape
                                            lock + form
                                            shape +
                                            tokens
                                            referenced)
    tests/test_auth_log_privacy.py         ~80 LOC
                                            (no
                                            password /
                                            hash /
                                            secret in
                                            logs;
                                            sentinel
                                            test)
    tests/test_main_auth.py                ~80 LOC
                                            (auth
                                            set-credentials
                                            CLI happy +
                                            no-tty
                                            fallback)

  Visual:
    1-2 PNGs of login screen
    1 PNG of post-login redirect
    1 .webm of edge-to-edge: visit / →
      login → enter creds → app shell

  Docs:
    docs/deploy-runbook.md                 NEW (bring-up
                                            from scratch
                                            + caddy +
                                            nginx +
                                            mkcert dev
                                            flow + ops
                                            rotation)
    docs/event-schema.md                   no change
                                            (no new bus
                                            event types)
    docs/local-dogfood.md                  +30 LOC
                                            (link to
                                            deploy-runbook;
                                            note auth
                                            now required
                                            for /api/*)

  Target ~1500-2500 LOC code+tests+docs.

POSSIBLE SPLIT into UI-13a + UI-13b:
  Considered IF the first round of audits surfaces a
  scope cap concern. Default disposition: single PR.
  UI-13a/b split would draw the line at:
    UI-13a: auth backend + login/logout flow + middleware.
    UI-13b: CSRF + SW scope + ops runbook + frontend
            CSRF header.
  The chunk implementer picks at code time if the test
  surface or the audit cycles demand it.
```

[NEEDS OPERATOR SIGN-OFF on the single-chunk vs split
disposition; default single chunk]

## 7 · Audit cadence (UI-12c §7 + Phase 4 §7 carry-forward)

```text
- PR body documents the brief sections it implements.
- Test surface: 9-10 new test files all green; existing
  731 + memory-sync delta still green (no regression).
- Visual surface: 1-2 PNGs of login + 1 PNG of post-
  login redirect + 1 .webm edge-to-edge.
- Lighthouse: re-run; thresholds unchanged from UI-9.1
  baseline. Auth-gated routes excluded from the scoring
  corpus (the login page IS the corpus for the deployed
  posture).
- Operator sign-off marker before code branch opens.
- Codex audit out-of-band; verdict ferried back via
  operator (no @codex review tag, no ChatGPT Codex
  Connector).
- Memory sync follow-up PR after UI-13 merges (mirror
  of PR #99 / #103 / #106).
```

## 8 · Frozen contracts (UI-13 MUST respect)

```text
- AgentResponse, F3, F7, F8, surface=sink, single-
  worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol — all frozen.

- The bus event schema (additive only; UI-13 emits NO
  new event types — auth events are NOT bus events).

- The /api/events / /api/health / /api/meta /
  /api/scars / /api/agents / /api/push response
  shapes. UI-13 ADDS auth gating ON TOP; the response
  bodies behind a valid session are byte-for-byte the
  pre-UI-13 shape.

- The UI-12b POST /api/push/subscribe +
  /api/push/unsubscribe shapes. UI-13 adds auth gating
  + CSRF requirement; the success / error matrix is
  unchanged.

- The UI-12c push_emit pipeline. UI-13 does NOT
  change the dispatch contract; only WHO can subscribe
  the browser changes (auth required).

- The cryptography import scope (3 push_emit files).
  UI-13 does NOT extend it.

- The Lighthouse threshold contract.

- The 145 binding pins inherited.

- Out-of-band Codex audit.
```

## 9 · Out of scope for UI-13

```text
- PWA install prompt posture — UI-14.
- Mobile layout audit — UI-14.
- Service worker update strategy refinements beyond
  the pre-auth/post-auth split — UI-14.
- Native packaging — UI-15+.
- Multi-operator authorization — Phase 4.y.
- Multi-instance HA — Phase 4.x.
- A2A peer push fan-out — Phase 4.z.
- Per-event push opt-in beyond the closed enum —
  future chunk.
- Push body content beyond editorial title — future.
- VAPID auto-rotation — future.
- DB-backed session table (per-session revocation
  beyond credential rotation) — future chunk if
  dogfood demands.
- Phase 3 hardening F9 / F10 / F11 — parallel ops
  track per Phase 4 macro §10 (5).
- Password reset flow.
- "Create account" / signup flow.
- Third-party auth (OAuth / OIDC).
- Username + password recovery (operator edits the
  credentials file).
- Per-IP allow / deny lists beyond the localhost
  rate-limit bypass — future chunk if dogfood demands.
- Audit log surface for failed-auth attempts — the
  log lines are the audit; a UI surface for them
  earns its own brief.
```

## 10 · Open questions (operator sign-off needed)

All eight resolved at brief draft time per Victor's
2026-05-07 defaults. Markers flip to confirmed on
en-bloc sign-off.

```text
1. TLS posture. PROPOSAL — caddy/nginx principal +
   stdlib ssl dev fallback (§3-A).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

2. Credentials format. PROPOSAL — username + password
   + scrypt (§3-B).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

3. Session format. PROPOSAL — signed cookie via
   stdlib hmac + secrets (§3-C).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

4. Login screen primitive. PROPOSAL — minimal,
   blocked, no marketing/signup/reset/third-parties
   (§3-E).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

5. F9 / F10 / F11 disposition. PROPOSAL — parallel
   ops track, OUT of UI-13 scope, unless brief proves
   one blocks security/deploy.
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

6. CSRF mechanism. PROPOSAL — signed double-submit
   cookie + Origin check (§3-F).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

7. SW scope discipline. PROPOSAL — pre-auth only
   login/manifest/inert assets; post-auth swap on
   login success message (§3-H).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]

8. `karasu deploy` CLI helper. PROPOSAL — DISCARDED;
   replaced by env / config + ops runbook
   (docs/deploy-runbook.md).
   [NEEDS OPERATOR SIGN-OFF — default
   confirmed 2026-05-07]
```

## 11 · §11.6 anticipated pins (Codex audit, pending)

The chunk-level brief earns §11.6 pins from Codex's
audit. Anticipated shape (mirror of UI-12c §11.6 + Phase
4 §11.6; final wording lands after Codex's verdict):

```text
1. Production TLS posture is caddy / nginx termination;
   stdlib ssl is dev/local fallback only. Startup
   banner emits "NOT for production" warning when
   --tls-cert / --tls-key flags are set.

2. Credentials live in karasu-auth.json mode 0600 with
   the documented JSON shape: username +
   scrypt-hashed password + session signing secret +
   credentials_generation. scrypt parameters
   N=16384 / r=8 / p=1 binding.

3. Sessions are signed cookies (stdlib hmac +
   secrets). Validation order: parse → HMAC verify
   (constant-time hmac.compare_digest) → gen match →
   exp check (60 s clock skew margin) → pass.
   Any failure → unauthenticated.

4. Cookie attributes binding: HttpOnly, Secure (when
   TLS detected), SameSite=Strict, Path=/, Max-Age
   per --session-ttl-days (default 14, range 1-30).

5. Credentials_generation rotation invalidates ALL
   existing sessions (cookies embed gen at issue;
   middleware rejects gen mismatch). No DB-backed
   per-session revocation in UI-13.

6. Anonymous path whitelist is the EXACT set in §3-D
   under the existing /assets/* namespace. URL
   contract: /assets/css/login.css (NEW), existing
   /assets/css/{tokens,reset,base}.css,
   /assets/manifest.json, /assets/sw.js,
   /assets/crow/crow.svg, /assets/icons/karasu-192.png,
   /assets/fonts/*.woff2, plus GET / + POST
   /auth/login + GET /auth/logout. POST /auth/logout
   is auth+CSRF-required and NOT in the anon
   whitelist (Codex round 1 P1 binding).

7. Login failure response is generic ("Could not
   sign in.") + dummy scrypt verification on the
   no-username branch for timing parity. scrypt
   hash comparison is constant-time
   (hmac.compare_digest, Codex round 1 P2 binding).
   No username / hash / secret in any log line.
   Failed-auth log: WARNING with derived client IP +
   generic marker.

8. CSRF mechanism is SIGNED double-submit cookie
   (karasu_csrf value = nonce.sig where sig =
   HMAC-SHA256(session_signing_secret,
   "csrf:"||nonce||"|user:"||username||"|gen:"||gen);
   NOT HttpOnly, SameSite=Strict) + strict
   Origin/Referer match check. Every mutating route
   on every transport requires both. POST
   /auth/login is exempt from the CSRF cookie check
   (cookie doesn't exist pre-login) but enforces
   the Origin/Referer match in deployed posture.
   Absent-Origin + absent-Referer → 403 by default;
   only the localhost dev posture (--no-auth flag
   OR direct 127.0.0.1 traffic with no Forwarded)
   accepts absent-Origin (loud-stderr-warned).
   All comparisons constant-time (hmac.compare_digest).
   Codex round 1 P1 binding 2026-05-07.

9. Trusted-client-IP derivation. The reverse-proxy
   posture means peer addr is always 127.0.0.1 in
   deployed mode; rate-limit MUST derive client IP
   correctly. Direct 127.0.0.1 + no Forwarded →
   bypass. 127.0.0.1 + Forwarded for=<remote> → use
   <remote> as rate-limit key (NO bypass unless
   <remote> itself is localhost). Trusted-proxy
   list under auth.trusted_proxies in karasu.yaml
   (default ["127.0.0.1", "::1"]). Malformed
   Forwarded → fail-closed (no bypass). Codex round
   1 P1 binding 2026-05-07.

10. Per-CLIENT-IP rate-limit (post-derivation): 5
    failed attempts / 60 s → 429; backoff doubles
    per burst (cap 1 hour). Per-credentials: 10
    failed / 5 min. In-memory only; restart-cleared.

11. SW pre-auth cache shape is the EXACT set in
    §3-H ("Cached assets pre-auth"). The PWA app
    shell + UI-12b push.js + UI-10/UI-11 modals are
    NOT pre-cached. Post-auth swap on
    {type:"auth:granted"} postMessage; revert on
    {type:"auth:revoked"}. Cache names:
    "karasu-ui-login-v13" pre-auth + "karasu-ui-v13"
    post-auth.

12. Post-auth cache revocation paths beyond explicit
    logout: (a) navigation network-first for `/` so
    the server's expiry/gen-mismatch redirect lands
    at the operator's tab; (b) page sends
    auth:revoked postMessage on any 401 OR
    redirect-to-/auth response from /api/*.
    Test surface pins expired cookie + gen mismatch
    + offline + logout paths. Codex round 1 P1
    binding 2026-05-07.

13. UI-13 emits NO bus events. Auth events live in
    server logs only.

14. Frontend CSRF header attach: every existing
    UI-10 / UI-11 / UI-12b mutating call MUST attach
    X-Karasu-CSRF. Test surface pins each by hand.

15. Bootstrap CLI: `karasu auth set-credentials`.
    Prompted-password fallback for ops automation
    via stdin pipe; documented in deploy-runbook.

16. Fail-closed startup: deployed `karasu ui` refuses
    to bind the listener if karasu-auth.json is
    absent / malformed / wrong-mode / partial.
    Generic stderr + exit 2 + no anonymous fallback.
    Localhost --no-auth dev flag is the ONLY bypass;
    loud-stderr "AUTH DISABLED — dev only" warning
    at startup. Mirrors UI-12c §3-F bootstrap fatal.
    Codex round 1 P1 binding 2026-05-07.

17. Logout split: GET /auth/logout is anonymous +
    idempotent (cookie clear + redirect). POST
    /auth/logout is auth+CSRF-required (the JS
    affordance from the PWA shell). Both clear
    cookies; only POST asserts operator intent.
    Codex round 1 P1 binding 2026-05-07.

18. Constant-time compare discipline. Every
    comparison of auth material — session HMAC,
    scrypt password hash, CSRF cookie nonce.sig vs
    header, CSRF cookie sig re-verification — uses
    hmac.compare_digest. Plain `==` on auth material
    is a regression. Codex round 1 P2 binding
    2026-05-07.

19. cryptography import scope (UI-12c §11.6.13)
    NOT extended. UI-13 uses stdlib hashlib + hmac +
    secrets + ssl exclusively.

20. docs/deploy-runbook.md is the bring-up source of
    truth. Includes caddy snippet, nginx snippet,
    mkcert dev flow, credential rotation, trusted-
    proxy threat model, common troubleshooting (TLS
    misconfig, expired cert, wrong Forwarded
    posture, fail-closed startup messages).
```

These are anticipated; final wording lands after Codex's
verdict. Pins flip from anticipated to verbatim binding
once Codex's audit closes.

## 12 · Status

```text
Brief status:        DRAFT — operator sign-off pending.
Operator sign-off:   pending on §3 (A-H) + §3.5 + §10
                     en bloc. Operator orientation
                     provided 2026-05-07 with confirmed
                     defaults for all 8 §10 questions.
                     Macro brief codifies the
                     orientation into vinculant draft
                     form.
Codex audit:         Round 1 CHANGES-REQUIRED (6 P1 +
                     1 P2, no P0). All seven findings
                     addressed in-branch:
                       P1 §3-G trusted-client-IP
                          derivation: localhost
                          bypass only on direct peer
                          AND no-Forwarded; proxied
                          requests derive IP from
                          Forwarded/X-Forwarded-For
                          and bypass only when the
                          DERIVED IP is also
                          localhost. trusted_proxies
                          list under karasu.yaml
                          (default localhost). Test
                          surface pinned.
                       P1 §3-F CSRF "signed" actually
                          signed: cookie value is
                          nonce.sig where sig binds
                          session_signing_secret +
                          user + gen via HMAC-SHA256.
                          Validation uses
                          hmac.compare_digest. Origin/
                          Referer required to MATCH in
                          deployed posture; absent-
                          Origin acceptance is the
                          dev/legacy fallback only.
                       P1 §3-D logout split GET (anon
                          idempotent) vs POST
                          (auth+CSRF). POST /auth/logout
                          REMOVED from anon whitelist;
                          GET /auth/logout stays for
                          recovery / no-session calls.
                       P1 §3-D anonymous whitelist
                          aligned to existing
                          /assets/* namespace
                          (/assets/css/login.css NEW;
                          /assets/manifest.json,
                          /assets/sw.js, etc.).
                          login.html link rewrites to
                          match. URL contract pinned
                          in §11.6 anticipated pin 6.
                       P1 §3-H post-auth cache
                          revocation: navigation
                          network-first for /; page
                          sends auth:revoked
                          postMessage on any 401 OR
                          redirect-to-/auth response.
                          Tests pin expired cookie +
                          gen mismatch + offline +
                          explicit logout.
                       P1 §3-B fail-closed startup:
                          deployed `karasu ui` refuses
                          to bind on absent / malformed
                          / wrong-mode / partial
                          karasu-auth.json. Generic
                          stderr + exit 2 + no anon
                          fallback. Localhost
                          --no-auth dev flag with
                          loud-stderr warning is the
                          only bypass. Mirrors UI-12c
                          §3-F bootstrap fatal.
                       P2 §3-C constant-time compare
                          discipline: every auth-
                          material comparison
                          (session HMAC, scrypt hash,
                          CSRF cookie sig + header)
                          uses hmac.compare_digest.

                     §11.6 anticipated pins re-
                     numbered and expanded from 15 to
                     20 to absorb the new bindings
                     (added pins 6/8/9/12/16/17/18 +
                     adjusted pin 7).

                     Round 2 audit prompt delivered to
                     operator. Loop budget: 1/5
                     consumed.
Implementation:      BLOCKED on this brief's merge.
                     UI-13 code branch does NOT open
                     until this brief lands in main.
                     Phase 4 close criteria in
                     phase-4-macro-brief.md §3-E.
```

The brief follows the lifecycle established by the
prior chunks (UI-10 / UI-11 / UI-12 / UI-12b / UI-12c /
Phase 4 macro):

```text
1. Implementer drafts the brief as a doc-only PR with
   sign-off markers. (DONE — this PR.)
2. Operator reviews + confirms en bloc OR per-marker.
3. Implementer entrega the audit prompt copy-paste to
   the operator immediately.
4. Codex audits the brief; verdict ferried back via
   the operator. Round 1 typically returns 1-2 P0 + a
   handful of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   triggered when Codex round 1 was CHANGES-REQUIRED
   with P0; APPROVED-with-observations + P1/P2 land
   as in-branch follow-ups.
6. Brief PR merges BEFORE the UI-13 code branch
   opens. Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```
