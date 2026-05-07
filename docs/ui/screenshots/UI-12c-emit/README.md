# UI-12c — server-side push emit

Visual artifacts for the UI-12c chunk (PR #105). Brief
§7.3 + pin §11.6.10 carry-forward + Codex P2 round 1
binding (UI-12c brief audit).

## Capture form — OPTION B (deterministic browser-side mock)

Codex P2 round 1 of the brief audit accepted two forms for
the notification render:

  * **OPTION A** — real OS tray PNG via Playwright. Works on
    macOS / linux desktops where the tray is browser-controlled.
    Brittle on Windows / headless CI.
  * **OPTION B** — deterministic browser-side notification
    mock PNG. Stable across platforms; loses the "real OS
    tray" feel but proves the SW handler renders the
    documented title strings.

UI-12c shipped the `karasu watch` server-side emitter on
Windows; the OS tray render is OS-specific and outside
Karasu's design system (the SW push handler hands off to
`registration.showNotification`, the OS draws the chrome).
The capture script (`scripts/ui_screenshots.py`) injects an
HTML overlay that mirrors the `§3-H` title contract exactly —
the audit gate is "the title strings the SW push handler
renders match the brief", not "the chrome looks like macOS"
or "the chrome looks like Windows".

The `.webm` at `docs/ui/recordings/UI-12c-emit.webm` IS the
operator-felt audit (pin §11.6.10 carry-forward); these PNGs
are provenance.

## Files

| File                              | Category    | Title                                     |
|-----------------------------------|-------------|-------------------------------------------|
| `00-notification-attention.png`   | attention   | "Karasu paused — operator review needed." |
| `01-notification-errors.png`      | errors      | "An adapter failed."                      |
| `02-notification-corrections.png` | corrections | "A scar was recorded out-of-band."        |

The strings are byte-for-byte the values in
`src/karasu/push_emit/_dispatch.py::_TITLES`. A brief change
to the title contract requires both the source dict + these
PNGs to update; the test suite asserts the source side
(`test_push_emit_dispatch.py::test_payload_carries_attention_title`).

## Regenerate

```bash
# PNGs
python scripts/ui_screenshots.py UI-12c-emit

# .webm
python scripts/ui_screenshots.py UI-12c-emit --record-video
```

The capture plan lives in
`scripts/ui_screenshots.py::CAPTURES["UI-12c-emit"]` (PNGs)
and `scripts/ui_screenshots.py::RECORDINGS["UI-12c-emit"]`
(`.webm`).
