# UI-1 — rebase + cleanup screenshots

## ⚠ Screenshot waiver — ONE-TIME EXCEPTION

UI-0 design brief §7 mandates screenshots for every UI-N PR.
**This PR (UI-1) is a formal one-time exception** absorbed by
the round-1 audit on PR #63: no new visible state is
introduced, the static `index.html` is verbatim from the
cherry-picked commits, and the sandbox capturing this PR did
not have a browser available.

The exception holds because UI-1's surface change is 100% on
the JSON projection (text, no pixels):

- `_project_event` in `server.py` was expanded to surface the
  chunk-4c bus fields (`priority`, `controller_chain_depth`,
  `controller_resubmit`, `resubmit_origin`, `github_*`,
  `agent`, `status`, `trust_level`, `correlates`,
  `classification`, `requires_human`).
- The HTML stub at `static/index.html` was NOT modified by
  this PR. It renders the same way it did on
  `feat/ui-1-runtime` before the rebase.

Every subsequent UI-N PR (UI-2 onward) MUST ship real PNG
screenshots; the waiver does not extend.

## How the operator captures locally

```bash
pip install playwright
python -m playwright install chromium
python scripts/ui_screenshots.py UI-1-rebase
```

The script (`scripts/ui_screenshots.py`) seeds a temporary
`events.jsonl` with four synthetic events covering the major
chunk-4c shapes (watcher, agent_response, github webhook,
controller resubmit), starts `karasu.ui.server` against that
bus, and writes PNGs to this folder.

If the operator runs the script and commits the resulting
PNGs, this README's waiver becomes redundant — leave it for
record.

## Text evidence — `/api/events` projection against synthetic bus

Verified via curl smoke test in this PR's sandbox. The four
synthetic events project as:

```text
evt001 (file_change, source=watcher)
  priority=normal, classification=code_change

evt002 (agent_response, source=adapter)
  priority=normal, agent=claude_code, trust_level=1,
  status=completed, correlates=evt001, requires_human=false

evt003 (file_change, source=github_webhook)
  priority=high, github_event=pull_request_review_comment,
  github_action=created, github_pr=42,
  github_repo=VDP89/Karasu-, github_author=reviewer1

evt004 (file_change, source=controller)
  priority=high, controller_resubmit=True,
  resubmit_origin=evt001, controller_chain_depth=1
```

`/api/health` returns
`{"status":"ok","events":4,"crow":"processing"}` (latest
event is a `file_change`, so the crow surfaces "processing").

This is the contract UI-2..UI-9 will render against.

## Bus event shape — verification (round-1 audit follow-up)

Round-1 audit flagged a possible projection bug: that
`dispatch` / `response` might live under `data` rather than
at the event root. Verified directly against the `Event`
dataclass in `src/karasu/eventbus/jsonl_bus.py`:

```python
@dataclass
class Event:
    type: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    dispatch: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=_now)
```

`asdict(event)` serialises with `dispatch` and `response` as
**top-level keys**. The smoke test above proves this end-to-
end: evt002 (an `agent_response` event) projects `agent`,
`trust_level`, and `status` correctly through
`raw.get("dispatch", {})` — exactly what `_project_event`
does.

The original projection was correct; no bug to fix on this
axis.
