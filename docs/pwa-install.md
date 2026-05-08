# Installing Karasu as a PWA

Karasu ships as a Progressive Web App. Once installed, it
opens in its own window with no browser chrome, survives
across sessions, and (on platforms that support it) can
deliver Web Push notifications when something on the bus
needs your attention.

This page is the operator-facing walk-through. It is the
authoritative source for two things:

1. **How to install** Karasu as a PWA on each platform.
2. **What push notifications can and cannot do** on each
   platform — most importantly, the iOS Safari constraint
   that makes Web Push unreachable from a regular browser
   tab.

The corresponding code surface is sealed by `docs/ui/ui-14-design-brief.md`
§3-B (install affordance), §3-E (iOS push gating), and
§3-F (SW update lifecycle). When this page and the brief
disagree, the brief wins; please file an issue and the
walk-through gets corrected on the next chunk.

---

## 1 — Why install

The browser-tab posture is fine for trying Karasu. The
installed posture is what you want once Karasu is part of
your day:

- The window has no browser chrome — the editorial calm of
  the surface reads cleaner.
- The PWA tile lives on your home screen / dock, one tap /
  click from awake.
- Web Push notifications work on every supported platform
  the moment you opt in (UI-12c). On **iOS Safari**, push
  works **only** after install — the platform gates the
  Push API behind A2HS as of iOS 16.4 (March 2023). This
  is an Apple decision, not a Karasu bug.
- Service worker updates land on a cadence you control via
  the footer "Update available." line (§3-F SEALED). You
  see the affordance, you click Refresh, the new shell
  takes over.

---

## 2 — Per-platform install

The install affordance lives in the footer of the
authenticated shell, in the same family as `Notifications:`
and `crow:`. Its label is one of four states (§3-B SEALED):

| State         | What you see                              | What to do |
|---------------|-------------------------------------------|------------|
| `unsupported` | quiet `Install: unsupported` in muted fg  | nothing — the platform has no install path |
| `available`   | accent `Install: available`               | click the line; the OS install dialog opens |
| `ready`       | accent `Install: ready (Share → Add to Home Screen)` | follow the inline hint |
| `installed`   | quiet `Install: installed`                | nothing — you are running inside the PWA |

### 2.1 Android Chrome

Open Karasu in Chrome and log in. The footer flips to
`Install: available` once Chrome has captured enough
engagement signals (a handful of seconds of interaction
on first visit; immediate on repeat visits).

Click the line. The Chrome install dialog opens with
"Install Karasu" pre-filled. Confirm. The PWA tile lands
on your home screen.

If you ignore the affordance, Chrome will eventually
present its own install banner via the address bar
(three-dot menu → "Install Karasu"). The footer line and
the address-bar entry point do the same thing under the
hood; pick whichever is closer to your hand.

### 2.2 Desktop Chrome / Edge

Same shape as Android Chrome: the footer flips to
`Install: available`, click to install. The PWA opens in
its own window from your launcher / start menu.

### 2.3 iOS Safari (iPhone / iPad)

The browser does not fire `beforeinstallprompt` on iOS, so
Karasu cannot trigger an install dialog from JS. The
footer reads `Install: ready (Share → Add to Home Screen)`
to remind you of the manual gesture:

1. Tap the **Share** icon in Safari's bottom bar (square
   with an upwards arrow).
2. Scroll the share sheet down to **Add to Home Screen**.
3. Confirm. The Karasu icon lands on your home screen.

After install, open Karasu from the home-screen icon (not
from a Safari tab) so iOS opens it as a standalone PWA.
You will see `Install: installed` in the footer and the
push slot will be reachable per § 3.2 below.

### 2.4 Desktop Safari (macOS 13+ Ventura)

Safari on Ventura supports installing PWAs to the dock via
**File → Add to Dock…**. Pick a name (`Karasu` is the
default), confirm, and the dock entry appears. From there
the PWA opens in its own window like any other dock app.

Older macOS Safari versions do not support PWA install.
The footer reads `Install: unsupported` on those builds
and the operator has no install path; use Chrome / Edge if
you need the installed posture on a pre-Ventura Mac.

### 2.5 Firefox (any platform)

Firefox does not implement the install affordance the way
Chromium does, and Karasu does not document a Firefox
install flow. The footer reads `Install: unsupported`.
Karasu still works as a regular Firefox tab — push
notifications via Firefox are best-effort and not gated by
the §3-E binding (UI-14 audits Chrome / Edge / Safari).

---

## 3 — Per-platform push notifications

The push opt-in surface (UI-12b) lives in the same footer
as the install affordance, labelled `Notifications:`. Like
the install slot it has four states; the relevant one for
this section is `unsupported`.

