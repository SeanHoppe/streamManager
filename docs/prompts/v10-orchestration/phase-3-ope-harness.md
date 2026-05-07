You are implementing **Phase P3 — Off-policy evaluation (OPE) harness — 5-stage validation gauntlet** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` with v10 P1 + P2 merged.
- PR target: `main`.
- Branch: `feat/v10-ope-harness` (or operator's choice).
- If P2 is not merged, ABORT.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P3 must touch ONLY:

- `rl/ope.py` — new module; OPE estimators (IPS + doubly-robust).
- `rl/validate.py` — new module; 5-stage gauntlet pipeline.
- `rl/cli/validate.py` — CLI entry: `python -m rl.cli.validate --candidate <thresholds.json>`.
- `tests/test_rl_ope.py` — new test file.
- `tests/test_rl_validate.py` — new test file.

NO edits to gov code, NO edits to FROZEN soak driver, alignment-eval, or cassette files. The harness READS from those surfaces; it does not extend them.

Pre-flight grep:

```
grep -nE 'tools/alignment_eval.py|tools/soak_driver.py|tests/fixtures/soak_cassette' .
```

Verify all source surfaces exist on disk; STOP if any missing.

## Task brief

Per the v10 design review §"P4 — Off-policy evaluation before shadow" and §"Issue #3 — Validation strategy", validation is a 5-stage *pipeline*, not a parallel array. Cheap stages reject candidates before expensive stages see them. Stage 5 (shadow Tier 3) is reserved for candidates that survive stages 1–4.

### Validation stages (gauntlet order)

| Stage | Channel | Cost | Reject criterion |
|---|---|---|---|
| 1 | Alignment-eval golden replay | seconds | ANY FR-OG-7 row regresses |
| 2 | IPS estimate over `rl_episodes.db` | seconds | E[reward] < baseline + δ |
| 3 | Cassette replay (Tier 1) | minutes | reward < baseline + δ on cassette p95 |
| 4 | Adversarial synthetic | minutes | reward < baseline + δ on adversarial subset |
| 5 | Shadow Tier 3 soak | ~32 min | reward < baseline + δ OR any constraint floor breached |

Stages 1–4 land in P3. Stage 5 is harness-driven from P5 (a separate phase covers shadow + stop conditions).

### Deliverables

1. **`rl/ope.py`** — off-policy evaluation estimators:

   - `ips_estimate(episodes: list[Episode], target_policy: Callable[[State], Action]) -> tuple[float, float]`
     - Standard inverse-propensity-score estimate with Hájek normalisation. Returns (mean, half-width-95-CI).
     - Production policy at v10.0 is deterministic → `action_propensity = 1.0` for live episodes; this means IPS reduces to direct method on the support and is undefined off-support. Handle off-support gracefully: clip propensity weights to [0.01, 100] and emit warning.
   - `doubly_robust_estimate(episodes: list[Episode], target_policy: Callable, q_model: Callable[[State, Action], float]) -> tuple[float, float]`
     - DR estimator combining IPS and a fitted Q-model. `q_model` is a simple Ridge regressor over (state_features, action) → reward; fit on episodes, evaluate on held-out folds.
   - `cross_validated_dr(episodes, target_policy, k_folds: int = 5) -> tuple[float, float]`
     - 5-fold CV over the episode set; report mean across folds.

2. **`rl/validate.py`** — 5-stage gauntlet pipeline:

   - `Candidate` dataclass: `{thresholds: dict[str, float], manifest_sha: str, seed: int}`.
   - `validate(candidate: Candidate, baseline: Candidate, delta: float = 0.02) -> ValidationReport`:
     - Run stages 1 → 4 in sequence; STOP at first failure; report which stage rejected and why.
     - Each stage is a separate function (`_stage_1_golden`, `_stage_2_ips`, …) so individual stages are unit-testable.

   - **Stage 1 — alignment-golden replay**:
     - Load `tools/alignment_eval.py` golden rows (read-only via `rl/sources/golden.py`).
     - For each row: run gov decision under candidate threshold (offline, in-process — uses the existing `model_router.route` + cached cassette outcomes; NO live `claude -p` calls).
     - Reject if ANY FR-OG-7 row's verdict diverges from golden expected.

   - **Stage 2 — IPS over `rl_episodes.db`**:
     - Sample real episodes (source IN ('live', 'soak')) where state-feature distribution matches the post-v2.0 baseline within KL ≤ τ.
     - Compute `cross_validated_dr(episodes, target_policy=candidate, k_folds=5)`.
     - Reject if mean < `baseline_reward + delta`.

   - **Stage 3 — cassette replay**:
     - Run `tools/soak_driver.py --cli-replay tests/fixtures/soak_cassette_<latest>.jsonl` with `BRIDGE_L4_FALLBACK_CONFIDENCE=<candidate L4 threshold>` env override (read-only env injection — NO edit to soak_driver).
     - Parse the resulting report; extract `cassette p95`, fallback fire rate, action distribution.
     - Reject if cassette p95 regresses > 10 % vs baseline cassette p95 OR if action distribution shifts > 20 % (stages-1–4 are about reward; stage 3 also catches plumbing regressions per ADR-17).

   - **Stage 4 — adversarial synthetic**:
     - Load `rl.sources.review.iter_episodes()` + `rl.sources.probe.iter_episodes()`.
     - Construct an adversarial subset: BLOCK-expected probe rows + caveman-review-derived stress rows.
     - Compute reward over the subset under candidate policy.
     - Reject if reward < baseline reward on the adversarial subset.

3. **`rl/cli/validate.py`** — CLI entry point:
   ```
   python -m rl.cli.validate \
     --candidate path/to/proposed_thresholds.json \
     --baseline  path/to/production_thresholds.json \
     --delta 0.02 \
     --report-path reports/v10-validate-<UTC>Z.md
   ```
   Output is a Markdown report with one section per stage, exit code 0 on PASS, 1 on REJECT (stage + reason in last line of report).

4. **Tests** — `tests/test_rl_ope.py`:
   - `test_ips_uniform_propensity_matches_mean_reward` — deterministic propensity → IPS reduces to mean reward.
   - `test_ips_clips_extreme_weights` — propensity 0 → clipped to 0.01.
   - `test_dr_better_than_ips_on_synthetic` — generate synthetic episodes where Q-model has signal → DR variance < IPS variance.
   - `test_cv_dr_5_fold_returns_mean_across_folds` — folds aggregated correctly.

5. **Tests** — `tests/test_rl_validate.py`:
   - `test_stage_1_rejects_fr_og_7_regression` — synthetic candidate that flips an FR-OG-7 row → stage 1 reject.
   - `test_stage_2_rejects_low_ips` — fixture episodes engineered s.t. candidate has ips_mean < baseline + delta → stage 2 reject.
   - `test_stage_3_rejects_cassette_p95_regression` — fixture cassette + candidate threshold pair that regresses p95 > 10 % → stage 3 reject.
   - `test_stage_4_rejects_adversarial_drop` — adversarial subset reward < baseline → stage 4 reject.
   - `test_pipeline_short_circuits` — when stage N rejects, stages N+1..4 do NOT run (verifiable via spy / counters).
   - `test_pass_through_returns_full_report` — well-behaved candidate passes 1–4; report has 4 PASS sections.
   - `test_no_live_cli_calls` — pipeline runs to completion with `PATH` scrubbed of `claude` binary (cassette replay must not require live model).

### OPE-only invariant

P3 changes NO governance behaviour and runs ZERO live `claude -p` calls. The CLI must complete with `claude` absent from PATH.

### LOC budget

P3 net add ≤ 600 lines (slightly higher cap because OPE math is dense; stage code is small). If draft exceeds, scope back DR estimator to IPS-only and defer DR to a follow-up.

## DOD

- [ ] `rl/{ope,validate}.py` + `rl/cli/validate.py` created
- [ ] `tests/test_rl_{ope,validate}.py` created
- [ ] Pipeline short-circuits on first failure; test covers it
- [ ] No live `claude -p` calls in any test or CLI run
- [ ] Stage 1 (golden) is the FIRST stage and rejects on ANY FR-OG-7 regression (zero tolerance)
- [ ] LOC budget ≤ 600 net add
- [ ] All v1.7–v2.0 tests green
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `rl:`

Report back when PR is open with: PR URL, diff stat, file list, sample validation report from running the CLI on the current production thresholds against themselves (sanity: must PASS all 4 stages).
