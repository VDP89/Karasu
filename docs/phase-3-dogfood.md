# Phase 3 — Local Dogfood Runbook

This runbook is for Phase 3: validating the LoopController react
loop (chunk 3b) end-to-end against a real Claude CLI + Telegram
bot. Same shape as `docs/local-dogfood.md` (Phase 1B/1C), updated
for the chat-driven correction path.

## Goal

Validate the full chunk-3b loop:

```text
file_change           → pipeline → claude -p     → agent_response
agent_response        → operator reads in Telegram
operator /correct     → ScarEngine.record + human_decision on bus
controller poll       → resubmits originating file_change
pipeline (resubmit)   → _apply_scar_override applies the new scar
                      → claude -p with corrected priority
                      → second agent_response
```

If any link is missing or slow, record it and escalate.

## Coverage relative to automated tests

The four tests in ``tests/test_phase3_integration.py`` already
exercise the loop with a fake adapter. The dogfood adds what those
tests cannot:

```text
- Real claude -p latency under the resubmit (sub-second vs. seconds).
- Real Telegram inbound timing (``human_decision`` actually written
  when the operator types /correct).
- Cost / volume of two real Claude calls per correction.
- Concurrency: what happens if a watcher event lands DURING the
  resubmit reaction.
- The redaction policy on unauthorized writes (audit trail without
  the args content).
```

## Prerequisites

```bash
git clone https://github.com/VDP89/Karasu-.git
cd Karasu-
git pull origin main      # post-merge of #34 + #35 + #36 + #37
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                 # confirm 197+ green on main
```

Required env:

```bash
export KARASU_TELEGRAM_TOKEN="<bot-token-from-BotFather>"
export KARASU_TELEGRAM_CHAT_ID="<numeric-chat-id>"
```

`claude` CLI must be on PATH (``which claude``). Same Phase 1C
setup as issue #25.

## Sandbox config

Outside the repo, mirroring the Phase 1C dogfood layout:

```bash
mkdir -p ~/karasu-phase3-sandbox && cd ~/karasu-phase3-sandbox
mkdir -p .karasu
```

`karasu.yaml`:

```yaml
event_bus:
  path: .karasu/events.jsonl

scars:
  rules_path: .karasu/scars/

watch:
  path: .
  debounce_ms: 250
  ignore: [.git, __pycache__, "*.pyc", .karasu/, "*.log", "*.tmp"]

classify:
  patterns:
    - match: "*.py"
      type: code_change
      priority: normal

agents:
  claude_code:
    command: "claude"
    trust_level: 2          # high enough that the resubmit auto-flows
                            # through; for trust_level=1 you'll see
                            # [DECISION] prefixes on each report.
    handles: [code_change]
    timeout_s: 180

interface:
  telegram:
    poll_interval: 0.5
    allowed_users: [<your-telegram-user-id>]   # required for /correct
```

A throwaway target file:

```bash
cat > sample.py <<'EOF'
def f():
    return 1
EOF
```

## Run

Two terminals.

Terminal 1:

```bash
karasu watch | tee watch.log
```

Terminal 2:

```bash
karasu chat
```

