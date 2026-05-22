# v10 — RL companion track (formal design)

**Status**: Accepted (v10 P0). Date: 2026-05-07.
**Supersedes**: `docs/v10-rl-design-seed.md` (D1–D7) + `docs/v10-rl-design-review.md` (5-issue treatments).
**Predecessors (read-only references)**: `docs/v10-rl-companion-discussion.md`, `docs/adr/ADR-18-mvp-surface-freeze.md`, `docs/adr/ADR-5-latency-budget.md`, `docs/adr/ADR-17-soak-tiers.md`.

---

## 1. Goal

Close the streamManager governance loop with a deterministic-Python contextual bandit over the L4 confidence threshold, off-policy trained on logged Tier 3 + cassette + golden + probe episodes, gated by a 5-stage validation gauntlet, with three hard constraints (FR-OG-7, HITL-agreement floor, alignment-eval pass-rate floor).

## 2. Non-goals

- Parameterising more than the L4 threshold in v10.1.
- LLM tokens in the training loop (trainer is pure numpy / scipy / sqlite3).
- Modifying any FROZEN gov surface (per ADR-18 §"Initial classification").
- Auto-writeback before v10.3. Trainer outputs proposals only; production threshold is unchanged by trainer runs through v10.2.

## 3. State-feature schema

Concrete numerical vector emitted by `rl.state_features.extract(state) -> dict[str, float | int]`:

| Field | Type | Notes |
|---|---|---|
| `latency_ms_last5_p95` | float | Rolling p95 of `cli_pool_send_ms` over last 5 dispatches |
| `content_length` | int | Character count of the user-message under governance |
| `regex_destructive_match` | int (0/1) | v10-owned destructive-content regex hit |
| `regex_alignment_match` | int (0/1) | Alignment-trigger regex hit |
| `time_of_day_bucket` | int (0–23) | UTC hour bucket |
| `session_history_action_share` | list[float] (length 5) | Rolling share of last 5 actions over ALLOW / SUGGEST / INTERVENE / BLOCK / AMBIGUOUS |
| `routing_band` | int (1–4) | L1/L2/L3/L4 from `RoutingDecision` |
| `trigger_factor` | int | Output of `classify_trigger_factor` |
| `learn_mode_bias_hint` | float | Current `bias_consult` advisory output (advisory only) |

Function is pure: deterministic, no I/O, no clock reads. Caller supplies `now_utc`. Regex helpers are declared locally in `rl/state_features.py` (no import of FROZEN destructive-pattern symbols).

## 4. Action space (v10.1)

L4 confidence threshold ∈ {0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90}. **9 bins** (closed interval [0.50, 0.90], step 0.05). 0.95 dropped as a degenerate near-noop arm (every realistic L4 verdict surpasses it).

Other parameters (L2/L3 thresholds, verdict-fallback fire conditions, `bias_consult` weights, trigger-pattern weights) are LOGGED but NOT VARIED in v10.1. They become candidate action dimensions only after L4 closes the loop.

## 5. Reward formula

```
reward_stage_A = 1 if HITL_agreement(action) else 0
reward_stage_B = reward_stage_A − λ₁ · z(latency_p95) − λ₂ · budget_violation_count
```

- **Stage A** (v10.1 launch): pure HITL-agreement reward. λ₁ = λ₂ = 0. Use until ≥ 1 retrain has produced a stable per-arm posterior (ε-tilt arms within `α₀ + β₀ = 20` invariant).
- **Stage B**: activates only after λ₁ / λ₂ calibration completes per phase 4 §"reward calibration". Calibration target: λ₁ such that latency-term magnitude is 10–20 % of HITL-term magnitude observed in v10.0 logs; λ₂ when budget violations become non-rare.

Hard constraints (§7) are NEVER encoded as reward penalties.

## 6. Hard constraints (CMDP)

A candidate threshold vector is INFEASIBLE and dropped from the action set BEFORE Thompson sampling if ANY:

1. **FR-OG-7 violation count > 0** on alignment-golden replay (every shadow-evaluated candidate; zero-tolerance).
2. **HITL agreement < baseline − 2 %** absolute on logged subset (computed via IPS over `rl_episodes.db`).
3. **Alignment-eval pass rate < baseline pass rate** (golden replay, n=32).

Constraint violations REJECT the candidate; they do not modify the reward. Constraint-violating EPISODES remain in the log for observability — only constraint-violating CANDIDATES are dropped from the action set.

## 7. Posterior family

Beta-Bernoulli per arm (binned discrete action space). Per-arm prior `Beta(α₀, β₀)` with `α₀ + β₀ = 20` invariant (moderately informative). Mild ε-tilt around the production-baseline arm per seed D6:

