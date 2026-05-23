# C9 — `e2e-smoke-runner` game plan

**Agent file:** `.claude/agents/e2e-smoke-runner.md`
**Role:** Final end-to-end smoke + latency capture.
**Tools:** Read, Grep, Bash.

## Role in fleet

Captures one cold live pass: operator turn → JsonlTailWorker emit → governance decide → dashboard surface. Records per-stage timing + total wall-clock; PASS if ≤ 5000 ms target / WARN if ≤ 15000 ms ADR-5 ceiling / FAIL otherwise.

## Inputs

- Coordinator-relayed operator turn-sent timestamp + envelope text class.
- C1's locked triple.
- Bus DB (read-only).
- Dashboard endpoint (read-only).
- ADR-5 §"NFR-P2".

## Steps

1. Wait for coordinator relay (operator's `AskUserQuestion` confirmation that one turn was sent).
2. Stage C3: poll for envelope; record `t_envelope`.
3. Stage C4: poll for decision row; record `t_decision`.
4. Stage C5: connect to dashboard SSE; record `t_surface`.
5. Compute per-stage ms + total ms.
6. Apply budget gate.

## PASS criteria

- All three stages observable within 90 s wall-clock total.
- Total latency ≤ 5000 ms (target) / ≤ 15000 ms (ADR-5 ceiling = WARN).

## Outputs to coordinator

- Per-stage timing table (n=1 sample).
- Optional request: re-fire for distribution n>1.

## Why this exists separately from C3+C4+C5

C3/C4/C5 are step-wise PASSes. C9 captures the single cold-path latency in one observed sample, which is what the POC needs to ship a verdict on "real-time" feasibility.

## Failure modes

- `awaiting-operator-turn` — coordinator relay never received; not a real FAIL, re-fire.
- `stage-N-exceeded-90s` — pipeline broke between stages; HARD FAIL.

## Refs

- ADR-5 §"NFR-P2".
- `src/stream_manager/jsonl_tail.py:178`.
- `dashboard/server.py:292-331`.
