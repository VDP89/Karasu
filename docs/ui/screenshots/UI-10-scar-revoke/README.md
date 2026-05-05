# UI-10 — Scar revoke flow screenshots

The first write path on the operator surface. The drawer
(UI-7) extension shows active scars on `human_decision`-typed
events; clicking inline `Revoke` opens the confirmation modal
(`.modal` primitive, brief §5.2). Confirming the modal POSTs
`/api/scars/{id}/revoke`, which appends a revoke record to
`scars.jsonl` and emits a `human_decision` event with
`data.action="scar_revoke"`.

The recording lives at
`docs/ui/recordings/UI-10-scar-revoke.webm` (~437 KB, 1024×640)
and walks the full operator flow in one Playwright context:
boot with two active scars seeded → click timeline row →
drawer opens with active scars section → click first Revoke
button → modal opens → type reason → click Revoke → modal
closes → drawer re-fetches `/api/scars` and renders the empty
branch (the second scar was the one we revoked; the first
remains active in the test corpus).

## Audit anchor — pin §11.6.6

Codex pinned an explicit operator-feel test on the
implementation `.webm`:

> *"does the click → modal → confirm flow read as a deliberate
> action against ScarEngine, or as ticking a checkbox in a
> settings panel?"*

If the recording reads as the latter, that is a P0 — the
editorial pin is binding (brief §3.5 + §11.5). The 1024×640
viewport per UI-3 audit pin #5 keeps the entire shell visible
so the auditor can confirm the modal sits ABOVE the existing
drawer rather than replacing it.

## PNGs in this directory

| File | Captures |
|------|----------|
| `00-drawer-with-revoke.png` | Drawer opened on the seeded `human_decision` event. The active-scars section is visible below the JSON body with TWO inline Revoke verbs. Pin §11.6.1 verified: revoke lives only inside the existing drawer; no toolbar / floating button. |
| `01-modal-default.png` | Modal opened by clicking the first Revoke button. Title (`Revoke this scar?`), editorial lede, scar correction quote in mono, optional reason textarea, Cancel + Revoke buttons. The Cancel button has the focus ring (operator never confirms by accident). |
| `02-modal-with-reason.png` | Modal with the reason textarea populated. The textarea grows vertically; the modal does not push off-screen. |
| `03-modal-reduced-motion.png` | Modal under `prefers-reduced-motion: reduce`. The backdrop's opacity transition is NOT on the UI-2 chromatic whitelist, so it becomes effectively instant under this media. The audit verifies the structural integrity (no half-faded backdrop, no flicker). |
| `04-post-revoke-surface.png` | Post-revoke surface — the just-revoked scar disappeared from the active-scars list; one row remains. Pin §11.6.4 verified: operator MUST see the revocation, not infer it from the timeline. |
| `05-modal-revoke-hover.png` | Optional hover state on the destructive button (encouraged but not blocking by brief §11). The `--danger` token's hover alias darkens via `color-mix`; pinning a regression baseline for the future. |

## Editorial check — pin §3.5 reaffirmed

The brief's operator pin (binding 2026-05-04) shapes the
visual surface:

- **Mutation explicit** → modal is non-skippable. The
  `00-drawer-with-revoke.png` capture shows there is NO
  inline-confirm shortcut next to the Revoke verb; the modal
  IS the friction.
- **Reversible only if the backend supports it** → no Undo
  button anywhere. The post-revoke PNG simply removes the
  row; the bus is the audit log.
- **Visually quieter than the read-only watchtower** →
  `--danger` token is the only chromatic delta vs UI-9; the
  destructive button uses it sparingly (single fill, no
  glow, no scale, no animation). The drawer scars section
  is editorial, not dashboard chrome.

## Frozen contracts — verified by the captures

- The surface = sink invariant from UI-1..UI-9 holds: every
  visual mutation in UI-10 derives from a `human_decision`
  event written through the documented endpoint, never
  through direct DOM mutation that bypasses the bus.
- The 28 binding pins from UI-2..UI-9.1 carry forward —
  fonts, palette, spacing scale, motion durations, focus
  ring all reuse the same tokens.
- The `--danger` semantic alias (introduced by UI-10) ships
  as the same hex as `--accent`; the alias IS the contract
  per Codex P2 binding from PR #83.