### 3.1 Android Chrome (tab OR installed)

Push works in **both** postures. The footer flips to
`Notifications: off` on first visit; click to opt in.
Chrome shows the OS permission prompt; accept and the slot
flips to `Notifications: on`. The §3-E binding does not
gate Android push behind install — both shapes are
audited.

### 3.2 iOS Safari (installed PWA only)

In a regular Safari **tab**, the footer reads
`Notifications: Install Karasu first`. This is the §3-E
SEALED pointer copy: iOS gates the Push API behind A2HS,
so subscribing from a tab is structurally impossible —
`PushManager` is not exposed on `window`. Karasu does not
fake support; the pointer points you back to § 2.3.

After A2HS install, open Karasu from the home-screen
icon. `navigator.standalone === true` flips on, the push
detector finds `PushManager`, and the footer reads
`Notifications: off`. Click to opt in normally; Apple's
push service handles the rest.

If you tap a Karasu home-screen icon and the URL bar is
visible, you opened a Safari tab pointing at the
home-screen URL, not the standalone PWA. Long-press the
icon, choose **Edit Home Screen → Open in Standalone**
(or re-add to Home Screen) to fix the launcher record.

### 3.3 Desktop Chrome / Edge (tab OR installed)

Push works in both postures. Same shape as Android Chrome:
click `Notifications: off`, accept the OS prompt, the slot
flips to `Notifications: on`.

### 3.4 Desktop Safari (macOS 13+ Ventura, installed)

Push works once the PWA is added to the dock per § 2.4.
Pre-Ventura Safari does not support Web Push at all and
the slot reads `Notifications: unsupported`.

### 3.5 Firefox (any platform)

Best-effort. Karasu does not gate or audit Firefox push;
the slot reflects what `PushManager` / `Notification`
report.

---

## 4 — Updates after install

Once installed, the SW (service worker) keeps the shell
fresh in the background. UI-14 §3-F SEALED replaces UI-8's
eager `skipWaiting + clients.claim` with an explicit opt-in
flow:

1. The new SW installs as `waiting`. Open tabs continue
   serving from the previous SW.
2. The page polls `registration.update()` every 60 minutes
   (and on every navigation event the browser fires its
   own check).
3. When a new SW is waiting, the install slot in the
   footer family flips to `Update available. [Refresh]`.
   The install line yields per §11.6.9 mutual-exclusion —
   you see one affordance at a time.
4. Click `Refresh`. Karasu posts `SKIP_WAITING` to the
   waiting SW, the SW takes over, and the page reloads
   into the new shell.

The reload is the only side effect of the SW update — your
session cookie survives, your bus path survives, the
post-auth cache reseeds lazily on first navigation under
the new SW.

If you ignore the `Refresh` affordance, the new SW takes
over the next time you open Karasu fresh (no existing tab
controlling). There is no forced reload; UI-14 traded
UI-8's aggressiveness for editorial calm on a deployed
PWA an operator may keep open across sessions.

---

## 5 — Troubleshooting

- **The install slot reads `unsupported` in Chrome.**
  Chrome needs engagement signals before it will fire
  `beforeinstallprompt`. Visit Karasu twice, leave the
  surface focused for ~30 seconds total, and the slot
  should flip on the next refresh. If it stays
  `unsupported` after that, the manifest may be cached
  stale — see §3-F update flow above to reload under the
  current SW.
- **The iOS share sheet does not show "Add to Home Screen".**
  You opened Karasu from a non-Safari iOS browser
  (Chrome / Firefox / Edge on iOS all run on top of
  WebKit but suppress A2HS). Open the Karasu URL in
  **Safari** specifically.
- **`Install: installed` shows but the address bar still
  appears.** You opened the home-screen URL in a Safari
  tab instead of via the standalone launcher. Re-tap the
  home-screen icon (long-press → Open) so iOS treats it
  as the PWA, not as a tab shortcut.
- **`Notifications: Install Karasu first` shows on
  desktop Safari.** Desktop Safari uses dock-installed
  PWAs (§ 2.4) — until you File → Add to Dock, the slot
  treats your session as the iOS-tab equivalent.
- **The push slot stays `denied` after I opt in.** You
  declined the OS prompt, or browser-side notification
  permissions are off for your origin. Open the browser's
  site settings (Chrome: 🔒 in the address bar →
  Notifications) and re-grant; reload Karasu.

If something still doesn't add up, the binding contracts
live in `docs/ui/ui-14-design-brief.md` §3-B / §3-E /
§3-F. The brief is the source of truth; this page is the
operator translation layer.
