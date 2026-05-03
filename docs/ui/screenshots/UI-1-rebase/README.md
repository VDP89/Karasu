# UI-1 — rebase + cleanup screenshots

UI-1 ships:

- 5 cherry-picked commits from ``feat/ui-1-runtime`` (the
  6th was a placeholder stub and is replaced by the new
  ``cmd_ui`` in ``__main__.py``).
- ``server.py`` projection expanded to surface chunk-4c
  fields (``priority``, ``controller_chain_depth``,
  ``controller_resubmit``, ``resubmit_origin``,
  ``github_event``, ``github_action``, ``github_pr``,
  ``github_repo``, ``github_author``, ``correlates``,
  ``status``, ``trust_level``, ``classification``).
- ``static/index.html`` is the cherry-picked stub —
  unchanged in this chunk. UI-2 / UI-3 introduce the real
  shell.
- ``docs/ui/karasu-win95-runtime-mockup.md`` archived to
  ``docs/ui/explorations/`` per UI-0 design brief §3 D.

## Capture status

The original capture environment for this chunk did not have
a browser available (apt-locked sandbox; Playwright Chromium
download blocked by upstream). The visual surface in UI-1 is
the **same stub** that already existed on
``feat/ui-1-runtime`` — no new visible state is introduced
by this PR. The "new" thing is the data shape behind
``/api/events``, which is verified by the pytest smoke
script and by the curl-evidence in this README.

The operator can capture screenshots locally by running:

```bash
pip install playwright
python -m playwright install chromium
python scripts/ui_screenshots.py UI-1-rebase
```

The script seeds a temporary ``events.jsonl`` with four
synthetic events (one per major bus shape — watcher,
agent_response, github webhook, controller resubmit), starts
``karasu.ui.server`` against that bus, and writes screenshots
to this folder.

## /api/events evidence (text, since no browser)

Against the synthetic bus above, ``/api/events`` returns four
events with the chunk-4c projections populated:

```text
evt001 (watcher file_change)
  priority=normal
evt002 (agent_response)
  priority=normal, agent=claude_code, trust_level=1
evt003 (github webhook file_change)
  priority=high, github_pr=42, github_author=reviewer1
evt004 (controller resubmit file_change)
  priority=high, controller_resubmit=True,
  controller_chain_depth=1
```

``/api/health`` returns ``{"status":"ok","events":4,"crow":"processing"}``
on the same bus tail.

This is the contract UI-2..UI-9 will render against.
