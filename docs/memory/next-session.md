# Next Session Entry Point

## Status: Phase 4 (deployed surfaces) — FIRST CHUNK CLOSED

main HEAD: `6e283a8` (UI-13 code chunk merged, 2026-05-08).
0 PRs open. 0 branches open (working chunks all merged).

UI-13 code closed cleanly: 9 chunked feat commits + 4
audit-round follow-up fix commits = 13 commits squash-
merged into `6e283a8`. +6982 / -89 LOC across 26 files.
Codex audit closed at round 5 of 5 (rounds 1-4 each
CHANGES-REQ with in-branch follow-ups; round 5 APPROVED
clean). The 20 §11.6 pins from the UI-13 brief
(`ad003db`, PR #108) are now binding implementation
contracts in `main`.

**Phase 4 FIRST CHUNK CLOSED.** The auth surface (scrypt
credentials store + signed-cookie sessions + signed
double-submit CSRF + three-layer trusted-IP derivation +
per-IP/per-cred rate-limit + anonymous-path perimeter +
login surface + SW pre-auth/post-auth cache split + CLI
bootstrap + frontend CSRF auto-attach + caddy/nginx
deploy-runbook) is ready for deployed dogfood.

## Context recap (UI-13 code session 2026-05-07 → 2026-05-08)

1. **PR #109** — UI-13 code chunk. 13 commits squash-merged:
   1. `aec3c33` feat(ui-13): _auth module — credentials
      store + scrypt + primitives (chunk 1, ~830 LOC, 19
      tests)
   2. `00e2b68` feat(ui-13): session + CSRF + Origin
      tests (chunk 2, 28 tests)
   3. `1cc0cb3` feat(ui-13): trusted-IP + rate-limit +
      anonymous path tests (chunk 3, 119 tests)
   4. `2a24ef1` feat(ui-13): server.py wiring — auth
      middleware + login/logout + cookies (chunk 4, 36 tests)
   5. `16cdff5` fix(ui-13): Codex round 1 audit — P0 +
      3xP1 + P2 closed in-branch (10 regression tests)
   6. `79562ab` fix(ui-13): Codex round 2 audit — P1 +
      P2 closed in-branch (3 regression tests)
   7. `ccfb2f2` feat(ui-13): chunk 5 — login visual
      primitive + asset routing fix
   8. `48576c9` feat(ui-13): chunk 6 — sw.js cache split
      + auth:granted/revoked hooks
   9. `4853de7` feat(ui-13): chunk 7 — CLI bootstrap +
      fail-closed startup (16 CLI tests)
   10. `c171724` feat(ui-13): chunk 8 — frontend CSRF
       header attach (1 structural test)
   11. `4b5a71b` feat(ui-13): chunk 9 — deploy-runbook +
       visual artefacts (2 PNGs + Playwright capture)
   12. `a93183b` fix(ui-13): Codex round 3 audit — P0 +
       2xP1 + P2 closed in-branch (11 regression tests)
   13. `253e61e` fix(ui-13): Codex round 4 audit — P0
       closed in-branch (2 regression tests)
   14. (squash merge commit `6e283a8`)

   - Round 1 audit: CHANGES-REQ (1 P0 + 3 P1 + 2 P2).
     P0+3xP1+1xP2 closed in-branch; asset-routing P2
     deferred per Codex's framing → landed in chunk 5.
   - Round 2 audit: CHANGES-REQ (1 P1 + 1 P2). Both closed.
   - Round 3 audit: CHANGES-REQ (1 P0 + 2 P1 + 1 P2). All
     closed (--session-ttl-days implemented; --tls-*
     deferred with runbook rationale).
   - Round 4 audit: CHANGES-REQ (1 P0 — non-loopback bind
     + empty expected_origins refused at startup).
   - Round 5 audit: APPROVED clean.
   - Loop budget: 4/5.
   - Merge: Claude Code lands the merge per
     `feedback_karasu_merge_es_implementer.md`
     (`gh pr merge 109 --squash --delete-branch`).
   - Final test surface: 985 passed + 7 skipped + 2
     pre-existing Windows quirks (CRLF + cwd path;
     documented; NOT regressions). UI-13 contributes
     ~250 new tests across 6 new test files.

2. **PR #110** (this PR) — docs/memory sync after UI-13
   code merge.

## Entry point for THIS session

**Phase 4 — second chunk: UI-14 PWA installable.** UI-13
closed the auth foundation. Per Phase 4 macro brief PR #107
§3-D the binding chunk sequence is:

```text
UI-13 — Remote operator surface             ✔ closed 2026-05-08
UI-14 — PWA installable                     ← next chunk
UI-15+ — Native packaging (CONDITIONAL)     deferred unless
                                            UI-14 dogfood
                                            surfaces a concrete
                                            platform need
```

UI-14 earns "app-like" — web app manifest with proper
icons / theme color / display mode; install prompt posture
(footer affordance, no nag banners per UI-8 audit pin #5);
mobile layout pass; iOS Safari + Android Chrome push
compatibility audit (UI-12c shipped against desktop Chrome
headless); SW update strategy on a deployed surface (the
current `skipWaiting + clients.claim` from UI-8 may need
adjustment when long-running tabs hold the operator's
session). Estimated scope: ~800-1500 LOC including tests
+ docs.

Phase 4.y / later deferred bucket (NOT next-chunk scope):

```text
- Multi-operator authorization — login, session
  management, per-operator audit log filtering, role /
  permission tiers per-user. Phase 4 macro brief §3-B
  last paragraph defers this explicitly to Phase 4.y or
  later: "Multi-operator collaboration / per-user trust
  gradient filtering / operator-scoped audit log is
  explicitly DEFERRED to Phase 4.y or later." UI-13 ships
  single-operator credentials and is intentionally the
  end of single-operator scope.

- Multi-host writer concurrency — the UI-12c §3-G file
  lock is single-filesystem only (fcntl.flock /
  msvcrt.locking semantics over network filesystems are
  not portable). Deployed surfaces with shared storage
  (NFS / multi-instance deployment) need their own
  concurrency contract.

- A2A peer push fan-out — Karasu instance pushing to
  another Karasu instance (vs the UI-12c per-browser
  push).

- Push enhancements (post-UI-12c):
    * Per-event push opt-in beyond the closed enum
      {attention, errors, corrections}.
    * Scheduled / quiet-hours / DND beyond OS-level DND.
    * VAPID auto-rotation (operator-driven today).

- Per-category push debounce override via env var.
  Deferred from UI-12c per brief §10.5.

- Direct-TLS in karasu (--tls-cert / --tls-key) —
  intentionally deferred from UI-13. Sealed UI-13
  production shape is reverse-proxy TLS termination;
  reopens for UI-15+ if dogfood demands it (per
  docs/deploy-runbook.md preamble).
```

### Recommended next move

Open the UI-14 PWA installable chunk-level brief
(doc-only PR, `[NEEDS OPERATOR SIGN-OFF]` markers per
the §3 sub-decision pattern UI-12..UI-13 used). Macro
brief §3-D anchors UI-14 = PWA installable as the binding
next chunk; this brief earns the visual / manifest /
install-posture / mobile-compat / SW-update decisions
that the macro brief defers to chunk level.

Multi-operator authorization is NOT UI-14. The post-UI-13
sync mistakenly named it as such; the 2026-05-08
correction PR (this one) restores the macro binding.
Multi-operator stays in the Phase 4.y deferred bucket
above until dogfood surfaces a concrete need.

### Phase 4 chunk lifecycle

Per the brief-before-code pattern (UI-9 audit pin #1,
reaffirmed UI-10..UI-13):

```text
1. Implementer drafts the chunk-level brief as a
   doc-only PR with [NEEDS OPERATOR SIGN-OFF] markers.
   Inherits the 165 binding pins from UI-0..UI-13
   (126 inherited + 19 Phase 4 macro + 20 UI-13 §11.6).
2. Operator reviews + confirms ("avanzar" or per-marker).
3. Implementer entrega the audit prompt copy-paste to the
   operator immediately.
4. Codex audits; verdict ferried back via the operator.
5. In-branch follow-ups; re-audit if round 1 was
   CHANGES-REQUIRED with P0.
6. Brief PR merges BEFORE the first code branch opens.
   Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```

## Accumulated state

- **165 binding pins inherited** (52 base + 6 UI-10 §0.5 +
  12 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6 + 4
  PR #102 round-2 forward-carry + 20 UI-12c §11.6 +
  20 UI-13 §11.6 + 19 Phase 4 macro).
- **Test suite on main**: 985 passed + 7 skipped + 2
  pre-existing Windows quirks (CRLF + cwd path; documented
  as NOT regressions; verified across UI-13 audit rounds).
- **Lighthouse contract** unchanged from UI-9.1 baseline.
- **Loop budget tracker (last 3 chunks)**:
  - UI-12c brief: 4/5; UI-12c code: 2/5.
  - UI-13 brief: 4/5; UI-13 code: 4/5.

## Open issues

```text
None — F9/F10/F11 (Phase 3 dogfood findings) all
resolved 2026-05-02 (PRs #40/#41/#42; merge commits
0010fed/dd4995c/56a7d7b). Memory sync was deferred
until 2026-05-08 hygiene PR caught the gap.
```

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
- Production dogfood: bring up a real reverse-proxy + TLS
  cert + run `karasu auth set-credentials` against a
  configured `auth.expected_origins` so the deployed
  posture (Secure cookies + Origin/Referer enforcement)
  exercises end-to-end.
```

## Phase / prototype status

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED.
Phase 2 — Git-aware + A2A                 ✔ CLOSED.
Phase 3 — PWA + Advanced                  ✔ CLOSED.
Phase 4 — Deployed surfaces               ⚙ FIRST CHUNK
                                           CLOSED 2026-05-08
                                           by UI-13 PR #109.
                                           Auth surface ready
                                           for deployed
                                           dogfood. Remaining
                                           chunks per "Entry
                                           point for THIS
                                           session" above.
```
