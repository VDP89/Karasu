# Karasu UI — Win95 Runtime Mockup Spec

Status: draft design memory
Branch context: `feat/ui-1-runtime`

## 1. Design intent

Karasu's UI should not treat the crow as a mascot. The crow is the visible cursor of the message bus: a 16-bit messenger that makes agent-to-agent flow legible inside a Windows 95-style runtime surface.

The visual model follows the repository identity:

- Karasu connects agents the user already runs.
- Karasu watches, routes, and reports.
- The human enters when the system needs a decision.
- The future PWA must expose timeline, trust management, correction history, scars, and notifications.

Therefore, the crow sprite must encode state and direction, not decoration.

## 2. UI style decision

Canonical UI style:

- Windows 95 / early desktop runtime
- 16-bit visual language
- beveled panels
- flat gray surfaces
- hard pixel edges
- no modern gradients
- no soft shadows
- no floating mascot treatment

Core palette:

| Element | Color |
| --- | --- |
| Desktop gray | `#C0C0C0` |
| Window light edge | `#FFFFFF` |
| Window dark edge | `#808080` |
| Deep shadow | `#404040` |
| Text | `#000000` |
| Active title blue | `#000080` |
| Highlight text | `#FFFFFF` |
| Warning yellow | `#FFD84A` |
| Error red | `#FF3B3B` |
| Active blue | `#66A8FF` |

## 3. Product metaphor

Karasu is a runtime console, not a SaaS dashboard.

Closest references:

- Windows 95 utility window
- old system monitor
- small local daemon control panel
- retro agent bus inspector

Avoid:

- game HUD
- anime mascot
- modern glassmorphism
- generic chatbot UI
- decorative bird animation

## 4. Main window mockup

```text
┌────────────────────────────────────────────────────────────┐
│ Karasu Runtime v0.x                              [_][□][X] │
├────────────────────────────────────────────────────────────┤
│ File  View  Agents  Memory  Help                          │
├───────────────┬───────────────────────────┬────────────────┤
│ AGENTS        │ MESSAGE BUS               │ KARASU         │
│───────────────│───────────────────────────│────────────────│
│ ▣ Claude      │ 12:03 dispatch.task       │                │
│ ▣ Codex       │ 12:04 audit.return        │      [sprite]  │
│ ▣ GitHub      │ 12:05 webhook.received    │                │
│ ▣ Memory      │ 12:06 scar.detected       │ State: waiting │
│               │                           │ Route: none    │
├───────────────┴───────────────────────────┴────────────────┤
│ EVENT LOG                                                   │
│ > watcher.file_changed                                      │
│ > router.dispatch: Claude -> Codex                          │
│ > adapter.codex.review_started                              │
│ > reporter.waiting_for_human                                │
└────────────────────────────────────────────────────────────┘
```

## 5. Window zones

### 5.1 Agents panel

Purpose: fixed list of active endpoints.

Baseline nodes:

- Claude
- Codex
- GitHub
- Memory
- Human

Each node can show:

- enabled / disabled
- trust level
- current role
- last event timestamp

### 5.2 Message Bus panel

Purpose: the primary place where Karasu movement makes sense.

The crow should travel through or above this zone during route transitions.

Examples:

```text
Claude  ───────►  Codex
        Karasu flies right
```

```text
Claude  ◄───────  Codex
        Karasu flies left
```

### 5.3 Karasu panel

Purpose: compact current-state inspector.

This panel is not a cage for the mascot. It is the fallback location when Karasu is not actively crossing the message bus.

It shows:

- current sprite frame
- current state
- current route
- last significant event

### 5.4 Event Log

Purpose: textual truth source. Every visible Karasu animation must correspond to a logged event.

Rule: no animation without event.

## 6. Karasu sprite system

Sprite style:

- 16-bit, not 8-bit
- readable at small size
- black crow body
- limited animation frames
- hard pixel edges
- no anti-aliasing
- no soft lighting

Recommended base sprite canvas:

- 32x32 px canonical for UI use
- 16x16 px icon fallback
- 64x64 px inspection / empty state

Reasoning:

- 16x16 is too small for the main runtime panel.
- 32x32 preserves retro clarity while allowing recognizable crow posture.
- 16x16 remains valid for tray, timeline, and log icons.

## 7. Required sprite poses

### 7.1 Idle

Meaning: daemon alive, no active route.

Visual behavior:

- perched / standing
- low motion
- optional blink every few seconds
- neutral yellow eye

Use when:

