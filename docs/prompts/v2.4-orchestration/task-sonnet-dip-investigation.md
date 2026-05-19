# Task — Sonnet-DIP investigation (🟡 Seed v2.4-D)

> Minted 2026-05-19 as part of v2.4 P1 fire. Comparison anchor:
> `docs/v2.4-next-steps.md` §"Seed v2.4-D — 🟡 Sonnet-DIP investigation".
> Promoted from `docs/v2.3-next-steps.md` §"NEW v2.3 ship-gate seeds" #1.
> Precedent prompt: `docs/prompts/v2.2-orchestration/task-alignment-dip-row-audit.md`
> (v2.1→v2.2 audit, closed at v2.2 ship-gate).

## Why

v2.3 ship-gate alignment-eval landed sonnet pass-rate **0.8182** vs
v2.2 ship-gate **0.9474** — a 0.1292 drop. The eval is FR-OG-7
load-bearing per ADR-18 row table; FR-OG-7 floor (0.80) was not
breached but the trajectory across three cycles is non-monotone and
the denominator behaviour is suspicious:

| Cycle | Report                                    | Sonnet stable n | Sonnet pass n | Sonnet pass rate |
|-------|-------------------------------------------|-----------------|---------------|------------------|
| v2.1  | `reports/alignment-eval-20260511T185249Z` | 22              | 19            | 0.8636           |
| v2.2  | `reports/alignment-eval-20260517T154229Z` | 19              | 18            | 0.9474           |
| v2.3  | `reports/alignment-eval-20260517T205353Z` | 22              | 18            | 0.8182           |

Per-cycle pass *count* sits at 18-19 across all three. The
denominator oscillates 22 → 19 → 22 — adding/removing rows from the
stability set is what moves the rate, not Sonnet flipping golden-
match to golden-miss on a fixed row set. The v2.3 close memory
(`project_v23_cycle_close.md` §"Sonnet alignment-eval DIP (NEW v2.3
seed)") flags two confounds:

1. **Stability-denominator oscillation** — re-runs land rows in /
   out of stable-set on majority-vote variance. Some "DIP" is
   denominator inflation, not Sonnet behavioural change.
2. **CLI-degrade artefacts** — v2.3 close memory observed multiple
   `cli governance timeout (>25.0 s); degrading` lines during the
   eval. The degrade path (`src/stream_manager/cli_governance.py:350`)
   returns `None`, which the harness scores as `NONE` action.
   Several v2.3 rows show stable-`NONE` (e.g. `frog7-lifecycle-
   bridge-08`: `NONE,NONE,NONE`) which is the timeout fingerprint —
   not a Sonnet semantic verdict.

This investigation disambiguates: how many of the v2.3 stable-failing
rows are **CLI-degrade fingerprints** (re-run when CLI healthy) vs
**genuine Sonnet drift** (corpus or model rot) vs **stability-
oscillation rows** (rows whose majority bounces).

## Audit procedure

### Step 1 — identify the row flip set

Diff the per-row sonnet `stable` + `maj` columns between v2.2 and
v2.3 reports:

```bash
diff \
  <(awk -F'|' '/^[|] (frog7|ambig|cycle|cycle-|tier|fr-og)/ {gsub(/ /, "", $0); print $2, $5, $6}' reports/alignment-eval-20260517T154229Z.md) \
  <(awk -F'|' '/^[|] (frog7|ambig|cycle|cycle-|tier|fr-og)/ {gsub(/ /, "", $0); print $2, $5, $6}' reports/alignment-eval-20260517T205353Z.md)
```

Bucket each delta row into one of:

| Bucket | v2.2 | v2.3 | Diagnosis |
|--------|------|------|-----------|
| A | stable-PASS  | stable-FAIL  | row regression — Sonnet drift OR golden rot OR CLI-degrade |
| B | stable-PASS  | unstable     | denominator removal — re-test stability not regression |
| C | unstable     | stable-PASS  | denominator add (favourable) |
| D | unstable     | stable-FAIL  | denominator add (unfavourable) — same row may have been stable-fail at v2.1; check |
| E | stable-FAIL  | stable-FAIL  | unchanged failure — no v2.3 contribution |

