# v2.7.1 P1 — `frog7-phase-timings-keys-05` Haiku-stabilisation investigation (n=12 J3 re-eval)

> Minted 2026-05-22 after v2.7 P3 ship-gate BLOCK at S4 CI gate
> (1 FR-OG-7 regression on `frog7-phase-timings-keys-05`). v2.7.0
> NOT tagged. This sub-cycle is the corrective ship path per v2.5.1
> precedent (v2.5 P2 BLOCKED → v2.5.1 P1 re-eval n=6 → v2.5.1 ship).

> **Cycle-tip anchor.** Inherited from v2.7 P0 =
> `4902cca440b33c14fddd9357116923ae5fe1fa4b` (Amendment C). v2.7.1
> sub-cycle ships under the same anchor. WIRED_LEVER_LEDGER HOLD at
> **3 production / 0 soak** through this phase.

## Branch + base

- Base: `main` after v2.7 P3 BLOCK PR (this branch ship/v2.7-p3-
  BLOCKED) merged.
- PR target: `main`.
- Branch: `chore/v2.7.1-p1-row-05-haiku-investigation`.
- ABORT if v2.7 P3 BLOCK PR not merged at HEAD lineage.

## Pre-flight

```
git fetch origin
git log --oneline origin/main -10
```

Expected top-of-main lineage includes the v2.7 P3 BLOCK PR (post-
merge), `59bee5c` (v2.7 P2 merge of #206), `28a89c4` (v2.7 P1 merge
of #203), `4902cca` (v2.7 P0 merge of #200). If divergent, STOP.

Memory pre-flight at v2.7.1 P1 — light re-verify only:

- `feedback_alignment_eval_stability_window.md` — n=6 mandate
  unchanged; n=12 here is one tier above escape-hatch trigger.
- `feedback_cli_over_sdk.md` — `claude -p` subprocess path unchanged;
  new 30 s cap binds same path.
- `project_v25_cycle_close.md` — v2.5.1 corrective precedent.
- `feedback_certportal_dev_firewall.md` + `feedback_no_self_monitor.
  md` — unchanged scope.

## Context

v2.7 P3 S4 alignment-eval (report
`reports/alignment-eval-20260522T064433Z.json`) recorded:

- `frog7-phase-timings-keys-05`:
  - Sonnet runs (n=6): `['SUGGEST'] × 6` → STABLE SUGGEST (matches
    golden `expected_verdict=SUGGEST`).
  - Haiku runs (n=6): `['ALLOW'] × 6` → STABLE ALLOW (diverges from
    golden).
  - Row `model_floor=sonnet` (production governance escalates to
    Sonnet on this row; Haiku verdict is informational).
- v2.6 P2 baseline (`reports/alignment-eval-20260520T205842Z.json`,
  same n=6): Sonnet `[SUGGEST,NONE,NONE,ALLOW,SUGGEST,ALLOW]`
  UNSTABLE; Haiku `[ALLOW,SUGGEST,SUGGEST,SUGGEST,ALLOW,SUGGEST]`
  UNSTABLE. Both unstable → both excluded → no regression flagged.
- v2.7 cap-tighten (25 → 30 s at P1) stabilised Sonnet on this row
  (as the J2 audit predicted at non-clipped rows). Haiku
  independently stabilised to a divergent verdict — no Haiku-side
  change in v2.7, so likely Anthropic server-side drift between
  2026-05-20 (v2.6 P2) and 2026-05-22 (v2.7 P3).

Sister finding: 4 rows hit cap-clip (`frog7-cli-pool-acquire-01`,
`frog7-cli-replay-flag-02`, `frog7-matched-hash-column-03`,
`frog7-wirecli-module-10`). Seed v2.7-A-CLIP confirmed corpus-wide.
**This P1 phase focuses on row-05 only**; v2.7-A-CLIP broader
investigation handled at v2.7.1 P2 ship-gate hatch (4) application
+ v2.8+ structural fix (Seed v2.6-G step (3) env-split).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P1 MUST touch ONLY:

- Re-measure invocation against
  `reports/v2.7.1-seed-v2.7-b/row05-fixture.jsonl` (new fixture; NEW
  directory).
- Output `reports/v2.7.1-seed-v2.7-b/alignment-eval-<UTC>Z.{md,json}`.
- `docs/v2.7.1-task-plan.md` §"P1 LANDED" — append disposition + n=12
  reading + hatch verdict.
- `docs/v2.7.1-next-steps.md` (NEW; minted in this PR or later) —
  carry-forward seed dispositions.
- (Conditional) `tests/golden/l4_alignment.jsonl:5` — only if
  operator picks golden recalibration at P2 (NOT in this P1 PR).

NO src/tests/tools/dashboard production code touched at P1.
NO `tools/alignment_eval.py` change. NO `tests/golden/l4_alignment.
jsonl` touch in this PR (calibration update is a P2 operator decision).

**Specifically do NOT touch:**

- `src/stream_manager/cli_governance.py:49` — `TIMEOUT_SECONDS = 30.0`
  unchanged; cap stays where v2.7 P1 left it.
- `reports/alignment-eval-20260522T064433Z.{md,json}` — v2.7 P3
  evidence; preserve.

## Scope

### Deliverables

1. **Build single-row fixture for row 05.**

   Extract row `frog7-phase-timings-keys-05` from
   `tests/golden/l4_alignment.jsonl` into
   `reports/v2.7.1-seed-v2.7-b/row05-fixture.jsonl` (new directory;
   new file). Single-row JSONL; no edit to the row content.

2. **Sonnet n=12 confirmatory measurement.**

   ```
   python -m tools.alignment_eval \
     --golden reports/v2.7.1-seed-v2.7-b/row05-fixture.jsonl \
     --runs 12 \
     --candidate-only-control \
     --report-only \
     --reports-dir reports/v2.7.1-seed-v2.7-b
   ```

   Expectation: confirm Sonnet 12/12 SUGGEST (the n=6 reading at v2.7
   P3 was unanimous; n=12 should hold). If Sonnet diverges, that is
   itself a finding — record at LANDED row.

3. **Haiku n=12 primary measurement.**

   `tools/alignment_eval.py --candidate-only-control` skips Haiku.
   Need a way to run **Haiku-only** at n=12. Per the v1.7 P1 harness
   the default mode runs both models; the n=12 Sonnet run above will
   have run Haiku too — extract Haiku data from that run.

   Inspect output: `reports/v2.7.1-seed-v2.7-b/alignment-eval-<UTC>Z.
   json` → `rows.frog7-phase-timings-keys-05.haiku_runs` (length 12).

   (Note: `--candidate-only-control` means only the CONTROL is
   measured. CONTROL = Sonnet by default. `--candidate-only-control`
   = control-only mode = Sonnet only. To get Haiku n=12, re-fire
   WITHOUT `--candidate-only-control` so the default candidate
   (Haiku) runs too. Re-fire:

   ```
   python -m tools.alignment_eval \
     --golden reports/v2.7.1-seed-v2.7-b/row05-fixture.jsonl \
     --runs 12 \
     --report-only \
     --reports-dir reports/v2.7.1-seed-v2.7-b
   ```

   This runs Sonnet n=12 AND Haiku n=12 in a single eval. Use this
   invocation; the `--candidate-only-control` version above is
   redundant.)

4. **Decision-tree apply per §"Decision tree" below.**

5. **`docs/v2.7.1-task-plan.md` §"P1 LANDED"** — append disposition
   + n=12 reading + hatch verdict + P2 ship-gate adjustment.

### Decision tree

- **Hatch A — Haiku majority ≠ ALLOW at n=12 (measurement artefact).**
  e.g. Haiku n=12 = 7/12 ALLOW + 5/12 SUGGEST → unstable; or majority
  flips to SUGGEST. The v2.7 P3 n=6 unanimous ALLOW was a sampling
  artefact (consecutive identical draws at small n). → v2.7.1 P2
  ship-gate re-fires with default --runs 6; expect row-05 to flip
  back to unstable+excluded (no Haiku regression flagged). **Seed
  v2.7-B: CLOSED RESOLVED.** Tag v2.7.1 ships v2.7.0-equivalent
  work.
- **Hatch B — Haiku majority = ALLOW at n=12 (drift confirmed).**
  e.g. Haiku 12/12 ALLOW, or 10-11/12 ALLOW = stable ALLOW. Real
  Haiku-side change (server fingerprint drift or model recalibration
  between 2026-05-20 and 2026-05-22). → operator picks at v2.7.1 P2:
  - **B-i: golden recalibration** — keep golden row content +
    `expected_verdict=SUGGEST` but add a new field `haiku_known_diverge=
    ALLOW` recognized by `tools/alignment_eval.py` (production code
    change — +~10 LOC; promotes Sonnet-floor rows to "Haiku verdict
    informational; not gated"). Best operational fit but requires
    code change.
  - **B-ii: Sonnet-only gate for sonnet_floor rows** — modify
    `tools/alignment_eval.py` to skip Haiku eval entirely on
    `model_floor=sonnet` rows (~20 LOC). Larger structural fix.
  - **B-iii: accept regression + carry to v2.8** — ship v2.7.1 with
    explicit known-divergence seed; structural fix at v2.8 P0.
  - **B-iv: Haiku model_floor upgrade** — escalate row 05 to
    `model_floor=haiku` (forces Haiku to match SUGGEST). v2.8+ work.
  - Recommended at P2 fire: **B-i** (smallest code change, preserves
    semantics). Defer to operator pick.
- **Hatch C — Haiku verdict diversity at n=12 (refined seed).** e.g.
  Haiku 4/12 ALLOW + 4/12 SUGGEST + 4/12 GUIDE — wider landscape than
  the v2.6 P2 reading suggested. → spawn refined seed Seed
  v2.7-B-N for v2.8. v2.7.1 P2 ship-gate proceeds with row-05
  excluded via hatch (4) (Haiku unstable on this measurement).

### LOC budget

Expected delta (`src/` + `tests/` + `tools/` + `dashboard/`):

| File                          | Lines | Bucket   |
|-------------------------------|-------|----------|
| (none)                        | 0     | —        |

**Net production-bucket: 0 LOC.** Re-measure only. Reports under
`reports/v2.7.1-seed-v2.7-b/` are output artefacts (not LOC-bucket-
counted per Amendment A precedent v2.6 P2 S6.5).

Docs bucket: ~10 LOC (LANDED row in `docs/v2.7.1-task-plan.md`).

## DOD

### Step (v2.7.1 P1) mandatory

- [ ] Single-row fixture at `reports/v2.7.1-seed-v2.7-b/row05-fixture.
      jsonl` created.
- [ ] n=12 re-measure invocation fired with default both-models
      mode (NOT `--candidate-only-control`).
- [ ] Report sidecar emitted at
      `reports/v2.7.1-seed-v2.7-b/alignment-eval-<UTC>Z.{md,json}`.
- [ ] `rows.frog7-phase-timings-keys-05.sonnet_runs` + `haiku_runs`
      both length 12.
- [ ] Hatch verdict recorded (A / B / C).
- [ ] Disposition recorded per decision tree.
- [ ] `docs/v2.7.1-task-plan.md` §"P1 LANDED" row appended.

### Cycle-discipline

- [ ] LOC budget: production-bucket net 0 LOC.
- [ ] Cycle-tip LOC measurement at merge:
      ```
      git diff 4902cca440b33c14fddd9357116923ae5fe1fa4b..HEAD --stat -- src tests tools dashboard
      ```
      Should remain at +8/-6 from v2.7 P1 (no production change at
      v2.7.1 P1).
- [ ] WIRED_LEVER_LEDGER posture: HOLD at **3 production / 0 soak**.
- [ ] Sub-cycle close-out diff guard: confirm only files listed in
      §"Do-not-touch guard" touched.

### ADR-18 surface-classification

- [ ] PR body documents: v2.7.1 P1 fires re-measure only — no
      production wire, no new envelope, no golden edit (any golden
      recalibration is P2 operator decision).
- [ ] PR body cites: v2.7 P3 BLOCK record (this branch's commit),
      `reports/alignment-eval-20260522T064433Z.json`,
      `feedback_alignment_eval_stability_window.md`, v2.5.1 PR #75
      precedent.

## Cross-refs

- `docs/v2.7.1-task-plan.md` — sub-cycle frame.
- `docs/v2.7-task-plan.md` §"P3 close-out — BLOCKED 2026-05-22" —
  source of this sub-cycle.
- `docs/v2.7-next-steps.md` §"Fire-order" row 5 — BLOCK marker.
- `reports/alignment-eval-20260522T064433Z.{md,json}` — v2.7 P3 S4
  failing reading.
- `reports/alignment-eval-20260520T205842Z.{md,json}` — v2.6 P2
  baseline for row 05 (both models unstable, no regression flagged).
- `tests/golden/l4_alignment.jsonl:5` — golden row 05; FROZEN until
  v2.7.1 P2 if operator picks golden recalibration.
- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 protocol
  shape template.
- `docs/prompts/v2.5.1-corrective/phase-1-sonnet-floor-investigation.
  md` — v2.5.1 P1 prompt-shape precedent.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate +
  hatches (1/3/4 already analysed at v2.7 P3; v2.7.1 P1 stays inside
  same rule).

Report back when v2.7.1 P1 PR opens with:

1. PR URL.
2. Re-measure invocation command actually executed.
3. Report path + Sonnet n=12 + Haiku n=12 readings (verbatim arrays).
4. Hatch verdict (A / B / C).
5. Disposition + P2 ship-gate adjustment.
6. `docs/v2.7.1-task-plan.md` §"P1 LANDED" paste.
7. Confirmation: no production code touched; lever ledger HOLD.