(`tee watch.log` is fine — chunk 3a's `DEFAULT_IGNORE` covers
`*.log`, so the cascade from issue #14 cannot reproduce.)

## Workflow

```text
T1.  Edit sample.py (any change).
T2.  Wait for the agent_response to arrive in Telegram.
T3.  Note the agent_response id (last 8 hex chars).
T4.  In Telegram: /correct <id-prefix> priority=high
T5.  Wait for the SECOND agent_response. Note the latency from
     /correct send to second response receipt.
T6.  Run: karasu analyze --json
T7.  Edit sample.py again to trigger a fresh dispatch.
T8.  Verify the new dispatch ALSO sees priority=high (the scar
     fires on subsequent file_changes too — chunk 3b's resubmit
     was the one-shot trigger; ``Pipeline._apply_scar_override``
     handles every subsequent dispatch).
T9.  Try /correct with a wrong prefix. Verify the bot logs the
     warning and no resubmit happens.
T10. Try /correct repeatedly (5+ times) on the same agent_response
     id. Verify only RESUBMIT_CAP=3 resubmits fire; the rest log
     "cap reached".
```

## Observations to capture

Mine + ChatGPT's pre-mortem follow-ups. Fill each based on what
you actually see.

```text
## Loop closure
First  file_change → first  agent_response  : (paste timestamps + delta)
/correct sent → second agent_response       : (paste timestamps + delta)
Did the second agent_response carry the
   corrected priority?                       : YES / NO

## Resubmit visibility on the bus
karasu analyze --json output                 : (paste)
Number of file_changes with
   controller_resubmit=true                  : (count)
Number of human_decision events              : (count)

## Cap enforcement (T10)
Total /correct attempts (text recorded)      : (count)
Total resubmits actually fired               : (should be == 3)
Log line "cap (3) reached" present?          : YES / NO

## Subsequent dispatches (T8)
After the first resubmit, edits to sample.py
   trigger dispatches with priority=high?    : YES / NO

## Latency
Median end-to-end (file_change → response)   : (ms)
Median /correct → resubmit response          : (ms)
Resubmit overhead vs. native dispatch        : (ms delta)

## Cost / volume
Total Claude calls per logical correction    : (count, expected: 2)
Bus growth per /correct                      : (events: 1 file_change
                                                + 1 scar_consultation
                                                + 1 human_decision
                                                + 1 file_change (resubmit)
                                                + 1 agent_response)

## Failures / surprises
(free-form: anything that surprised you, anything that should be
filed as a finding before Phase 3+ archive work starts)
```

## Decision rule for the follow-up PR

```text
If the loop closes cleanly:
  → docs-only PR. Update docs/memory/current-state.md to mark
    Phase 3 as DOGFOOD-VALIDATED. No code change. Phase 3+
    archive (webhook / A2A / handoff) opens next.

If the loop is intermittent or slow:
  → focused code-bearing PR per finding (same pattern as F6/F7/F8
    in Phase 1C). Examples of what counts as a finding:
    - Resubmit takes >5 s with claude -p (poll_interval too coarse?)
    - Double-resubmit on a single /correct (race in the bus reader?)
    - Scar fires on the resubmit but NOT on subsequent edits
      (Pipeline._apply_scar_override regression?)
    - Cap enforced inconsistently across long-running sessions.

If the loop does NOT close:
  → escalate. Open a tracking issue (mirror of #25 / #14) and
    pause Phase 3+ work until root cause is found.
```

## What NOT to do during the dogfood

```text
- Do not start GitHub webhook receiver, A2A, or review-comment
  handoff work. Phase 3+ archive waits on this dogfood.
- Do not parallelize the controller worker. The single-worker
  invariant is part of what's being validated.
- Do not let the pipeline consume human_decision directly. The
  controller is the only consumer (chunk 3b contract).
- Do not touch AgentResponse, F3, F7, F8.
```

## Caveats already known (verify or refute)

```text
Caveat 1: trust_level=2 was used so the resubmit is autonomous.
  trust_level=1 is the operational default and adds a
  [DECISION] prefix. Worth running BOTH paths if time allows.

Caveat 2: Bus poll interval is 0.5 s in production. /correct →
  resubmit therefore has a ~0.5 s floor before the resubmit fires.
  If that's intolerable, file a finding rather than tightening
  the constant; it's a tradeoff with disk read frequency.

Caveat 3: capture_correct re-classifies the path with the
  CURRENT classifier config. If you change `classify.patterns`
  between the original dispatch and the /correct, the trigger
  reflects the new config (documented in
  docs/phase-2-surface.md "Trigger derivation note"). Worth
  noting if you see surprising trigger shapes.
```
