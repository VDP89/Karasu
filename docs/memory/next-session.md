# Next Session Entry Point

## Goal

**Phase 1C — validate the real Claude adapter loop.**

Demonstrate that:

```text
file_change → classify → dispatch → Claude CLI → agent_response
```

works end-to-end with a real adapter, under continuous editing, without crashing or losing events.

This is **validation, not production.** Do NOT optimize, parallelize, abstract, or generalize.

## Checklist

```text
1. Pull latest main.
2. Configure karasu.yaml:
     agents:
       claude_code:
         command: "claude"
         trust_level: 1
         handles: [code_change]
3. Run karasu watch in one terminal.
4. Run karasu tail --follow in another.
5. Edit a small .py file in the watched root.
6. Observe:
     - Claude CLI is invoked.
     - stdout is captured.
     - agent_response appears on the bus, paired with the file_change.
     - HumanReporter prints the reply (or asks for decision per trust).
7. Run karasu analyze and record metrics.
8. Open issue: phase:1C real adapter loop results.
```

## Behaviour expected of the adapter (minimal)

- Invoke the configured CLI with the request payload.
- Capture stdout.
- Wrap into `agent_response` with at least:

  ```json
  {
    "dispatch": {"agent": "claude_code", "status": "completed | failed", "trust_level": 1},
    "response": {"content": "<stdout>", "requires_human": "<per trust>"}
  }
  ```

- On adapter failure: emit `agent_response` with `status: failed` and the error message in `content`. **Do NOT crash the pipeline.**

## What to observe

```text
- file_change → agent_response latency.
- Output structure (does Claude return parseable text? markdown? both?).
- Failure modes (timeout, non-zero exit, malformed output).
- Cost implications (how often does each save trigger Claude?).
- System stability under repeated edits over several minutes.
```

## Output

Create issue: `phase:1C real adapter loop results`. Include:

- `karasu analyze` output.
- New ratio file_change / agent_response (expect ≥ 0 and ≤ 1, depending on classifier coverage).
- Subjective observations on output usefulness.
- Failure cases encountered.

## Exit condition

```text
Enough data to decide whether the adapter contract needs hardening
before any UI/Telegram/controller work. If yes, open
feat/claude-adapter-output-contract. If no, the next layer is open
for design.
```

## Do NOT do yet

```text
- Do not add Telegram or any UI.
- Do not add a LoopController or scheduler.
- Do not add GitHub webhooks or A2A.
- Do not mutate scars from chat / Telegram.
- Do not retry, batch, or parallelize adapter calls.
- Do not abstract the adapter behind a plugin layer.
```

## Anchor for the previous session

Phase 1B closed 2026-04-28. All five dogfood findings (F1–F5) resolved. Bus volume down 99.6 % from baseline on the same workload. See `current-state.md` and `session-log.md`.
