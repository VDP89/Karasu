# UI-11a — Trust Display

Single PNG required by the UI-11a definition of done.

## 00-drawer-trust-visible.png

What to verify:

- The drawer is opened from an `agent_response` event.
- `trust_level: 2` is visible as its own read-only row below the drawer header.
- There is no Adjust button, modal, toolbar affordance, or `/agents` page.
- The JSON projection includes `action: null`, proving UI-11a's additive projection field is visible without changing the rest of the shape.

UI-11b earns the write affordance separately.
