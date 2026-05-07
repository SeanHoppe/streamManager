You are implementing **Phase P4 — Constrained Thompson-sampling bandit trainer (v10.1)** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` with v10 P1 + P2 + P3 merged.
- PR target: `main`.
- Branch: `feat/v10-bandit-trainer` (or operator's choice).
- If `rl_episodes.db` has < 200 live episodes, ABORT (per seed v10.0 → v10.1 promotion gate).
- If P3 OPE harness CLI is missing, ABORT — trainer DEPENDS on `rl.validate.validate(...)`.

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P4 must touch ONLY:

- `rl/bandit.py` — new module; constrained Beta-Bernoulli Thompson sampler.
- `rl/constraints.py` — new module; CMDP feasibility filter.
- `rl/cli/train.py` — new CLI: `python -m rl.cli.train --episodes <db> --proposals <out>`.
- `rl/manifest.py` — new module; reproducibility manifest writer.
- `tests/test_rl_bandit.py`, `tests/test_rl_constraints.py`, `tests/test_rl_manifest.py` — new test files.

NO edits to gov code. NO live `claude -p` calls. Trainer is pure numpy / scipy / sqlite3 — zero LLM tokens (per seed deterministic-Python thesis).

Pre-flight grep:

```
grep -nE 'np\.random|scipy\.stats|sqlite3' rl/
```

After P4 edits this should resolve to `rl/bandit.py` + `rl/constraints.py` + adapters only. NO numpy in `rl/episode_logger.py` (fast hot-path stays import-light).

## Task brief

Per the v10 design review §"Issue #5 — Reward gaming" (CMDP) and §"Issue #1 — Episode-count math" (posterior-CI gate), implement:

1. **CMDP feasibility filter** — drop infeasible candidates BEFORE Thompson sampling.
2. **Beta-Bernoulli Thompson sampler** — over the 9-bin L4 threshold action space, with a baseline-warm-start prior.
3. **Posterior-CI gate** — promotion to shadow (P5) requires posterior CI on best arm ≤ 0.10 wide (not just episode count ≥ 200).
4. **Reproducibility manifest** — every train run snapshots seed + DB SHA + hyperparams + per-arm posterior + IPS estimate per candidate.

Trainer outputs are PROPOSALS only — never written back to gov config in v10.1 (writeback is v10.3, gated by separate ADR-18 amendment).

### Deliverables

1. **`rl/constraints.py`** — CMDP feasibility filter:

   - `class ConstraintBundle`:
     ```python
     @dataclass
     class ConstraintBundle:
         fr_og_7_floor: int = 0           # max violations (hard zero)
         hitl_agreement_floor: float      # baseline - 0.02
         alignment_pass_rate_floor: float # baseline pass rate
     ```
   - `is_feasible(candidate: Candidate, bundle: ConstraintBundle, validation_report: ValidationReport) -> bool`
     - Returns True iff ALL three constraints satisfied.
     - Reads stage-1 (golden) and stage-2 (IPS) outputs from validation report; does NOT re-run stages.
     - Constraint violations are NOT encoded as reward penalties anywhere — they REJECT the candidate from the action set.

   - `feasible_action_set(candidates: list[Candidate], bundle: ConstraintBundle, validate_fn: Callable) -> list[Candidate]`
     - Map every candidate through `rl.validate.validate` (P3) at least to stage 2 (cheap).
     - Return only feasible candidates. Empty list is a valid output → trainer reports "no feasible candidate, retain baseline".

2. **`rl/bandit.py`** — Beta-Bernoulli Thompson sampler over the 9-bin L4 threshold action space:

   - **Action space**: L4 threshold ∈ {0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90} (9 bins).
   - **Prior**: per-arm `Beta(α₀, β₀)` with `α₀ + β₀ = 20` (moderately informative). Mean centered on the production-baseline arm: that arm gets `Beta(14, 6)` (mean 0.70 = optimistic prior on baseline); other arms get `Beta(10, 10)` (uniform prior, no baseline assumption).
   - `update(arm: int, reward: int)` — increments α or β.
   - `sample(rng: np.random.Generator) -> int` — draws one sample from each arm's posterior, returns argmax.
   - `posterior_ci_width(arm: int, level: float = 0.95) -> float` — width of the 95 % credible interval for the named arm.
   - `best_arm_posterior_ci() -> float` — CI width of the arm with highest posterior mean.
   - **Promotion gate**: `is_ready_for_shadow() -> bool` — True iff `best_arm_posterior_ci() ≤ 0.10` AND total episodes ≥ 200.

3. **`rl/manifest.py`** — reproducibility manifest:

   - `write_manifest(path: Path, *, seed: int, db_sha: str, hyperparams: dict, posterior: dict, candidates: list, ips_per_candidate: dict[str, float]) -> None`
   - `db_sha` = `sha256(rl_episodes.db at retrain time)`.
   - Manifest is JSON; trainer writes one per run.

4. **`rl/cli/train.py`** — CLI:
   ```
   python -m rl.cli.train \
     --episodes-db rl_episodes.db \
     --baseline-thresholds path/to/production.json \
     --proposals-out rl_proposals/<UTC>Z.json \
     --manifest-out  rl_proposals/<UTC>Z.manifest.json \
     --seed 42
   ```
   - Loads episodes via `rl.corpus_augment.assemble_training_set`.
   - Builds Thompson sampler with baseline-warm-start prior.
   - Runs 1 sampling + update pass per episode (offline replay; not online).
   - Computes `feasible_action_set(...)` over the 9 binned candidates.
   - Writes proposals (top-3 feasible by posterior mean) + manifest.
   - **Exit code 0** if a feasible candidate other than baseline has higher posterior mean AND posterior CI ≤ 0.10. **Exit code 2** if no candidate beats baseline (= retain baseline). **Exit code 1** on any error.

5. **Tests** — `tests/test_rl_bandit.py`:
   - `test_baseline_warm_start_prior` — initial best arm is the baseline arm (production threshold).
   - `test_update_concentrates_posterior` — feeding 200 successes on one arm shrinks its CI below 0.10.
   - `test_promotion_gate_requires_both_n_and_ci` — n=199 → False even if CI ≤ 0.10; n=200 + CI=0.15 → False; n=200 + CI=0.10 → True.
   - `test_thompson_does_not_sample_outside_action_space` — every draw ∈ 0..8.
   - `test_deterministic_with_seed` — same seed → same draws.

6. **Tests** — `tests/test_rl_constraints.py`:
   - `test_fr_og_7_violation_is_infeasible` — candidate with golden-replay FR-OG-7 fail → infeasible.
   - `test_hitl_floor_violation_is_infeasible` — IPS estimate of HITL agreement < baseline − 0.02 → infeasible.
   - `test_alignment_pass_floor_violation_is_infeasible` — alignment-eval pass < baseline → infeasible.
   - `test_all_constraints_pass` — well-behaved candidate → feasible.
   - `test_empty_feasible_set_returns_empty` — when no candidate is feasible, output is `[]`, no exception.

7. **Tests** — `tests/test_rl_manifest.py`:
   - `test_manifest_round_trip` — write + read returns same dict.
   - `test_manifest_db_sha_changes_with_db` — modifying `rl_episodes.db` between writes produces different SHA.

### Trainer-only invariant

P4 changes NO governance behaviour. Trainer outputs proposals; nothing reads them in production. Sanity check post-merge:

- `cli_dispatch_ms` p95 unchanged vs P3.
- All v1.7–v2.0 + v10 P1–P3 tests green.

### LOC budget

P4 net add ≤ 700 lines (highest cap of any v10 phase because the math is concentrated here). If draft exceeds, move manifest to a P4-followup.

## DOD

- [ ] `rl/{bandit,constraints,manifest}.py` + `rl/cli/train.py` created
- [ ] `tests/test_rl_{bandit,constraints,manifest}.py` created
- [ ] Promotion gate requires BOTH n ≥ 200 AND posterior CI ≤ 0.10; tests cover both
- [ ] CMDP filter is the gate, NOT a reward penalty; test asserts no penalty term in `rl.bandit`
- [ ] Trainer is pure numpy / scipy / sqlite3; ZERO `subprocess` / `claude` / `anthropic` imports
- [ ] Sample manifest produced from a real `rl_episodes.db` snapshot; attach to PR
- [ ] LOC budget ≤ 700 net add
- [ ] All v1.7–v2.0 + v10 P1–P3 tests green
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `rl:`

Report back when PR is open with: PR URL, diff stat, file list, sample manifest path, sample proposals JSON, CLI exit code on a known-stable v2.0 baseline (sanity: must be exit 2 = retain baseline if no real lift detected).
