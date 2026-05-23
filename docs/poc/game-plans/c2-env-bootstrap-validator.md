# C2 — `env-bootstrap-validator` game plan

**Agent file:** `.claude/agents/env-bootstrap-validator.md`
**Role:** Runtime-env gatekeeper.
**Tools:** Read, Glob, Grep, Bash.

## Role in fleet

Second in sequence (after C1 lock). Verifies operator's `BRIDGE_*` env satisfies the v2.8 P0 monitor-target binding contract. If env is wrong, tail will silently match the wrong slug; C3+ will produce false negatives.

## Inputs

- C1's locked triple.
- Operator env (read-only).
- `docs/v2.8-task-plan.md` §"Monitor target (Q-D BOUND 2026-05-22)" (binding spec).
- `docs/learn-mode-design.md` §7.2.1 (production wiring env contract).
- Dashboard log path (operator-supplied or default `dashboard.log`).
- `rl/shadow.py` (`_is_sm_self` / `_sm_slug_set` — refusal-layer reference).

## Steps

1. Snapshot env: `BRIDGE_PROJECT_SLUG`, `BRIDGE_SM_PROJECT_SLUGS`, `BRIDGE_SM_SELF_SESSION_ID`, `BRIDGE_PROJECTS_DIR`.
2. Verify each row of the table against C1-locked.
3. Polarity-flip check: target slug ∉ SM slugs; not equal to `streamManager`; C1 sessionId ≠ self sessionId.
4. Read dashboard log; confirm `jsonl_tail: started (... slug=<target> ...)` line for the target slug.
5. Negative test: invoke `_is_sm_self({"project_slug": "streamManager"})`; confirm `True`.

## PASS criteria

- All 4 env vars present + correct.
- Polarity-flip refusal fires for SM slug.
- Dashboard log confirms tail started against C1 target.

## Outputs to coordinator

- Env snapshot table.
- Polarity-flip negative-test row.
- Gates C3 (without env mandate met, C3 cannot validate).

## Failure modes

- `polarity-flip-violation` — operator set `BRIDGE_PROJECT_SLUG` to an SM slug. HALT.
- `dashboard-not-tailing-target` — log says tail started against a different slug. HALT.
- `bridge-sm-self-session-id-missing` — refusal layer cannot self-exclude. HALT.

## Refs

- `docs/v2.8-task-plan.md` §"Monitor target".
- `docs/learn-mode-design.md` §7.2.1.
- `rl/shadow.py`.
- `feedback_no_self_monitor.md`.
