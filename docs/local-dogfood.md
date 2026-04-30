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

### Read-only slash commands

With ``karasu chat`` running, the bot accepts three commands. Each
returns a snapshot of state — no writes, no side effects:

```text
/status   — karasu version, event log path, total events,
            counts by type, last event timestamp.
/agents   — registered adapters with their `handles` lists.
/scars    — active scar rules (trigger -> correction).
```

The ``allowed_users`` whitelist (``interface.telegram.allowed_users``
in ``karasu.yaml``) gates these commands. Empty whitelist allows
anyone, mirroring the chunk-1 default; set it to your Telegram user
id for single-operator setups.

### Inbound scar capture

Two commands write a ``Scar`` to the configured ``ScarEngine`` so a
correction becomes a durable rule:

```text
/correct <event_id-prefix> <field>=<value> [<field>=<value> ...]
/scar <field>=<value> [<field>=<value> ...]
```

``/correct`` resolves the ``agent_response`` whose id starts with the
given prefix (git-style; longer prefix needed if the bot replies
"ambiguous"). ``/scar`` skips the lookup and uses the most recent
``agent_response`` on the bus — convenience for "fix the thing I
just saw".

Allowed correction fields are ``classification``, ``priority``,
``path`` (the same allowlist the dispatcher honours per
``Pipeline.SUPPORTED_SCAR_KEYS``). Anything else is rejected with a
clear reply and the bus stays untouched.

Whitelist policy for write commands is **strict**: an empty
``allowed_users`` rejects every ``/correct`` and ``/scar``. The
operator must add their Telegram user id to the YAML before scar
capture will fire. Reads (``/status``, ``/agents``, ``/scars``) are
unaffected.

Every attempt — accepted, rejected, or unauthorized — also writes a
``human_decision`` event on the bus so the audit trail is preserved.
For unauthorized callers and unknown commands the recorded text is
**redacted**: the bus stores ``"/<name> (unauthorized)"`` or
``"/<name> (unknown command)"`` instead of the raw message body
(message text could contain arbitrary input from a leaked chat;
only the metadata is operationally useful in those cases).
Authorized calls record the full ``/<name> <args>`` so the operator
can reconstruct what they sent. The pipeline does NOT consume
``human_decision`` events in Phase 2.
