# C8 — `firewall-auditor` game plan

**Agent file:** `.claude/agents/firewall-auditor.md`
**Role:** Continuous-audit watchman.
**Tools:** Read, Grep, Glob.

## Role in fleet

Continuous parallel audit while C1..C11 are firing. Any breach of (a) certPortal dev firewall, (b) INTENT §"Hot zones" write, (c) INTENT §"Out of scope" exfiltration shape, OR (d) >5min subagent Bash = HARD FAIL aborts POC ship.

## Inputs

- Tool-call records for every other subagent (coordinator supplies; or harness-emitted log).
- `feedback_certportal_dev_firewall.md`.
- `feedback_subagent_long_task_abandonment.md`.
- INTENT.md §"Hot zones" + §"Out of scope".
- `.claude/settings.local.json` (deny patterns; read-only reference).

## Steps

1. Repo-source breach scan: grep tool-call records for any certPortal repo path read (literal backslash + forward-slash variants).
2. Project-transcript boundary: ensure any `~/.claude/projects/C--Users-SeanHoppe-VS-certPortal/` read targets `*.jsonl` files only.
3. Hot-zone diff scan: zero `Write` / `Edit` against governance.py / message_bus.py / project_context.py / cli_governance.py.
4. INTENT §"Out of scope" scan: zero `transport/` writes, zero plaintext session-token shapes, zero off-host gov.db copies.
5. `>5min` Bash audit: zero subagent Bash invocations exceeding 300 s wall-clock.

## PASS criteria

- All five scans return zero hits.

## Outputs to coordinator

- Continuous-audit row. Single emission at end of POC window; intermediate HARD-FAIL aborts coordinator's fleet.

## Failure modes

- HARD FAIL on any breach. No `partial-PASS` allowed.

## Why parallel-and-continuous

Firewall breach detection must run for the lifetime of the POC, not at endpoints — a subagent could read a forbidden path mid-run and the breach matters even if no final report cites it.

## Refs

- `feedback_certportal_dev_firewall.md`.
- `feedback_subagent_long_task_abandonment.md`.
- INTENT.md §"Hot zones" + §"Out of scope".
- `.claude/settings.local.json`.
