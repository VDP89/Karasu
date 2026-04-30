# Local Dogfood Runbook

This runbook is for Phase 1B: validating Karasu on a real local machine before adding Telegram, UI, or controller logic.

## Goal

Validate the real loop:

```text
filesystem change -> JSONL event bus -> pipeline -> agent response -> tail output
```

The goal is not to make the system elegant. The goal is to observe real behavior.

## Prerequisites

```bash
git clone https://github.com/VDP89/Karasu-.git
cd Karasu-
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Branches to test

Until PRs are merged, test the stacked branches in order:

```bash
git fetch origin
git checkout feat/eventbus-jsonl-tail-reader  # PR #9
git checkout feat/eventbus-tail-cli           # PR #10, stacked on #9
```

After PR #9 and PR #10 merge, test `main`.

## Minimal config

Create `karasu.yaml`:

```yaml
event_bus:
  path: .karasu/events.jsonl

watch:
  path: .
  ignore:
    - .git
    - .venv
    - __pycache__
    - "*.pyc"
    - .karasu/

classify:
  patterns:
    - match: "*.py"
      type: code_change

agents:
  claude_code:
    command: "claude"
    trust_level: 1
    handles:
      - code_change
```

Create runtime directory:

```bash
mkdir -p .karasu
```

## Terminal layout

Terminal 1:

```bash
karasu watch
```

Terminal 2:

```bash
karasu tail --follow
```

Terminal 3:

```bash
printf "print('hello')\n" > dogfood_probe.py
printf "print('world')\n" >> dogfood_probe.py
```

## What to record

Record these observations in a GitHub issue or `docs/memory/session-log.md`:

```text
Date:
Branch/commit:
OS/shell:
Python version:
Claude CLI version:
Command run:
Number of file_change events per save:
Number of agent_response events per save:
Latency observed:
stdout shape:
stderr shape:
Duplicate/noisy events:
Failures:
Unexpected behavior:
```

## Success criteria

```text
- karasu watch starts without crashing
- karasu tail shows events in real time
- .py file changes produce code_change flow
- agent_response is visible or failure is explicit
- no silent loss
- no silent misroute
```

## Known caveats

### Do not write output under watch root

Do not redirect `karasu watch` or `karasu tail` output into the watched directory:

```bash
# Avoid this
karasu tail --follow > tail.log
```

If the output file is inside the watched root, Karasu may observe its own output and create a feedback cascade.

### Event noise is expected

A single editor save may produce multiple filesystem events. Do not fix this before measuring it.

Decision rule:

```text
If duplicate events create repeated Claude calls, confusing reports, queue backlog, or cost risk, open a focused debounce PR.
Otherwise document the behavior and continue.
```

## What not to do during dogfood

```text
- do not add Telegram
- do not add LoopController
- do not add webhooks
- do not add /correct
- do not mutate scars from Telegram/chat
```

## Next decision after dogfood

Based on observations:

```text
A. If event noise is acceptable -> merge observability and move toward UI/console planning.
B. If event noise is high -> open feat/watch-debounce.
C. If Claude CLI output is unusable -> open feat/claude-adapter-output-contract.
D. If failures are clear but recoverable -> document and add focused adapter handling.
```

## Phase 2 — Telegram outbound sink (optional)

Once the JSONL pipeline is stable, the outbound Telegram sink can
forward each ``agent_response`` to a chat:

```bash
export KARASU_TELEGRAM_TOKEN="<bot-token-from-BotFather>"
export KARASU_TELEGRAM_CHAT_ID="<numeric-chat-id>"
karasu chat
```

Both env vars are mandatory — ``karasu chat`` exits with code 2 if
either is missing. With them set, the process polls the bus and
sends one Telegram message per ``agent_response``. ``file_change``
and other event types are not forwarded; the surface is a sink, not
an event mirror (see ``docs/phase-2-surface.md``).

Inbound replies in the chat write ``human_decision`` events on the
bus but the pipeline does NOT react to them in Phase 2. Override /
scar capture is deferred.