Bucket A + Bucket D are the rate-dip drivers. Report counts per
bucket.

### Step 2 — CLI-degrade fingerprint check

For every Bucket A and Bucket D row, inspect the v2.3 sonnet `runs`
column for `NONE` count:

- **3× NONE** = certain timeout/degrade artefact. Treat as inconclusive,
  not a Sonnet verdict. Flag the row.
- **1-2× NONE** mixed with semantic actions = partial degrade.
  Inspect json side (`reports/alignment-eval-20260517T205353Z.json`)
  for that row's per-run `cli_path` / `latency_ms` / error markers.
- **0× NONE** = no degrade signal. Row goes to Step 3 (replay).

Record per-row degrade count. If degrade is widespread (≥ 4 rows
with 3×NONE) → root cause is `cli_governance` flakiness at high
contention, **not** Sonnet alignment drift. Recommend FREEZE-on-
content + escalate to Seed v2.4-G (CLI-timeout audit, currently
deferred v2.5) as a v2.5 promotion to 🔴.

### Step 3 — replay procedure (Sonnet-drift test)

For each Bucket A / D row with 0-2× NONE in v2.3, replay against
current Sonnet:

```bash
python -m tools.alignment_eval --rows <row-id-csv> --runs 5 --json-out reports/sonnet-dip-replay-<ts>.json
```

(If `--rows` is not yet supported, run the full eval and grep the
report for the row IDs. Do NOT mutate `tools/alignment_eval.py` to
add the flag in this investigation PR — that would breach
consolidation cycle LOC budget. Note as v2.5 follow-up.)

Then per-row, classify with the v2.2 precedent matrix (`task-
alignment-dip-row-audit.md` §"Step 2 — replay each row"):

| Live (replay) = Golden | v2.3 majority = Golden | Diagnosis |
|------------------------|-----------------------|-----------|
| YES                    | YES                   | False alarm — already passing |
| YES                    | NO                    | Transient — v2.3 sample variance only |
| NO                     | NO                    | Sonnet behavioural shift OR golden rot — escalate per row |
| NO                     | YES                   | Inverse transient — re-baseline if persistent |

For "NO / NO" rows: choose between (a) golden-update PR (corpus
rot — modern Sonnet is right) or (b) REQUIREMENTS amendment (model
drifted away from spec — Sonnet is wrong). Decision per row, with
inline rationale.

### Step 4 — three-cycle trajectory cross-check

Also pull v2.1 majority for each Bucket A / D row (`reports/
alignment-eval-20260511T185249Z.md`). If a v2.3-stable-failing row
ALSO failed at v2.1, the v2.2 PASS is the outlier, not the v2.3
FAIL. This pattern points at **v2.2 sampling artefact**, not v2.3
regression. Record per-row trajectory `v2.1 → v2.2 → v2.3` (e.g.
`unstable → stable-PASS → stable-FAIL`).

## Deliverable

Single markdown report at `reports/sonnet-dip-v23-v24.md` containing:

1. **Bucket counts** (A/B/C/D/E from Step 1).
2. **Per-row table** for Bucket A + Bucket D, columns:
   `id | v2.1 maj | v2.2 maj | v2.3 maj | v2.3 NONE-count | expected | bucket | replay verdict | diagnosis`.
3. **Aggregate degrade signal**: total NONE-majority rows in v2.3
   vs v2.2 vs v2.1.