- no active message transfer
- watcher is running
- system is stable

### 7.2 Watching

Meaning: watcher active, no dispatch yet.

Visual behavior:

- same base pose as idle
- subtle head/eye movement
- no walking
- no flying

Use when:

- file watcher / webhook listener is armed
- system has no pending action

### 7.3 Fly right — Claude to Codex

Meaning: dispatch from reasoning/audit context toward execution or implementation.

Visual behavior:

- crow flies right across Message Bus
- compact wing motion
- no exaggerated flapping
- optional small envelope / payload pixel only if readable

Use when:

- router dispatches task to Codex
- Claude output becomes Codex work item

### 7.4 Fly left — Codex to Claude

Meaning: audit return, review result, or correction routed back.

Visual behavior:

- mirrored right-flight pose
- slightly slower return motion acceptable
- visual direction must be unmistakable

Use when:

- Codex review returns to Claude
- audit result becomes reasoning task

### 7.5 GitHub hop

Meaning: webhook / PR / commit event.

Visual behavior:

- short hop rather than long flight
- one bounce between GitHub node and bus
- can include single exclamation pixel on arrival

Use when:

- webhook received
- PR event detected
- commit event detected

### 7.6 Processing

Meaning: internal work in progress; no human action required.

Visual behavior:

- crow remains near destination node or Karasu panel
- blue eye
- contained 2–3 frame loop
- no movement across the bus

Use when:

- adapter is working
- classifier/router is resolving
- response is being formatted

### 7.7 Waiting for human

Meaning: Karasu needs a human decision.

Visual behavior:

- still pose
- stronger yellow eye
- no animation except rare blink
- posture should feel attentive, not cute

Use when:

- trust level requires approval
- conflicting correction requires confirmation
- system asks whether to store a scar

### 7.8 Notification / caw

Meaning: important event surfaced to human.

Visual behavior:

- one-frame beak open or caw mark
- small motion pulse
- short duration
- no loop

Use when:

- push notification equivalent
- user-facing report is emitted

### 7.9 Scar / memory

Meaning: stored correction or repeated pattern detected.

Visual behavior:

- small glitch in the crow silhouette
- double-eye or pixel offset
- no red eye unless it is also an error
- must feel like memory, not failure

Use when:

- correction memory matched
- prior human override applies
- scar is offered or used

### 7.10 Error

Meaning: technical failure.

Visual behavior:

- red eye
- short shake
- no dramatic collapse
- no explosion / cartoon failure

Use when:

- adapter error
- webhook invalid
- dispatch failed
- reporter failed

## 8. Motion grammar

Rule: Karasu only moves when the event bus moves.

| Event class | Motion |
| --- | --- |
| watcher armed | idle / watching |
| dispatch Claude -> Codex | fly right |
| audit Codex -> Claude | fly left |
| GitHub webhook | hop from GitHub node |
| adapter processing | contained processing loop |
| trust approval needed | waiting still pose |
| report emitted | caw / notification pulse |
| scar matched | glitch / memory pulse |
| error | red-eye shake |

## 9. Interaction with logs

Every animation must be traceable to a line in the runtime log or event timeline.

Example:

```text
12:03:11 router.dispatch source=claude target=codex
12:03:11 ui.karasu.motion fly_right
```

No idle animation should imply work that is not happening.

## 10. Design constraints

Hard constraints:

- Karasu is not always active.
- Karasu must not compete with logs.
- Karasu must not become a decorative pet.
- Karasu movement must encode source, destination, and state.
- Scar and correction memory must have a distinct visual state.
- Waiting must be visually quiet but semantically strong.

## 11. Mockup variants to produce next

The next visual sheet should contain:

1. Full Windows 95 runtime screen.
2. Message bus strip with Claude, Codex, GitHub, Memory, Human.
3. Karasu sprite sheet in 32x32:
   - idle
   - watching
   - fly right
   - fly left
   - GitHub hop
   - processing
   - waiting
   - notification / caw
   - scar
   - error
4. State-to-event legend.
5. One example timeline showing Claude -> Codex -> Claude -> Human.

## 12. Decision record

Accepted:

- Windows 95 / 16-bit UI direction.
- Karasu as messenger/cursor of the event bus.
- 32x32 primary sprite size, 16x16 fallback.
- State-driven animation only.
- Visual memory/scar state as first-class product feature.

Deferred:

- Final sprite artwork.
- Exact frame count per animation.
- React/CSS implementation.
- PWA layout code.
- Sound design for caw notification.
