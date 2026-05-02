# 2026-05-02 — Phase 3 dogfood (chunk 3b live validation)

Full bitácora of the Phase 3 dogfood session. Closed cleanly:
loop validated end-to-end with a real Claude CLI + Telegram bot;
three operational findings filed and merged the same day.

## Operator + environment

```text
Operator:           VDP89 (DG INGENIERIA SRL)
Date:               2026-05-02
OS:                 Windows 11 (10.0.26200.8328)
Shell:              cmd.exe
Python:             3.13.5  (C:\Python313\python.exe)
Claude Code CLI:    2.1.123 (npm-installed at
                    %APPDATA%\npm\claude.cmd)
python-telegram-bot: 22.7  (installed via pip during session)
Telegram bot:       @Karasu_dogfood_bot (created mid-session via
                    @BotFather)
Sandbox:            C:\karasu-phase3-sandbox\
Repo:               C:\karasu-work\Karasu-\  (cloned at start of
                    session via gh CLI)
```

## Goal

Validate Phase 3 chunk 3b (the controller's reaction loop) end-to-end
against real Claude CLI and a real Telegram bot. Phase 1C had
validated `file_change → claude → agent_response`; chunk 3b adds
`/correct or /scar → controller resubmit → second dispatch with
priority rewrite`. That added control-flow path had only run against
unit tests + integration tests with a fake adapter (#38). The dogfood
was the first time it ran live.

## Setup walkthrough (what actually got typed)

The operator was on a fresh Windows machine with `gh` CLI already
authenticated as `VDP89`. Each step below ran in the order shown.

### 1. Clone the repo to a clean working dir

```cmd
cd C:\
mkdir karasu-work
cd karasu-work
gh repo clone VDP89/Karasu-
cd Karasu-
git status
```

Output: `On branch main`, working tree clean. Repo cloned at commit
`1674c5b` (Phase 3 chunk 3c — TriggerSource + git-hook source).

### 2. Verify Python and Claude CLI

```cmd
python --version       # Python 3.13.5
claude --version       # 2.1.123 (Claude Code)
where python           # C:\Python313\python.exe (also two stale 3.8 + Microsoft Store stubs)
where claude           # C:\Users\DG INGENIERIA SRL\AppData\Roaming\npm\claude.cmd
```

`claude` is the npm-installed shim. PR #24 (Phase 1C, F8 / `shutil.which`) handles this case correctly — confirmed during the dogfood that `claude` launched without `FileNotFoundError`.

### 3. Install Karasu in editable mode

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"
```

Resolved `watchdog 6.0.0`, `python-telegram-bot 22.7`, `pyyaml 6.0.3`, `httpx 0.28.1`, plus dev deps (pytest 9.0.3, pytest-asyncio 1.3.0, pytest-cov 7.1.0).

```cmd
pytest -q
# 197 passed in 6.10s
```

(197 because PR #38's integration tests + runbook hadn't been merged to main yet at this point; they came in later.)

### 4. Sandbox creation (outside the repo, mandatory — see issue #14 caveat)

```cmd
cd C:\
mkdir karasu-phase3-sandbox
cd karasu-phase3-sandbox
mkdir .karasu
notepad karasu.yaml
notepad sample.py
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
    trust_level: 2
    handles: [code_change]
    timeout_s: 180
interface:
  telegram:
    poll_interval: 0.5
    allowed_users: [7509793010]
```

`sample.py` started as `def f(): return 1`.

### 5. Telegram bot creation

The operator created `@Karasu_dogfood_bot` via `@BotFather` mid-session
(`/newbot` → name "Karasu dogfood" → username "Karasu_dogfood_bot"
→ token issued). Chat ID `7509793010` retrieved via `@userinfobot`.
The operator then sent `/start` to the new bot from their Telegram
account — required so the bot knows about the chat for outbound
messages.

### 6. Env vars

```cmd
set KARASU_TELEGRAM_TOKEN=<bot-token>
set KARASU_TELEGRAM_CHAT_ID=7509793010
```

### 7. Two terminals, two processes

Terminal B (new cmd):

```cmd
cd C:\karasu-phase3-sandbox
C:\karasu-work\Karasu-\.venv\Scripts\activate.bat
karasu watch
# karasu watch: writing events to .karasu\events.jsonl
```

Terminal A (the original — env vars set here):

```cmd
karasu chat
```

**This is where finding F9 surfaced.**

## Mid-flight finding F9 — `[job-queue]` extra missing

`karasu chat` crashed at startup:

```
PTBUserWarning: No `JobQueue` set up. To use `JobQueue`, you must
install PTB via `pip install "python-telegram-bot[job-queue]"`.
...
File "...\interface\telegram_bot.py", line 248, in run_application
    application.job_queue.run_repeating(_drain_job, interval=poll_interval)
AttributeError: 'NoneType' object has no attribute 'run_repeating'
```

Root cause: `python-telegram-bot>=21.0` ships `JobQueue` as a separate
`[job-queue]` extra. Our `pyproject.toml` declared the base package only.

**Diagnosis took ~30 seconds** — PTB's own warning telegraphs the cause
explicitly. We unblocked with:

```cmd
pip install "python-telegram-bot[job-queue]"
karasu chat
# karasu chat: forwarding agent_response events to chat_id=7509793010
```

Filed as **F9 (P1)** for follow-up after the dogfood. Real production
fix landed as PR #40 (`python-telegram-bot[job-queue]>=21.0` in
`pyproject.toml`).

**Why unit / integration tests didn't catch this**: `tests/test_phase3_integration.py` exercises the controller's bus subscription **directly** (constructs a real `LoopController`, calls `start()` / `submit()`, observes the bus). It never builds the `python-telegram-bot` `Application` because that path is `pragma: no cover` in `run_application`. The dogfood was the first time `application.job_queue` was actually accessed. Lesson: the runbook caught what unit + integration tests structurally couldn't. Both are needed.

## The loop closure moment

After F9 was patched, the loop ran clean.

### First dispatch (smoke check)

The operator edited `sample.py` from a third Notepad window. The
file-save sequence had some hiccups (`return 1 → return 2`, then a
larger divide-by-zero block — the second save didn't always
persist). Three dispatches fired during this period; Claude correctly
identified them as no-ops because the dispatch payload carried no
task spec, and refused to repeat its diagnosis. This is itself a
useful observation: **Claude with `trust_level=2` self-rate-limits
on uninformative dispatches**.

Eventually the divide-by-zero file did save (10 lines):

```python
def add(a, b):
    return a + b
def divide(a, b):
    return a / b
result = divide(10, 0)
print(result)
```

Claude reviewed it AND **fixed it autonomously** — changed the call
site from `divide(10, 0)` to `divide(10, 2)` and added a guard. The
agent_response noted: *"Fixed sample.py: added a zero-divisor guard
in divide and changed the call site from divide(10, 0) to divide(10,
2). Script now runs and prints 5.0."*

This is the **trust gradient operating in production**: `trust_level=2`
(NOTIFY_ASYNC) means the agent acts and notifies. We saw it act.
**This is not a bug.** It's the Phase 1A contract working as designed.

### The chunk-3b moment

The operator sent `/scar priority=high` in Telegram.

**Bot response (Telegram)**: `recorded scar 5e2056c9: trigger={'classification': 'code_change', 'path': 'sample.py'} correction={'priority': 'high'}`

**Bus events** (timestamps from `karasu tail --from-start --json`):

```text
13:39:05.310Z  human_decision  source=interface
                               data.text="/scar priority=high"
                               id=35fdc54b-87c4-4b8d-89dd-3027a8f2f8a1

13:39:05.404Z  file_change     source=controller
                               controller_resubmit=true
                               resubmit_origin=f3748ff8-97b1-4030-9bd9-90157d6d42c8
                               id=53c56694-27b3-43e0-8237-659b5cb44837

13:39:34.187Z  agent_response  source=adapter
                               correlates=53c56694-27b3-43e0-8237-659b5cb44837
                               content="Reviewed sample.py (10 lines): ..."
                               id=fbb46981-a399-4256-b296-3a39fe031044
```

**Latencies**:

- `/scar` arriving on the bus → controller resubmit emitted: **94 ms**.
  This is the next bus poll tick (poll interval is 0.5 s; the actual
  detection happened sub-poll because the human_decision was
  appended right before a tick).
- Resubmit → claude response: **~28.78 s**. Pure `claude -p` time
  with auto-discovery. Comparable to Phase 1C dogfood (~38.5 s).

**The smoking quote** — Claude's response on a subsequent
cap-allowed resubmit:

> *"the scar rule fired correctly — that's why this arrives at high"*

This was **direct evidence** that `Pipeline._apply_scar_override`
rewrote the priority on the dispatch and the adapter received it. The
agent_response itself does NOT persist priority on the bus (data only
carries `correlates` and `path`), so we had no other way to verify
the rewrite reached Claude. Claude exposed it voluntarily. Lucky
break — but worth noting that **future audits would benefit from
persisting `priority` on the agent_response** for direct
verification (filed mentally; not P1 enough for an F-finding).

## Cap test (T10)

The operator sent six `/scar priority=high` in rapid succession to
verify `RESUBMIT_CAP=3` holds.

**Result**: exactly **3 resubmits fired**, **3 cap warnings logged**:

```
controller resubmit: cap (3) reached for file_change 53c56694-...; skipping
controller resubmit: cap (3) reached for file_change 53c56694-...; skipping
controller resubmit: cap (3) reached for file_change 53c56694-...; skipping
```

`karasu analyze --json` final state:

```json
{
  "by_type": {
    "agent_response": 8,
    "file_change": 11,
    "human_decision": 7
  },
  "total_events": 26,
  "duplication_factor_file_changes_per_path": 5.5
}
```

Math:
- 7 human_decision = 1 baseline + 6 from cap test
- 11 file_change = 8 baseline (watcher) + 3 controller_resubmit (cap-allowed)
- 8 agent_response = 5 baseline + 3 from the cap-allowed resubmits

**Cap held exactly as designed.** The single-worker invariant means
the 3 dispatches process serially (~30 s each = ~90 s total). The
operator ran `analyze` mid-flight first (saw 7 agent_responses, then
60 s later 8) — confirming the worker was draining sequentially.

The duplication_factor of 5.5 was inflated by Notepad's atomic-write
artifact `sample.py.tmp.5296.1777729004615` showing up as 2
file_change events that the existing `*.tmp` glob does not match.
Filed as **F11** (cosmetic).

## Findings filed

```text
F9 (P1, #40)
   pyproject.toml didn't declare python-telegram-bot[job-queue] extra.
   karasu chat crashed on fresh install with AttributeError on
   application.job_queue.run_repeating.
   Fix: change dependency to python-telegram-bot[job-queue]>=21.0
   with an in-line comment pointing at this dogfood.

F10 (P3, #41)
   _drain_job in run_application emitted APScheduler "skipped:
   maximum number of running instances reached (1)" warnings when
   bot.send_message took longer than poll_interval. Cosmetic — no
   functional impact (skip is correct because JsonlTailReader is
   not thread-safe, max_instances=1 is a safety bound).
   Fix: pass job_kwargs={"coalesce": True, "max_instances": 1} to
   run_repeating. APScheduler collapses queued misses into a single
   follow-up. No warnings, no missed work.

F11 (P3, #42)
   DEFAULT_IGNORE *.tmp does not match Notepad atomic-write
   artifacts (<file>.tmp.<PID>.<TS>) because they end in digits.
   Cosmetic — they don't match *.py classifier glob, so they don't
   trigger dispatch. Just bus noise.
   Fix: add "*.tmp.*" to DEFAULT_IGNORE. Tested with the exact
   filename observed live (sample.py.tmp.5296.1777729004615).
```

All three landed the same day as separate focused PRs. Stack-clean
merges (F9 → F10 → F11 → docs).

## PRs landed

```text
#38  test(phase-3): integration tests + runbook       (4 new tests)
#40  fix(deps): F9 [job-queue] extra                  (P1)
#41  fix(interface): F10 drain coalesce               (P3)
#42  fix(watcher): F11 *.tmp.* glob                   (P3)
#43  docs(memory): mark DOGFOOD-VALIDATED + queue
                   Phase 3+ pre-mortem
```

Issue #39 closed (state_reason: completed) once all four landed.

## Decisions made

1. **F9 fix is the dependency declaration, not a runtime check.**
   Could have caught this with a startup probe (`if application.job_queue is None: raise ImportError("install [job-queue] extra")`), but the dependency declaration is the actual correct level. The PTB warning already telegraphs the diagnosis.

2. **F10 fix keeps `max_instances=1` and adds an explicit comment.**
   Bumping it would race the JsonlTailReader's `_offset`. A future contributor might be tempted to bump it for "throughput"; the inline comment prevents that.

3. **F11 fix uses `*.tmp.*` rather than something more specific.**
   Notepad isn't the only editor that produces `.tmp.<id>.<ts>` patterns. The broader glob covers other editors with the same shape without enumerating them.

4. **Trust gradient autonomous-execution behavior is a feature, not a bug.**
   Claude editing `sample.py` autonomously surprised us mid-dogfood. Initial reaction: file an F-finding for unexpected behavior. Correct reaction: this is `trust_level=2` doing what `docs/decisions.md` D-003 promised. Document and move on.

5. **The dogfood narrative belongs in a session bitácora, not a code comment.**
   The setup story (clone, install, F9 unblock, /scar moment, cap test) is too rich for a commit message. Hence this file.

## Artifacts left behind

- **Repo**:
  - PRs #40, #41, #42 closed F9/F10/F11.
  - PR #38 added integration tests + runbook.
  - PR #43 marked Phase 3 DOGFOOD-VALIDATED.
  - `docs/memory/current-state.md` updated.
  - `docs/memory/session-log.md` chronological entry added.
  - `docs/memory/next-session.md` repointed at Phase 3+ pre-mortem.
  - This bitácora.
- **Issue #39** updated body with full evidence chain, then closed.
- **Operator's machine**:
  - `C:\karasu-work\Karasu-\` — local repo on `main`.
  - `C:\karasu-phase3-sandbox\` — sandbox with `karasu.yaml`,
    `sample.py`, `.karasu/events.jsonl` (26 events), `.karasu/scars/`.
  - `@Karasu_dogfood_bot` exists in their Telegram for future smokes.
  - `KARASU_TELEGRAM_TOKEN` / `KARASU_TELEGRAM_CHAT_ID` env vars set
    in the cmd session (lost on close).

## Lessons learned

```text
1. Integration tests with a fake adapter cover semantic correctness.
   They do NOT cover environment / dependency mismatch
   (F9: missing extra, only surfaces at first real Application boot).
   Both layers are needed.

2. Notepad-on-Windows produces atomic-write artifacts
   (.tmp.<PID>.<TS>) that the *.tmp glob doesn't match. Worth
   testing on the actual editors operators will use.

3. Telegram bot setup should NOT be a step gated by chat-paste of
   secrets. Future runbooks should explicitly say "do NOT paste
   tokens in the chat", and we should prefer env-var-only flows.
   The token leaked in chat history during this session — we
   weighed the risk and the operator chose to keep using the bot
   (it's a throwaway bot, single-operator, the chat is private).
   Recorded explicitly here for transparency.

4. The bus poll of 0.5 s is enough to give a sub-second reaction
   (94 ms measured) for the human_decision → resubmit path. No
   incentive to tighten the constant.

5. Claude with trust_level=2 modifies code autonomously in
   response to dispatches. This is the contract; document
   prominently in onboarding so operators don't expect read-only
   behavior at trust=2.

6. The operator-on-mobile case matters. The session resumed from
   the cmd terminal mid-day after a partial mobile attempt. The
   tutorial-style guidance worked: small steps, paste output,
   confirm before proceeding.

7. APScheduler default coalesce=False is the wrong default for our
   drain job. Future PTB-based features should default to
   coalesce=True from day one.
```

## Next step pointer

See `../next-session.md` — pointed at the Phase 3+ archive
pre-mortem (docs-only doc per the design-first cadence).

Three Phase 3+ archive concepts queued:
- GitHub webhook receiver (HMAC + delivery dedup)
- A2A Agent Cards (`/.well-known/agent-card.json`)
- Review-comment auto-handoff to Claude Code

Recommended order: pre-mortem first, then webhook receiver (smallest
scope, plugs into the existing TriggerSource pattern from chunk 3c).
