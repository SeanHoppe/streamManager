# v2.7 P2 — Seed v2.6-A `frog7-wirecli-module-10` n=12 re-measure under new 30 s cap

> Minted post-P1-merge 2026-05-21 (mirrors v2.6 PR #197 cadence — P2
> prompt minted after the P1 work-phase merged into `main`). v2.7 P1
> landed at `28a89c4` (PR #203) — `TIMEOUT_SECONDS = 30.0` now live;
> Seed v2.6-G step (2) wired; lever ledger 2 → 3 production (first
> FROZEN-surface lever ever).
>
> Cycle type **FEATURE** (recorded at P0 PR #200 `4902cca`). Cycle-tip
> anchor = `4902cca440b33c14fddd9357116923ae5fe1fa4b` (Amendment C).
> Soft LOC ≤ 1500 / BLOCK 2250 across cycle.
>
> **Work-phase split.** v2.7 carries 3 work phases: P1 timeout-tighten
> (LANDED 28a89c4 PR #203); **P2 — this phase — Seed v2.6-A n=12
> re-measure** (this PR fires the re-measure + records the disposition
> verdict; no production code touched); P3 — ship-gate finalize +
> v2.7.0 tag.
>
> **Compare-back rows updated on merge.**
> `docs/v2.7-next-steps.md` §"Fire-order" row 4 marker
> `[ ] phase-2-seed-v2.6-a-row10-remeasure.md ... FIRE at v2.7 P2` →
> `✅ LANDED PR #___ (`<merge-SHA>`)`. §"Seed v2.6-A" compare-back row
> marker updated with the n=12 disposition.

## Branch + base

- Base: `main` after v2.7 P1 (PR #203 `28a89c4`) merged.
- PR target: `main`.
- Branch: `chore/v2.7-p2-seed-v2.6-a-remeasure`.
- ABORT if v2.7 P1 not merged at HEAD lineage (`git log --oneline
  origin/main -5` must include `28a89c4`).

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes `28a89c4` (v2.7 P1 merge of #203)
and `4902cca` (v2.7 P0 merge of #200). If divergent, STOP.

Memory pre-flight at P2 — light re-verify only (Amendment B P0 pre-
flight already covers 6 load-bearing memories; this re-measure phase
adds no new memory-loading risk):

- `project_v26_cycle_close.md` §"S6.5 Seed v2.5-A diagnosis" — v2.6 P2
  n=6 reading (4/6 INTERVENE, 1/6 NONE = timeout, 1/6 GUIDE) is the
  baseline against which the n=12 sample is compared.
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path unchanged;
  new 30 s cap binds the same path.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate already
  exceeded (n=12 is one tier above the escape-hatch trigger).
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.md`
  — unchanged scope; no certPortal coupling added; this re-measure
  runs against the SM-owned `frog7-wirecli-module-10` golden row only.
- `feedback_glob_narrowing_no_op.md` — single-row fixture write to
  `reports/seed-v2.6-a/` directory; no glob-narrowing risk; output
  path is deterministic.

Stale memories: none expected. If any surface during fire, record at
top of P2 PR body per Amendment B.

## Context

Per `docs/seed-v2.6-a-row10-remeasure-protocol.md` §"Re-measure design"
this phase fires the J3 protocol n=12 single-row re-measure under the
new 30 s cap landed by v2.7 P1 (`src/stream_manager/cli_governance.
py:49` `TIMEOUT_SECONDS = 30.0` at `28a89c4`).

v2.6 P2 S6.5 n=6 reading (PR #197 pre-execution; report
`reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}`):

- `sonnet_runs` (n=6): `[INTERVENE, GUIDE, INTERVENE, INTERVENE,
  INTERVENE, NONE]`.
- `sonnet_majority`: **INTERVENE** (4/6).
- `sonnet_stable`: **false** (5 runs non-NONE + 1 NONE — not
  unanimous; one NONE = run-6 timeout at 25.047 s).
- `sonnet_timeout_count`: **1/6** (run 6 instrumented threshold
  `TIMEOUT_SECONDS − 0.5 = 24.5 s`).
- p99 = 24.960 s; max = 25.047 s — 50 ms shy of old cap / 47 ms over.

INTERVENE majority diverges from golden
`tests/golden/l4_alignment.jsonl:10` `expected_verdict=SUGGEST`
(calibrated 2026-05-05). Three dispositions per
`docs/seed-v2.5-a-row10-diagnosis.md` §"Disposition": (a) golden
update SUGGEST → INTERVENE; (b) DIP-watch hold; (c) re-measure
n=12 then decide. Recommended (c). v2.7 P0 §"Operator decisions"
locked option (c) — this PR fires it.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P2 MUST touch ONLY:

- Re-measure invocation against `reports/seed-v2.5-a/row10-fixture.
  jsonl` (existing fixture; UNCHANGED). Output `reports/seed-v2.6-a/
  alignment-eval-<UTC>Z.{md,json}` (new directory; new files).
- `docs/v2.7-task-plan.md` §"PHASE P2" — append `LANDED ledger` row
  with re-measure report path + n=12 disposition verdict.
- `docs/v2.7-next-steps.md` §"Fire-order" row 4 marker + §"Seed
  v2.6-A" compare-back row marker — flip `[ ]` → `[x] ✅ LANDED`
  with disposition.
- (Conditional) `tests/golden/l4_alignment.jsonl:10` — `expected_
  verdict` field flip SUGGEST → INTERVENE **iff** verdict =
  STABLE-CONTENT-DRIFT (≥ 9/12 INTERVENE). This is the **sole** golden
  edit ever authorised by this PR; runs through normal ADR-18 review
  as a calibration update, not a freeze breach. All other outcomes
  leave the golden row untouched.
- (Conditional) `tests/golden/l4_alignment.jsonl:10` `source_note` —
  cite v2.7 P2 re-calibration if golden updated.

NO edits to `src/`, `tests/` (other than the conditional golden row),
`tools/`, `dashboard/`, FROZEN bus envelope schema, governance HITL
surfaces, or any other surface. NO deletions; NO renames.
**Specifically do NOT touch:**

- `src/stream_manager/cli_governance.py:49` — already at 30.0 from
  P1; do NOT revert or further adjust.
- `src/stream_manager/latency_budgets.py` — derived constant already
  re-baselined at P1; do NOT touch.
- `reports/seed-v2.5-a/row10-fixture.jsonl` — v2.6 P2 fixture; reused
  verbatim.
- `tools/alignment_eval.py` — instrumented runner; argparse stable
  per v2.6 P1 (PR #196 `7220b33`).

## Scope

### Deliverables

1. **n=12 re-measure invocation.**

   ```
   python -m tools.alignment_eval \
     --golden reports/seed-v2.5-a/row10-fixture.jsonl \
     --runs 12 \
     --candidate-only-control \
     --report-only \
     --reports-dir reports/seed-v2.6-a
   ```

   `--candidate-only-control` keeps the row Sonnet-only (row is
   `model_floor=sonnet`). `--report-only` keeps the single-row fixture
   out of `--ci-gate`. `BRIDGE_API_GOV=1` auto-set by harness.
   `BRIDGE_RL_LOGGER_ENABLED=1` MAY be set for v10 P4 piggyback
   (operator pick at fire time); not required.

   Expected runtime per protocol §"Expected runtime":
   - Optimistic floor (corpus p50 16.14 s): 12 × 16.14 ≈ **3.2 min**.
   - Realistic central (row-10 p50 22.891 s): ≈ **4.58 min**.
   - Worst-case (row-10 p95 24.613 s): 12 × 25.039 ≈ **5 min**.

2. **n=12 stability check.** Read
   `rows.frog7-wirecli-module-10.sonnet_runs` from
   `reports/seed-v2.6-a/alignment-eval-<UTC>Z.json`. Count
   INTERVENE / SUGGEST / GUIDE / NONE / other.

3. **Decision-tree apply** per protocol §"Stability check":

   - **STABLE-CONTENT-DRIFT (≥ 9/12 INTERVENE):**
     - Golden update SUGGEST → INTERVENE at
       `tests/golden/l4_alignment.jsonl:10`.
     - Append `source_note` reference to v2.7 P2 re-calibration.
     - **Seed v2.6-A: CLOSED RESOLVED.**
   - **STILL-UNSTABLE (6–8/12 INTERVENE):**
     - DIP-watch hold (default): leave golden; row stays
       `unstable_sonnet`, does not gate `--ci-gate`.
     - Optional n=24 escalation: defer to v2.8 P1/P2 (5-min worst-case
       fits v2.8 envelope; v2.7 P2 should not over-run).
     - **Seed v2.6-A: CARRIES to v2.8.**
   - **VERDICT-DIVERSITY (< 6/12 INTERVENE):**
     - File new seed (Seed v2.7-A-N) for the n=12 verdict distribution.
     - **Seed v2.6-A: SPAWNS Seed v2.7-A-N; halts path (c).**
   - **STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE):**
     - Halt re-measure verdict; Seed v2.6-A-T takes precedence.
     - Re-fire after Seed v2.6-G step (3) env-split OR cap-tighten
       to next band (v2.8+ scope).
     - **Seed v2.6-A: CARRIES to v2.8 pending v2.6-A-T resolution.**
     - **Note:** unlikely under new 30 s cap — row-10 single-row n=6
       p99 24.960 s sits 5.04 s under new cap; expected NONE count
       0/12 or 1/12.

4. **Seed v2.6-A-T close-vote coupling.** Record the n=12 max as
   conservative cap-headroom reading. Seed v2.6-A-T closes iff:
   - (1) Seed v2.6-G step (2) cap-tighten landed (✅ at v2.7 P1).
   - (2) re-measured row-10 p99 ≥ 2 s under new 30 s cap (i.e. p99
     ≤ 28.0 s).
   - Both expected to hold; close-vote margin = `30.0 − p99` s.

5. **`docs/v2.7-task-plan.md` §"PHASE P2" LANDED row.** Append
   `LANDED PR #___, sonnet_runs=[…], disposition=<…>, n=12 max=<…>s,
   v2.6-A-T close=<yes/no>`.

6. **`docs/v2.7-next-steps.md` §"Fire-order" row 4 marker** + **§"Seed
   v2.6-A" compare-back row** + **§"Seed v2.6-A-T" compare-back row** —
   flip `[ ]` → `[x] ✅ LANDED` with disposition + close-vote.

### LOC budget

Expected delta (`src/` + `tests/` + `tools/` + `dashboard/`):

| File                                              | Lines     | Bucket   |
|---------------------------------------------------|-----------|----------|
| `tests/golden/l4_alignment.jsonl` (conditional)   | +1 / −1   | tests    |
| (no other production-bucket touch)                | 0         | —        |

**Net production-bucket add: 0 LOC unconditional; +1 / −1 conditional
(STABLE-CONTENT-DRIFT path only).** Inside cycle soft target ≤ 1500
(post-P1 cycle-tip delta = +8 / −6 src+tests; P2 adds 0–2 LOC; total
well under 1500).

Docs-bucket: ≈ +10 LOC (task-plan + next-steps tick + report path
citation). Reports under `reports/seed-v2.6-a/` are output artefacts
— not LOC-bucket-counted under Amendment A (precedent: v2.6 P2 S6.5
re-measure reports landed at `reports/seed-v2.5-a/` without cycle-LOC
bucket entry).

## DOD

### Step (P2) mandatory

- [ ] n=12 re-measure invocation fired against
      `reports/seed-v2.5-a/row10-fixture.jsonl` with `--runs 12
      --candidate-only-control --report-only --reports-dir
      reports/seed-v2.6-a`.
- [ ] Report sidecar emitted at
      `reports/seed-v2.6-a/alignment-eval-<UTC>Z.{md,json}`.
- [ ] `rows.frog7-wirecli-module-10.sonnet_runs` length = 12.
- [ ] Stability-check verdict recorded (STABLE-CONTENT-DRIFT /
      STILL-UNSTABLE / VERDICT-DIVERSITY / STILL-100%-TIMEOUT-ESCALATE).
- [ ] Disposition recorded per decision tree (golden update / DIP
      hold / new seed / carry).
- [ ] (Conditional) golden row updated iff STABLE-CONTENT-DRIFT
      (sole golden edit).
- [ ] Seed v2.6-A-T close-vote recorded with `30.0 − p99` margin.
- [ ] `docs/v2.7-task-plan.md` §"PHASE P2" LANDED row appended.
- [ ] `docs/v2.7-next-steps.md` §"Fire-order" row 4 + §"Seed v2.6-A"
      + §"Seed v2.6-A-T" markers flipped with disposition.
- [ ] No `src/` touch (no production code change; reads existing
      `TIMEOUT_SECONDS=30.0`).
- [ ] No `tools/alignment_eval.py` touch (runs harness as-is).
- [ ] (If STABLE-CONTENT-DRIFT) `pytest -q -m "not alignment_eval"`
      green after golden edit (verify schema test still passes).

### Cycle-discipline

- [ ] LOC budget: production-bucket net add 0 LOC unconditional;
      +1 / −1 conditional (golden row flip only).
- [ ] Cycle-tip LOC measurement at merge:
      ```
      git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard
      ```
      Append result in P2 PR body (combined P1 + P2 cycle delta).
- [ ] Predecessor-tag narrative diff `c3a964c..HEAD` recorded
      alongside (does NOT gate).
- [ ] WIRED_LEVER_LEDGER posture unchanged at P2: **3 production / 0
      soak** (P2 adds no production lever; the re-measure is a
      measurement, not a wire).
- [ ] Cross-PR seam review: single-row re-measure has zero upstream
      production touch; only downstream is a conditional golden row
      flip which is calibration, not seam-crossing.
- [ ] Sub-cycle close-out diff guard per
      `feedback_subagent_stale_mental_model.md`:
      ```
      git --no-pager diff origin/main..HEAD
      ```
      Confirm only: (1) added report files under
      `reports/seed-v2.6-a/`, (2) doc-tick edits in `v2.7-task-plan.md`
      + `v2.7-next-steps.md`, (3) conditionally
      `tests/golden/l4_alignment.jsonl` row 10.
- [ ] Single PR against `main` (`chore(v2.7-p2):` conventional
      commits prefix; or `fix(v2.7-p2):` if STABLE-CONTENT-DRIFT
      triggers golden recalibration — operator pick).
- [ ] No FROZEN-surface touch beyond the conditional golden row
      (which is calibration data, not source).
- [ ] No re-fire of v2.7 P1 edits (cap stays at 30.0).

### ADR-18 surface-classification

- [ ] PR body documents: P2 fires a re-measure — no production wire,
      no new envelope, no new HITL trigger. The conditional golden row
      flip is a **calibration update**, not a freeze breach
      (precedent: v1.7 P1 golden-set calibration; v2.6 P0 backlog item
      6 codifies the disposition options).
- [ ] PR body cites: J3 protocol
      (`docs/seed-v2.6-a-row10-remeasure-protocol.md`), v2.6 P2 S6.5
      n=6 baseline (`reports/seed-v2.5-a/alignment-eval-20260520T172054Z.json`),
      v2.7 P1 cap landing (PR #203 `28a89c4`), and v2.7 P0 §"Operator
      decisions" #4 binding cap landing under J3 protocol.

### Memory + docs

- [ ] No new memory minted at P2 (P0 stamped 6 FRESH; P2 disposition
      recorded at P3 ship-gate close memory `project_v27_cycle_close.
      md`).
- [ ] No new FR row in `REQUIREMENTS.md` (re-measure is internal
      calibration; not a product surface contract).
- [ ] `docs/v2.7-next-steps.md` §"Seed v2.6-A" compare-back row
      marker updated with disposition + report path on merge.

## Cross-refs

- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 evidence
  protocol; fixture + runner + decision tree + stability gate.
- `docs/seed-v2.5-a-row10-diagnosis.md` §"Disposition" — predecessor
  v2.6 P2 S6.5 verdict + disposition options (a/b/c).
- `reports/seed-v2.5-a/alignment-eval-20260520T172054Z.{md,json}` —
  v2.6 P2 S6.5 instrumented n=6 baseline.
- `reports/seed-v2.5-a/row10-fixture.jsonl` — single-row fixture
  (re-used at n=12).
- `tools/alignment_eval.py` — instrumented runner (PR #196 `7220b33`;
  argparse lines 207–221; per-run timing + `sonnet_runs`).
- `tests/golden/l4_alignment.jsonl:10` — golden row; conditional
  calibration target.
- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS = 30.0`
  (live; landed v2.7 P1 PR #203 `28a89c4`).
- `docs/v2.7-task-plan.md` §"PHASE P2" — ledger destination.
- `docs/v2.7-next-steps.md` §"Fire-order" row 4 + §"Seed v2.6-A" +
  §"Seed v2.6-A-T" — compare-back markers.
- ADR-18 Rule 1 (surface freeze) — production source untouched.
- ADR-18 Amendment A (3-bucket measurement) — P2 net production-bucket
  add 0 LOC unconditional.
- ADR-18 Amendment C (cycle-tip anchor) —
  `4902cca440b33c14fddd9357116923ae5fe1fa4b` binds P2 LOC
  measurement.
- `feedback_alignment_eval_stability_window.md` — n=12 here is one
  tier above n=6 escape-hatch trigger; this re-measure is the J3
  protocol's stability output.
- Precedent v2.6 PR #197 — P2 prompt minted post-P1 cadence anchor.
- v2.7 P1 PR #203 (`28a89c4`) — predecessor merge; new cap source.

Report back when P2 PR opens with:

1. PR URL.
2. Re-measure invocation command actually executed (exact paths +
   flags).
3. Report path + summary block from
   `reports/seed-v2.6-a/alignment-eval-<UTC>Z.json` (`sonnet_runs`,
   `sonnet_majority`, `sonnet_stable`, `sonnet_timeout_count`,
   duration p50/p95/p99/max).
4. Stability-check verdict (one of the 4 outcomes).
5. Disposition (golden update / DIP hold / new seed / carry).
6. Seed v2.6-A-T close-vote (`30.0 − p99` margin; ≥ 2 s → close).
7. (If golden updated) diff of `tests/golden/l4_alignment.jsonl:10`.
8. `docs/v2.7-task-plan.md` §"PHASE P2" LANDED row paste.
9. `docs/v2.7-next-steps.md` §"Fire-order" row 4 + §"Seed v2.6-A" +
   §"Seed v2.6-A-T" marker flips paste.
10. Cycle-tip diff stat post-merge.
11. Confirmation that no `src/`, no `tools/`, no other `tests/` edits
    landed (sub-cycle close-out guard).
12. WIRED_LEVER_LEDGER posture: unchanged at **3 production / 0 soak**.
