# UI-11b - Trust Write

PNG set required by the UI-11b definition of done.

## 00-drawer-with-adjust.png

- Drawer is opened from an `agent_response` event.
- `trust_level: 1` is visible.
- Adjust appears only inside the drawer; no toolbar or `/agents` page exists.

## 01-modal-default.png

- Adjust opens the reused `.modal` primitive.
- Copy says `Recorded intent. Applies after watch restart.`
- Options are limited to `0`, `1`, and `2`.

## 02-modal-with-reason.png

- Raising from `1` to `2` is deliberate and confirmed in the modal.
- Optional reason is visible before confirm.

## 03-modal-reduced-motion.png

- Same modal state under `prefers-reduced-motion: reduce`.

## 04-post-confirm-annotation.png

- Drawer remains on the original `agent_response`.
- Post-confirm text reads as recorded intent, not live mutation.
