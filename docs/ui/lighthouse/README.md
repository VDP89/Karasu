# Karasu UI — Lighthouse audit contract

Lighthouse runs are **verification, not design driver** (Codex
pin #2 from the UI-8 audit). The thresholds below are the audit
contract from UI-0 §10; a run that falls below them is a P0 for
the chunk that introduced the regression. Lighthouse suggestions
that would add chrome (install prompt component, connection
badge, update toast, generic UX recommendations) are explicitly
out of scope — see "Recommendations to ignore" below.

## Thresholds

| Category | Minimum | Rationale |
|---|---|---|
| Performance | **95** | Operator surface; latency is editorial |
| Accessibility | **95** | WCAG AA pass + focus ring + reduced-motion |
| Best Practices | **95** | No console errors, secure defaults, no deprecated APIs |
| SEO | **90** | Lower bar — no public marketing copy, no JSON-LD, no canonical-tag concerns |

Bumping a threshold up is fine; bumping one **down** requires an
operator-signed rationale recorded in this file with a date and
the chunk that earned the exception.

## How to run

```bash
# Local — spins up the Karasu UI server in a temp dir with a
# seeded synthetic bus, runs Lighthouse via npx, asserts the
# thresholds, writes a JSON report to ./<date>.json.
python scripts/ui_lighthouse.py

# External — point at a deployed Karasu surface.
python scripts/ui_lighthouse.py --url https://karasu.example/

# Include the PWA category (only when the target serves HTTPS).
python scripts/ui_lighthouse.py --include-pwa --url https://karasu.example/
```

The runner exits 0 when every threshold passes, 1 when any
fails. Failing audits print to stderr with their category +
audit id so the operator knows which Lighthouse item to inspect
without opening the JSON.

## Why PWA is skipped by default

Lighthouse's installable-PWA audits require HTTPS. The local
dev server is HTTP, so the PWA category cannot run cleanly
against it.

The PWA contracts UI-8 ships are still verified:

```text
- Service-Worker-Allowed: / header on /assets/sw.js
  → tests/test_ui_server_http.py
- /api/* network-only fetch handler ordering
  → docs/ui/screenshots/UI-8-pwa/README.md (manual DevTools
    verification path)
- /offline.html route + body + .crow.offline class
  → tests/test_ui_server_http.py
- manifest.json colours matching tokens.css
  → tests/test_ui_server_http.py
- manifest.json top-level shape (name / start_url / scope /
  display / icons)
  → tests/test_ui_server_http.py
```

When the operator is auditing a deployed HTTPS surface, the
``--include-pwa`` flag adds the PWA category to the run.

## Recommendations to ignore

Lighthouse routinely surfaces audits that would compromise
Karasu's editorial direction. The list below is the audit's
explicit **ignore list**; Codex pin #2 backs it.

| Lighthouse audit | Why we ignore it |
|---|---|
| `installable-manifest` (when HTTPS unavailable) | Local server is HTTP; manifest itself is correct |
| `pwa-cross-browser` install prompt component | Pin #5 from UI-8 audit: no install banner / toast |
| `apple-touch-icon` warnings | Optional; the 192/512 icons cover the install flow |
| `themed-omnibox` recommendations beyond `theme_color` | Already set; further chrome-tinting is browser-side |
| `service-worker` "include offline-indicator UI" hints | Pin from UI-8 audit: no connection badge / toast |
| `font-display` swap recommendations | UI-2's FOUT-accept-FOIT-reject contract is editorial |
| Generic `unused-css-rules` reports | Hand-written CSS is small; the report's "unused" rules are typically used by states the audit didn't visit (focus-visible, hover, reduced-motion) |
| `meta-description` SEO suggestions | Operator surface, no public copy; SEO 90 bar is intentional |
| `crawlable-anchors` for the design-system page | `/design-system` is unlinked by design |

If Lighthouse surfaces a NEW recommendation that would add
chrome, the answer is "no" until the operator + Codex audit
sign off on it. Code review must reject PRs that add visual
affordances purely to chase a Lighthouse score.

## Reports

Each `<YYYY-MM-DD>.json` in this directory is a full Lighthouse
run (e.g. `2026-05-04.json`). The latest report is the baseline;
older reports are kept so regressions are diffable across
chunks.

The runner writes `YYYY-MM-DD.json` (UTC date at run time); if
a run on the same day overwrites a previous one, that's
deliberate — one canonical report per day.

## 2026-05-04 baseline — known threshold deviation

The first Lighthouse run against the UI-9 stack landed:

```text
performance       81 /  95  FAIL
accessibility     95 /  95  PASS
best-practices    96 /  95  PASS
seo               90 /  90  PASS
```

The performance miss is structural, NOT a regression. The
failing audits split into two buckets:

```text
Editorial — DO NOT fix (Codex pin #2 + UI-0 §4):
  unminified-css                   hand-written; no build step
  unminified-javascript            inline <script>, no bundler
  render-blocking-resources        multiple <link rel="stylesheet">
                                    is the editorial choice; a
                                    bundler would add chrome
  largest-contentful-paint-element first-paint hero is the crow
                                    SVG, the editorial mark
                                    itself; "fixing" it would
                                    mean defacing the brief

Server-side — pin-aligned, requires operator sign-off:
  uses-text-compression            gzip on text/* responses
  uses-long-cache-ttl              Cache-Control on /assets/*
  cache-insight                    same as above
```

The server-side bucket is the candidate for a UI-9 follow-up
or a UI-10 micro-chunk. Both are 1-line changes inside the
existing static-asset handler in `src/karasu/ui/server.py` and
do NOT add any chrome — they would only change response
headers / encoding. Estimated lift: Performance ≈ 92-95
post-fix.

Why the pin-aligned fix is NOT applied automatically:

```text
- UI-9 charter is verification-only; touching server.py
  exceeds scope.
- Codex pin #1 from UI-9 audit (PR #81): UI-10+ requires
  an operator-signed brief. Even a micro-chunk needs the
  sign-off.
- The threshold contract above explicitly says:
  "Bumping a threshold DOWN requires operator-signed
   rationale recorded in this file with a date and the
   chunk that earned the exception."
  The same gate applies to bumping UP via a code change.
```

Operator decision pending: apply the gzip + cache headers as
a UI-9 follow-up (justifiable: the README documented the
opportunity in next-session.md before the run), open a
dedicated micro-chunk, or accept the 81 Performance with a
documented exception here. Until the decision lands, the
baseline is the snapshot above.

## When to bump CACHE_NAME (cross-reference)

UI-8 ships a service worker with `CACHE_NAME = 'karasu-ui-v8'`.
Bump triggers documented in `src/karasu/ui/static/sw.js`
docstring AND in `docs/ui/screenshots/UI-8-pwa/README.md`. A
Lighthouse run can also surface a stale-cache issue (Best
Practices > "uses-http2", "no-vulnerable-libraries") if the
cached shell drifts from the current code. Bump the version,
re-run Lighthouse, expect the score to recover.
