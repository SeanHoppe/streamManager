# v2.2 P1 — API-timeout invariant test (gap-4 fold) + deletion offset

> Minted at v2.2 P0 cycle frame (this PR). Inherits gap-4 prompt
> body verbatim with v2.2-consolidation-cycle deletion-offset
> addendum. Fire when P0 merges.

## Branch + base

- Base: `main` after v2.2 P0 cycle frame merges (this PR's merge
  commit; expected `chore/v2.2-p0-cycle-frame` → main).
- PR target: `main`.
- Branch: `feat/v2.2-p1-api-timeout-invariant` (despite the `feat`
  prefix the cycle is consolidation; conventional-commits scope is
  by content, not cycle theme).
- ABORT if v2.2 P0 not merged.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -5
```

Expected top-of-main: this P0 PR's merge commit. If not present,
STOP.

## Scope

Inherits `docs/prompts/v2.2-orchestration/gap-4-api-timeout-
invariant-test.md` verbatim. Implementation guidance + DOD live
there.

### Consolidation-cycle addendum — mandatory deletion offset

ADR-18 Rule 3 binds consolidation cycles to net LOC ≤ 0 across
`src/` + `tests/` + `tools/` + `dashboard/`. Gap-4 adds ~80 LOC
(test + driver line). P1 MUST find ≥ 80 LOC offsetting deletion
in the same buckets to satisfy Rule 3 at ship-gate P2.

**Survey procedure (run FIRST, before any test code lands):**

1. Grep for dead exports / TODO-ripout markers:
   ```
   grep -rn 'TODO.*remove\|TODO.*rip\|@deprecated\|# DEAD' src/ tests/ tools/ dashboard/
   ```
2. Identify any test fixtures no longer referenced by tests in
   `tests/`. Pattern: fixtures under `tests/fixtures/` whose path
   doesn't appear in any `tests/test_*.py` import or `open(...)`.
3. Identify any utility script in `tools/` whose entry-point is
   not invoked by `pyproject.toml`, CI workflows, or any
   `tools/*.py` import.
4. Surface ≥ 5 candidates in PR body; operator picks which to
   delete OR records explicit "no candidates" stamp.

**Escalation path if survey yields < 80 LOC.** Two options:

- **(a) Defer gap-4 to v2.3.** Mark gap-4 prompt header
  `DEFERRED to v2.3` (matches gap-1/2/3 disposition shape). v2.2
  has only ship-gate P2; gap-tracking doc lifetime extends.
- **(b) Operator override.** Consolidation cycles do not have an
  Amendment A override mechanism (Amendment A only covers feature-
  cycle soft target). Requires a new ADR-18 amendment minted in
  this P1 PR — adds amendment scope to P1 work. Not recommended
  for a 80-LOC overage.

Default = (a).

## DOD

Per `gap-4-api-timeout-invariant-test.md` §DOD, plus:

- [ ] Deletion offset ≥ |gap-4 LOC add| stamped in P1 PR body
      OR P1 escalation per addendum above.
- [ ] Gap-4 prompt header stamp updated:
      `FOLDED v2.2 P1 — LANDED PR #<n>` on merge.
- [ ] `docs/v2.2-task-plan.md` §PHASE P1 ledger updated with
      final LOC delta.

## Cross-refs

- `docs/prompts/v2.2-orchestration/gap-4-api-timeout-invariant-
  test.md` — primary spec.
- `docs/v2.2-task-plan.md` §PHASE P1 — ledger destination.
- ADR-18 Rule 3 — consolidation LOC ≤ 0 (unchanged by v2.2 P0
  Amendment A).
- Memory `project_v17_cycle_close.md` — ADR-5 latency baseline
  anchor (~11 s p95).

Report back when P1 PR opens with: PR URL, deletion-offset survey
result, expected LOC delta vs `<P0-merge-sha>...HEAD --stat`.
