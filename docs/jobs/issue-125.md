# #125 — v10.x: restore Ridge-Q DR estimator; un-alias `doubly_robust_estimate` / `cross_validated_dr` from IPS

**Status:** BLOCKED on #131 (ADR-18 freeze-lift cycle not yet minted).
**Bucket:** v10 chain.
**GH:** https://github.com/SeanHoppe/streamManager/issues/125

## Origin

PR #123 deviation #1 (authorized LOC-budget escape hatch) + post-merge ❓ on rendered DR field.
Cross-ref `rl/ope.py:114-145` (alias docstring + impl).

## Problem

P3 prompt §"Deliverables" specified `doubly_robust_estimate` + `cross_validated_dr` with Ridge-Q +
Cholesky solver. Full draft hit 771 LOC, exceeded 600 LOC P3 budget. Per prompt's escape hatch, DR
scoped back to forward-compat IPS aliases (`del q_model`, `del k_folds, seed, alpha`). Public API
preserved but estimators give IPS-equivalent stats only.

Post-review fix in PR #123: alias was rendering alongside IPS in `_stage_2_ips` detail string +
`metrics["dr_target"]` → false-confidence signal that DR independently gating. DR call + render
dropped from stage 2 til DR ships for real.

## Acceptance

1. Ridge-Q model: `q_hat(state, action) = state_features @ θ` with closed-form Cholesky solve
   `θ = (XᵀX + αI)⁻¹ Xᵀr` over training folds. Ridge alpha calibrated against real `rl_episodes.db`
   (≥ 30 live/soak episodes).
2. `doubly_robust_estimate` returns
   `mean = E_target[q_hat(s, π(s))] + IPS_correction(r − q_hat(s, a))`. Self-normalised (Hájek) IPS correction.
3. `cross_validated_dr` 5-fold CV: train Ridge-Q on 4 folds, evaluate DR on held-out, return mean.
   `seed` param wired to `random.Random(seed)` fold-shuffle.
4. Restore DR rendering in `_stage_2_ips`: `dr_target` field + DR-vs-IPS comparison in `detail`. DR
   estimate must be allowed to disagree with IPS (un-aliased).
5. Tests:
   - `test_dr_better_than_ips_on_synthetic` — DR variance ≤ IPS variance on synth episodes with
     non-trivial reward.
   - `test_cv_dr_5_fold_returns_mean_across_folds` — fold-shuffle `seed`-stable; mean = exact fold avg.
   - Drop `test_dr_alias_matches_ips_in_p3` + `test_cv_dr_5_fold_alias_matches_ips`.
6. `rl/ope.py` module docstring (lines 1–18) rewritten — drop SCOPED OUT paragraph.

## Out of scope

- Stochastic propensities (v10.1; `TODO(v10.1)` at `rl/ope.py:106` for ESS denominator switch).
- Stage-1 wiring = #124.

## LOC posture

Est +80 LOC source. Whichever cycle picks must offset against ADR-18 Rule 2. Candidates:
`_verdict_under_threshold` deletion (sibling #124), `where_extra` already dropped, blank-line audit, docstring trim.

## Refs

- PR #123.
- `docs/v10-rl-design.md` §10c.
- Sibling: #124.
- Cycle parent: #131.