4. **Recommendation**: ONE of
   - **FREEZE-on-content** — no row-level corpus/Sonnet fix needed;
     dip is denominator / CLI-degrade artefact. v2.4 ship-gate
     records baseline; v2.5 may promote Seed v2.4-G (CLI-timeout
     audit) to 🔴.
   - **FIRE-fix at v2.5** — golden-update PR OR REQUIREMENTS-amendment
     PR identified for specific rows. List row IDs + chosen fix
     class for each.
   - **FIRE-fix at v2.4** — escape-hatch ONLY if a row crossed
     FR-OG-7 floor AND fix is single-row docs-only golden flip.
     Default OFF (consolidation cycle excludes content changes).

NO code change to `tools/alignment_eval.py`, `tests/golden/*`, or
`src/stream_manager/cli_governance.py` in the investigation PR.
This is a **report-only** task.

## Cycle-discipline (Amendment A + Amendment C)

Anchor: v2.4 P0-merge SHA `b35e982` (cycle-tip per Amendment C).

- Production (`src/`): **0 LOC**.
- Tests: **0 LOC**.
- Tooling (`tools/`): **0 LOC** (defer `--rows` flag to v2.5).
- Docs (`reports/sonnet-dip-v23-v24.md` + tick of `docs/v2.4-next-
  steps.md` Seed v2.4-D row): bucket only, advisory under Amendment A.

Consolidation gate net production LOC = **0**. Safe under net ≤ 0
ceiling.

## Surface (ADR-18 Rule 1)

No FROZEN surface touched. `tools/alignment_eval.py` is EVOLVING;
`tests/golden/l4_alignment.jsonl` is EVOLVING. Neither edited here.

## DoD

- [ ] `reports/sonnet-dip-v23-v24.md` written with all 4 sections
      (bucket counts, per-row table, aggregate degrade signal,
      recommendation).
- [ ] Per-row replay verdicts recorded for every Bucket A / D row
      with NONE-count ≤ 2 (Step 3).
- [ ] Three-cycle trajectory column populated from v2.1 baseline
      (Step 4).
- [ ] `docs/v2.4-next-steps.md` Seed v2.4-D row updated:
      `[x] Seed v2.4-D — report at reports/sonnet-dip-v23-v24.md;
      recommendation = FREEZE | FIRE-v2.5 | FIRE-v2.4`.
- [ ] If recommendation = FIRE-v2.5: row IDs + fix class
      (`golden-update` | `REQUIREMENTS-amendment`) explicitly listed
      and routed to v2.4 backlog → v2.5 carry-forward in the v2.4 P2
      close-out.
- [ ] If recommendation = FREEZE: rationale references degrade-
      fingerprint count and denominator-oscillation count
      explicitly. Optionally promote Seed v2.4-G (CLI-timeout audit)
      to 🔴 at v2.5 P0.
- [ ] PR body links Seed v2.4-D anchor + the v2.4 P2 ship-gate
      prompt so close-out can find this report.

## Refs

- `reports/alignment-eval-20260511T185249Z.md` (v2.1 anchor).
- `reports/alignment-eval-20260517T154229Z.md` (v2.2 anchor).
- `reports/alignment-eval-20260517T205353Z.md` (v2.3 ship-gate baseline — the dip).
- `tools/alignment_eval.py` (eval harness; do not edit in this PR).
- `src/stream_manager/cli_governance.py:350` (degrade-on-timeout site;
  emits the `cli governance timeout (>25.0s); degrading` log line).
- `docs/v2.4-next-steps.md` §"Seed v2.4-D".
- `docs/v2.4-task-plan.md` §"PHASE P1 — Sonnet-DIP investigation".
- `docs/prompts/v2.2-orchestration/task-alignment-dip-row-audit.md`
  (closed v2.1→v2.2 audit; matrix re-used in Step 3).
- `project_v23_cycle_close.md` §"Sonnet alignment-eval DIP (NEW v2.3 seed)".
- `project_v22_cycle_close.md` §"Alignment recovery — investigation CLOSED".
- ADR-18 §Amendment A (LOC budget) + §Amendment C (cycle-tip anchor).