| Arm distance from baseline | Prior | Mean |
|---|---|---|
| 0 (baseline arm) | `Beta(14, 6)` | 0.70 |
| ±1 step | `Beta(11, 9)` | ~0.55 |
| ±2 or more | `Beta(10, 10)` | 0.50 (uniform) |

Posterior updated via Beta-Bernoulli conjugate update: `update(arm, reward)` increments α (reward=1) or β (reward=0). Sampling: Thompson — draw one sample from each arm's posterior, return `argmax`.

**Promotion gate to v10.2 shadow** (§10): `is_ready_for_shadow() == True` iff `best_arm_posterior_ci() ≤ 0.10` AND `total_episodes ≥ 200`.

## 8. Cadence

Per seed D7:

- **Phase 1** (v10.1 trainer not yet stable): on-demand. Human triggers retrain when ≥ 60 new episodes accumulated or when debugging.
- **Phase 2** (after v10.1 trainer converges across ≥ 3 consecutive on-demand runs without manual override): weekly retrain, **pre-registered slot Sunday 02:00 local**. Tied to the ship cycle: proposed thresholds available before each Tier 3 soak.

Off-hours WAL conflict (predecessor issue #7): trivially handled at weekly cadence + dedicated DB writer (D2).

## 9. Phase ledger

| Phase | Scope | Files (touch list) | LOC budget | Predecessor gate |
|---|---|---|---|---|
| P0 | Formal design (this doc) + task plan | `docs/v10-rl-design.md`, `docs/v10-task-plan.md` | docs only | v2.0 ship tag |
| P0a | Seed reconcile (16 doc fixes) | `docs/prompts/v10-orchestration/phase-{0..5}-*.md`, `docs/v10-rl-design-review.md` | docs only | #106 merge |
| P1 | Episode logging | `rl/{__init__.py, schema.sql, state_features.py, episode_logger.py}`, `tests/test_rl_*.py`, ADR-5 append | ≤ 500 net add (excl. tests + schema) | P0 merge |
| P2 | Corpus augmentation | `rl/corpus_augment.py`, `rl/sources/{cassette,probe,golden,review}.py`, tests | ≤ 500 | P1 merge + ≥ 60 live episodes |
| P3 | OPE harness (5-stage gauntlet) | `rl/{ope.py, validate.py}`, `rl/cli/validate.py`, tests | ≤ 600 | P2 merge |
| P4 | Bandit trainer | `rl/{bandit.py, constraints.py, manifest.py}`, `rl/cli/train.py`, tests | ≤ 700 | P3 merge + ≥ 200 live episodes |
| P5 | Shadow + ship criteria | `rl/{shadow.py, stop_conditions.py}`, `rl/cli/{shadow.py, check_criteria.py}`, tests, design append | ≤ 600 | P4 merge + ≥ 1 ready-for-shadow proposal |

Each phase opens its own PR against `main`. P0 + P0a + P1 may bundle into a single PR (this PR) since each unblocks the next mechanically.

## 10. Stop conditions — pre-registered ship criteria

These thresholds are pre-registered. They are NOT relaxed based on observed data (p-hacking guard). If criteria cannot be met after 3 retrains × 3 shadows, the v10 track enters DORMANT-N per ADR-18 Rule 2 and is reviewed for rip in the next ship cycle.

| Criterion | Threshold | Window |
|---|---|---|
| Shadow reward improvement | reward(candidate) ≥ reward(baseline) + 0.02 | 3 consecutive Tier 3 shadows |
| FR-OG-7 violations | 0 | every shadow (full alignment-golden + adversarial) |
| HITL agreement | ≥ baseline − 2 % absolute | every shadow |
| Alignment-eval pass rate | ≥ baseline pass rate | every shadow |
| Posterior CI on best arm | ≤ 0.10 | computed at retrain |
| Parameter drift between retrains | \|Δθ\| ≤ 0.02 | 3 consecutive retrains |

> **Footnote (v2.4 P0, 2026-05-19):** v10.1 deterministic policy makes "Posterior CI on best arm ≤ 0.10" structurally unreachable on non-baseline arms. See ADR-18 §Amendments 2026-05-19 (Amendment D — v10 P5 entry-gate split v10.1-mode vs v10.3-mode; closes #177).

### 10a. P3 cassette p95 + action-dist thresholds — disposition

Per P0a item E1, the P3 prompt introduces two thresholds (cassette p95 ≤ 10 % regress, action-dist ≤ 20 % shift) that are NOT in the pre-registered ship-criteria table above. Disposition: **advisory only** at v10.0–v10.2. They appear in the validation report as observability signals but do NOT gate ship promotion. Promotion remains controlled by the 6 criteria in the table above. Re-evaluation in v10.3 if cassette regression empirically correlates with shadow regression.

### 10c. P3 stage-1 (golden) and stage-2 (IPS empty-DB) — ADVISORY pending L4-fallback wiring

`BRIDGE_L4_FALLBACK_CONFIDENCE` is documented as the L4 fallback threshold but is not wired at any pre-CLI callsite in `src/` or `tools/` as of v10 P3 (parallel finding to P3 deviation #2 for stage 3). Consequences for the P3 validation gauntlet:

- **Stage 1 (alignment-golden replay).** The implementation in `rl/validate.py:_verdict_under_threshold` is a bin-distance heuristic (sonnet-floor + Δ > 0.05 ⇒ ALLOW), NOT a `src/stream_manager/model_router.route` replay against the candidate threshold. Borderline non-bin-edge FR-OG-7 regressions will not trip it. Per ADR-18 Rule 1 (surface freeze), wiring `BRIDGE_L4_FALLBACK_CONFIDENCE` is out of scope for P3. Stage 1 is therefore tagged **ADVISORY** in the rendered report (`metrics["advisory"] = True`) and does not gate ship promotion in §10. Promotion is gated on the FR-OG-7 row in the table above ("every shadow"), which is satisfied by the production alignment-eval surface, not by P3 stage 1.
- **Stage 2 (IPS over `rl_episodes.db`).** When the DB is empty (sanity validation, fresh clone, pre-data v10.0 ring), the stage skips with `passed=True` to honor the DOD requirement that "production thresholds vs themselves PASSes all 4 stages". The skip is annotated `metrics["advisory_skipped"] = True` and rendered as `PASS (ADVISORY)`. Once `rl_episodes.db` has ≥ 30 live/soak episodes (per §6 sample budget), the advisory tag drops automatically and the stage gates as designed.

Promotion to non-advisory for stage 1 requires:

1. Wiring `BRIDGE_L4_FALLBACK_CONFIDENCE` (or an equivalent threshold parameter) at the `model_router.route` callsite.
2. Replacing `_verdict_under_threshold` with a `route()`-based replay that re-evaluates each golden row's recorded confidence against the candidate threshold.
3. ADR-18 reclassification of the relevant `model_router` / `cli_governance` surface from FROZEN to EVOLVING for the duration of the wiring change.

Tracked in [#124](https://github.com/SeanHoppe/streamManager/issues/124). The sibling P3 DR-estimator follow-up (deviation #1) is tracked in [#125](https://github.com/SeanHoppe/streamManager/issues/125).

### 10d. v10 ship criteria — pre-registered (v10 P5 codification)

Per v10 P5 deliverable 7 (Path-D landing at v2.8 P1), the six ship criteria below are codified as CODE CONSTANTS in `rl/stop_conditions.py` (`SHADOW_REWARD_DELTA`, `SHADOW_REWARD_WINDOW`, `FR_OG_7_VIOLATION_FLOOR`, `HITL_AGREEMENT_DELTA`, `POSTERIOR_CI_CAP`, `PARAMETER_DRIFT_CAP`, `PARAMETER_DRIFT_WINDOW`). The values are read-only at evaluation time and not overridable via environment variables (`tests/test_rl_stop_conditions.py::test_thresholds_are_constants_not_env_overrides` asserts this).

| Criterion | Threshold | Window |
|---|---|---|
| Shadow reward improvement | reward(candidate) ≥ reward(baseline) + 0.02 | 3 consecutive Tier 3 shadows |
| FR-OG-7 violations | 0 | every shadow (full alignment-golden + adversarial) |
| HITL agreement | ≥ baseline − 2 % absolute | every shadow |
| Alignment-eval pass rate | ≥ baseline pass rate | every shadow |
| Posterior CI on best arm | ≤ 0.10 | computed at retrain |
| Parameter drift between retrains | \|Δθ\| ≤ 0.02 | 3 consecutive retrains |

These thresholds are pre-registered. They are NOT relaxed based on observed data. If criteria cannot be met after 3 retrains × 3 shadows, the v10 track enters DORMANT-N per ADR-18 Rule 2 and is reviewed for rip in the next ship cycle.

`rl.cli.check_criteria` is the evaluator surface: exit code 0 = all criteria PASS (signal that v10.3 writeback can be opened — human-gated review per ADR-18, NOT auto-promotion); exit code 1 = at least one FAIL.

Under Amendment D v10.1-mode (the active mode through v10.3 writeback unlock), criterion 5 ("Posterior CI on best arm ≤ 0.10") is structurally unreachable on non-baseline arms; the v10.1-mode entry gate substitutes baseline-arm `_total >= 200 AND posterior_ci_width(baseline_arm) <= 0.10` for the original best-arm formulation. The criteria table itself is unchanged; the gate disambiguation lives in ADR-18 §Amendments 2026-05-19.

> **Footnote (v2.8 P1, 2026-05-22) — HITL-agreement criterion is a cand↔prod proxy in v10.1-mode.** Row 3 of the table above is labelled "HITL agreement". The v10 P5 evaluator (`rl/stop_conditions.py`) surfaces this criterion under the name `cand_prod_agreement` because `shadow_episodes.agree` records candidate-verdict vs production-verdict equality, NOT a HITL operator label. The pre-registered floor (1 − `HITL_AGREEMENT_DELTA` = 0.98) is unchanged; only the metric source differs from the design seed. True HITL-agreement wiring requires an IPS lookup against `rl_episodes.db` + `hitl_overrides` and lands with v10.3 writeback (a new criterion row, not a re-purposing of this row). Until then, the proxy is the binding criterion and is rendered as `cand_prod_agreement` in `rl.cli.check_criteria` reports.

### 10b. Shadow recording strategy — disposition

Per P0a item G1, P5's `--shadow-recorder` flag on `tools/soak_driver.py` requires that surface to be EVOLVING (not FROZEN) under ADR-18. Current ADR-18 classification places `tools/soak_driver.py` in the EVOLVING bucket (the v2.0 P1 `worker_recycle_every_n` kwarg pass-through landed without amendment). Therefore:

- **Primary strategy** (default): in-process subscriber via `tools/soak_driver.py --shadow-recorder rl_shadow.db --shadow-proposal <path>`. Recorder runs in-process with the bus.
- **Fallback strategy** (if soak_driver freezes between P3 and P5): sidecar JSONL-tail of soak's bus log file, post-run write to `rl_shadow.db`. NOT live but preserves the data; latency budget moot.

P5 implementation MUST re-verify the soak_driver classification at start of phase and pick the matching strategy. If the classification has flipped, P5 prompt is re-minted.

## 11. v10.3 writeback — ADR-18 amendment text (DRAFT, NOT ENACTED)

The amendment below lands ONLY when v10.3 is greenlit by §10's ship criteria PASS for ≥ 1 cycle. P0 records the draft so the v10.3 phase prompt can lift it verbatim.

> **ADR-18 Amendment §"v10.3 RL writeback authority"** (drafted v10 P0; not enacted).
>
> The following symbols are reclassified from FROZEN to EVOLVING for the purpose of v10.3 RL writeback:
>
> - `governance.GovernanceConfig.l4_confidence_threshold` (read site → write site).
>
> All other gov symbols remain FROZEN. The trainer writes a proposal manifest (`rl_proposals/<UTC>Z.json`); a separate `rl/cli/writeback.py` CLI applies the manifest to the live config. Writeback is gated on:
>
> 1. `rl.cli.check_criteria` exit code 0 (all 6 ship criteria PASS).
> 2. Human approval (HITL gate; no auto-promotion).
> 3. Post-writeback Tier 3 soak validates against the same 6 criteria.
>
> Rollback path: writeback CLI snapshots the prior threshold; `rl/cli/writeback.py --rollback` restores it. Rollback is automatic on post-writeback Tier 3 criteria failure.

This text is DRAFT. v10.3 phase prompt will refine after ≥ 200 episodes of v10.0–v10.2 observation.

## 12. Reproducibility

Per design review §P5, every train run writes a manifest:

- `rl_proposals/<UTC>Z.json` — top-3 feasible candidates, posterior summary, IPS per candidate.
- `rl_proposals/<UTC>Z.manifest.json` — seed, `rl_episodes.db` SHA, hyperparams, full per-arm posterior, candidate set.

Shadow runs reference manifests by SHA. End-to-end traceability: episode → manifest → proposal → shadow → criteria report.

---

## Open after this design

Items deferred to later phases (NOT pre-decided here):

- λ₁ / λ₂ calibration values (deferred to P4 reward calibration sub-phase, after v10.0 logs supply variance estimate).
- Concrete state-feature `time_of_day_bucket` discretisation if rolling p95 distribution shifts (re-evaluate at v10.1 baseline).
- v10.3 amendment refinement (above; draft only).

---

## Cross-references

- Seed: `docs/v10-rl-design-seed.md` (D1–D7).
- Review: `docs/v10-rl-design-review.md` (5-issue treatments + best-practice principles P1–P6).
- Surface freeze: `docs/adr/ADR-18-mvp-surface-freeze.md`.
- Latency budget: `docs/adr/ADR-5-latency-budget.md` (§"v10 logging overhead" added by P1; §"v10 shadow overhead" added by P5).
- Soak tiers: `docs/adr/ADR-17-soak-tiers.md`.
- Phase prompts: `docs/prompts/v10-orchestration/phase-{0,0a,1,2,3,4,5}-*.md`.
