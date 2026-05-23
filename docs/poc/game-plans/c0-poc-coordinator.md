# C0 — `poc-coordinator` game plan

**Agent file:** `.claude/agents/poc-coordinator.md`
**Role:** Orchestrator + verdict owner.
**Tools:** Read, Glob, Grep, Bash, Write.

## Role in fleet

Owns end-to-end POC verdict (`SHIP` / `NO-SHIP <blocker>`). Sequences C1..C11 dispatch, aggregates PASS/FAIL rows, writes `reports/poc-live-monitor-<UTC>.md`. Final accountability for both §3 pipeline conformance AND §4 INTENT.md conformance.

## Inputs

- `docs/2026-05-22-task-list.md` §1–§4 (binding spec).
- `INTENT.md` (binding for §4 product-shape rows).
- `docs/v10-mvp-status.md` §2 phase ledger (for gauge context in verdict report).
- All 11 subagent definitions under `.claude/agents/`.

## Steps

1. Read task list §3 + §4. Quote the binding row per subagent.
2. Mint `reports/poc-test-matrix-<UTC>.md` (one row per subagent + INTENT-§4 row, evidence cell empty).
3. Dispatch C1; lock `{pid, sessionId, cwd, projectSlug}`. HALT if `NO-TARGET`.
4. Dispatch C8 in parallel-and-continuous; abort all if HARD-FAIL.
5. Sequence C2 → C3 → C4 → C5 (each gates next).
6. After C4 PASS: parallel dispatch C6 (robin) + C7 + C10.
7. After C5 PASS: dispatch C11.
8. Dispatch C9 last; emit relay-request to main thread for operator turn via `AskUserQuestion`.
9. Aggregate verdict → `reports/poc-live-monitor-<UTC>.md`.

## PASS gate

POC SHIP iff:
- §3 pipeline: C1–C9 all PASS (C6 PASS = Path-D shadow infra conforms on synthetic fixtures).
- §4 INTENT: C4 alignment+cadence delivered, C10 5/5 + role divergence, C11 reload+budget+rank+revert, C5 3-frame + paired badges + HITL list, C7 routine-graduation, C8 zero breach.

## Dependencies

- Requires `feat/v2.8-p1-path-d` Path-D PR landed (for C6 robin shadow verification). POC pipeline (C1/C2/C3/C4/C5/C7/C8/C9/C10/C11) is orthogonal and can fire BEFORE Path-D land.
- Requires operator-supplied (a) dashboard log path, (b) C10 cassette pack OR live-injection approval, (c) C11 target `INTENT.md` path under non-SM non-firewalled project.

## Escalation paths

| Scenario | Action |
|---|---|
| C1 NO-TARGET | HALT; ask operator to start a non-SM Claude CLI session |
| C2 polarity-flip | HALT; print env diff + expected; refuse to proceed |
| C8 HARD-FAIL | ABORT all in-flight; verdict `NO-SHIP firewall-breach` |
| Any subagent > 5 min Bash | Per `feedback_subagent_long_task_abandonment.md` — verdict FAIL on that subagent; main thread takes over via `run_in_background` |
| C9 operator turn not received within relay window | Verdict `NO-SHIP awaiting-operator-turn`; not a real FAIL — re-fire when ready |

## Refs

- `.claude/agents/poc-coordinator.md` (the agent file).
- `docs/2026-05-22-task-list.md` §3 + §4.
- `INTENT.md` (full).
- `.claude/agents/robin.md` (contrast: robin owns v10 RL P1–P5 verification; coordinator owns POC product-level smoke).
