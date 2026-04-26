# Roadmap

## Phase 1 — Local daemon + Telegram (current)

The minimum loop that lets a human run Karasu against a single
repository from a phone.

- Filesystem watcher (`watchdog`) with config-driven ignore list
- Rule-based event classifier
- Agent adapters: Claude Code (CLI) and Codex (GitHub API)
- Trust gradient (0–3) per agent, per category
- Telegram bot for mobile interaction
- Scar engine for correction memory
- JSONL event persistence under `.karasu/events.jsonl`

**Exit criteria.** A user can `pip install -e .`, configure one
adapter, run `karasu watch`, edit a file, and receive the agent's
response in Telegram.

## Phase 2 — Git-aware + A2A

Lift the trigger surface from "files on disk" to "events in the
software lifecycle".

- Git hook listener (pre-commit, post-commit, post-merge)
- GitHub webhook receiver
- A2A Agent Cards for agent discovery and capability negotiation
- Auto-detect a Codex review on a PR and create a Claude Code task
  to address it
- CI/CD with GitHub Actions on the Karasu repository itself

**Exit criteria.** A reviewer comment posted on GitHub triggers a
Claude Code task without any human in the loop until the resulting
patch needs approval.

## Phase 3 — PWA + Advanced

Replace the Telegram interface with a branded surface and expose
the system's internals to the human.

- Progressive Web App (installable, offline-capable)
- Trust level management UI
- Correction history visualization (browse and revoke scars)
- Dashboard with event timeline
- Push notifications

**Exit criteria.** A user can manage trust levels and inspect scars
from the PWA without touching the config file or the JSONL log.
