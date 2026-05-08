# UI-14 mobile-viewport audit (§3-D)

Captured by `scripts/ui_14_mobile_audit.py` in headless
Chromium against an in-process Karasu UI server with auth
enabled (ephemeral creds inside a tempdir, mirrors
`scripts/ui_13_capture.py`).

The brief seals four mobile widths: **320 / 360 / 375 / 414**.
For each width three surfaces are captured:

1. **Login (pre-auth)** — UI-13 territory; UI-14 made zero
   login changes. The four PNGs are a sanity check that the
   manifest body / theme-color / SW lifecycle changes have
   not regressed the login render at narrow widths.
2. **Shell default state (post-auth)** — UI-14 added a fifth
   slot to the footer (`.footer-install`). At default the
   slot reads `Install: <state>` where `<state>` is whatever
   `decideState()` resolves to; in headless Chromium without
   `beforeinstallprompt` the resolution is `unsupported`.
3. **Shell update state forced (post-auth)** — JS injection
   forces the slot into the §3-F refresh state so the
   §11.6.9 mutual-exclusion winner (Refresh button visible)
   is captured at every width. This is the most-chrome
   layout the slot ever shows.

## File map

| File                              | Width × Height | Surface             |
|-----------------------------------|----------------|---------------------|
| `00-login-320.png`                | 320 × 568      | login (pre-auth)    |
| `01-login-360.png`                | 360 × 640      | login (pre-auth)    |
| `02-login-375.png`                | 375 × 667      | login (pre-auth)    |
| `03-login-414.png`                | 414 × 736      | login (pre-auth)    |
| `04-shell-default-320.png`        | 320 × 568      | shell, default      |
| `05-shell-default-360.png`        | 360 × 640      | shell, default      |
| `06-shell-default-375.png`        | 375 × 667      | shell, default      |
| `07-shell-default-414.png`        | 414 × 736      | shell, default      |
| `08-shell-update-320.png`         | 320 × 568      | shell, update state |
| `09-shell-update-360.png`         | 360 × 640      | shell, update state |
| `10-shell-update-375.png`         | 375 × 667      | shell, update state |
| `11-shell-update-414.png`         | 414 × 736      | shell, update state |

## Audit verdict (2026-05-08)

§3-D SEALED policy: the `<360px` breakpoint is applied
**only if screenshots demand**. The 12 captures above
demonstrate the surface holds at every sealed width
without requiring a new breakpoint:

- **320 px** — the narrowest sealed viewport. The footer
  wraps cleanly to three lines: `v0.1.0 | no events yet |
  crow: idle` on row 1, `Notifications: denied` on row 2,
  `Install: <state>` on row 3. The flex-wrap divider
  rule (`.shell-footer .meta + .meta { border-left: 1px
  solid var(--fg-3) }`) survives the wrap correctly. In
  the update state, the row-3 line `Install: Update
  available. [Refresh]` fits within the 320 px width with
  the Refresh button hugging the right edge — no
  overflow, no second wrap, no clipping.
- **360 px** — same three-line wrap as 320 px with more
  horizontal margin around every slot. No layout change.
- **375 px** — same three-line wrap. Comfortable.
- **414 px** — the footer compacts to two lines (rows 1 +
  2 of the 320 px wrap merge into a single row that fits
  the wider canvas). Update state still single-row.

The login surface (UI-13 sealed) renders identically at
every width: hero crow centered above the username +
password fields, primary `Enter` button. UI-14's manifest
body change (theme-color → `--bg-0`, expanded icons array)
introduces zero visible login regression — the login
render reads the same tokens UI-13 sealed.

**Decision: no `<360 px` breakpoint required.** The
`@media (max-width: 720px)` rule UI-3 already ships
(`padding-left: var(--space-4); padding-right:
var(--space-4)` on `.shell-header` / `.shell-footer`)
is sufficient down to 320 px. Codex audit may revisit
this verdict; if it does, evidence lives in this PNG set
and the §3-D follow-up commit lands inside the UI-14
branch (not as a UI-15 carry-forward).

## Reproducing

From the repo root with Playwright + Chromium installed:

```bash
python scripts/ui_14_mobile_audit.py
```

The script tears its server + tempdir down on exit. PNG
bytes are reproducible across runs as long as the
Chromium version + tokens.css + index.html shell stay
stable; a Chromium upgrade may shift glyph antialiasing
and rebaseline the captures. There is no golden hash
test on these artefacts — the audit is visual, the
verdict above is the lock.
