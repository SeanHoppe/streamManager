# C6 — `robin` (existing) reuse plan

**Agent file:** `.claude/agents/robin.md` (already minted — see `feat/v2.8-p1-path-d` lineage).
**Role:** v10 P5 shadow-side verifier (reuse).
**Tools:** Read, Glob, Grep, Bash, Write (per robin.md).

## Role in fleet

Robin's mandate is v10 RL track testing (P1–P5). In the POC fleet, robin is repurposed for the **shadow-side** of v2.8 P1 Path-D synthetic-fixture P5 verification — i.e. confirm `rl/shadow.py` (ShadowRecorder + non-invasion budget + polarity-flip filter) and `rl/stop_conditions.py` (ShipCriteria + evaluate_criteria) behave correctly against the Path-D synthetic fixtures.

Does NOT fire Tier-3 soaks (main-thread-only). Does NOT verify the live-tail surface (that's C3/C4/C5/C9 territory). Strictly read-only against `rl_shadow.db`.

## Inputs

- `rl/shadow.py` (working tree at session start: 276 lines; production version lands at `feat/v2.8-p1-path-d` merge).
- `rl/stop_conditions.py` (working tree: 454 lines).
- `docs/prompts/v2.8-orchestration/phase-1-seed-v2.6-c-path-d.md` (Path-D scope).
- Synthetic-fixture corpus (Path-D writes one).
- `rl_shadow.db` after Path-D dry-run (read-only).

## Steps

Per `.claude/agents/robin.md` §"P5 — shadow + stop conditions":

1. Shadow `on_governance_decision` p95 ≤ 50 ms over ≥ 1000 envelopes (synthetic stress; main thread runs).
2. Shadow rows live in `rl_shadow.db`, NOT `rl_episodes.db`.
3. `evaluate_criteria` over 3 shadows + 3 manifests; produce report.
4. ALL 6 ship criteria PASS → exit 0; any FAIL → exit 1 with reason.
5. Production verdict byte-identity: shadow-on vs shadow-off identical (main thread supplies both reports; robin diffs).
6. `grep -nE 'os.environ.*ship.*threshold' rl/stop_conditions.py` → empty (thresholds are code constants).

## PASS criteria

Same as robin.md §"P5 — shadow + stop conditions". POC accepts robin's verdict as-is.

## Outputs to coordinator

- `reports/v10-test-matrix-P5-<UTC>.md` (robin emits this).
- PASS/FAIL row in POC verdict report.

## Dependencies

- **Hard precondition: v2.8 P1 Path-D PR merged** (or local Path-D branch checked out with `rl/shadow.py` + `rl/stop_conditions.py` matching the working-tree drafts).
- Main thread owns Tier-3 soak; robin only ingests reports.

## Failure modes

- `path-d-not-landed` — robin cannot verify shipped code; POC SHIP can still proceed on §3 pipeline alone (Path-D is orthogonal per `docs/v2.8-task-plan.md` §"P1").
- Per-check failures: robin's standard remediation rows.

## Refs

- `.claude/agents/robin.md`.
- `docs/prompts/v2.8-orchestration/phase-1-seed-v2.6-c-path-d.md`.
- `rl/shadow.py`, `rl/stop_conditions.py` (working-tree drafts).
- `project_v10_p4_hold_lifted.md`.
- `project_v10_p5_gate_deadlock.md`.
