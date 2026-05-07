# v10 — RL companion track (raw discussion capture)

**Status**: discussion artefact, not a plan. Captured 2026-05-07 during v1.9 ship-gate finalize for review at a later date.

**Origin question** (Sean): "If we assign V10 to everything reinforcement learning, does it make sense that we start a new project under V10 for reinforcement learning? We would focus on accumulating more history and increased threshold this means the RL can learn off hours versus real time. I would like to think it can be more python and deterministic versus have a token usage, but I am open to ideas."

**Constraints stated by Sean**:

1. Accumulate more history (longer-running data collection).
2. Increased threshold (training threshold before policy update fires).
3. Off-hours batch RL (async, not real-time).
4. Prefer Python + deterministic over token usage (avoid burning Anthropic API tokens for the training loop).

---

## Holistic read of v1.0→v1.9 vs RL primitives

| RL element | Current state | Gap to RL |
|------------|---------------|-----------|
| Agent | `GovernanceEngine` | ✅ |
| Environment | CLI subprocess + desktop bus | ✅ |
| Episode | release cycle (soak + alignment-eval) | ✅ |
| Reward signal | soak PASS/FAIL, p95 deltas, alignment accuracy, caveman-review findings | mixed/sparse, human-curated |
| Policy | Python code + thresholds | not parameterized — git commits ≠ weight updates |
| Update rule | human reads reports → writes commits | manual, no optimizer |
| Exploration | corpus mix (Tier 3), P1a probes, scenarios library | curated not stochastic |
| Replay buffer | cassette/replay | regression-only, not used for learning |
| Credit assignment | caveman-review attributes finding→fix | manual |

**Pre-RL scaffolding already in place:**

- v1.3 Learn Mode JSONL ingest + Sonnet categorizer = reward-model surrogate over Desktop↔user dialogue. v1.9 P3 expanded sources → larger trajectory pool.
- HITL overrides table → `bias_consult` = preference data feeding policy *advice* (RLHF-shaped, but advisory only per design).
- v1.9 P1 verdict-fallback = explicit fallback policy on confidence threshold → ε-greedy-shaped on `c<0.85`, except deterministic.
- L4 Haiku→Sonnet fastpath (v1.7→v1.8) = action-cost-aware routing, parallels actor distillation.

**Honest read**: cycle cadence (frame hypothesis → Tier 3 → caveman-review → fix → ship → ADR baseline) = textbook **online evaluation loop with human as optimizer**. v1.3 + HITL seam are pre-RL scaffolding without close-the-loop authority.

---

## Proposed v10 framing — sibling track, not rename of v2.x

| Track | Cadence | Scope |
|-------|---------|-------|
| streamManager v2.x | current ship cadence | governance features, latency, lever wiring, ship-gates |
| **v10 RL companion** | off-hours batch | offline policy training over v2.x logs |

**Reasons to split rather than absorb into v2.x:**

- v2.x has hard ship-gate (Tier 3 PASS, FR-OG-7=0). RL needs cold-start exploration that violates both.
- v2.x policy = code+commits. v10 policy = parameter vector. Different artifact, different review process.
- Two-repo or two-subdir model avoids RL training churn polluting governance ship history.

---

## Deterministic-Python feasibility — probably the right call

What kills LLM-token RL: every reward eval = Anthropic call = token cost + variance. Avoidable:

| Component | Token-using approach | Deterministic alternative |
|-----------|---------------------|---------------------------|
| State | LLM summary of context | numerical features: latency, content-length, regex-match flags, time-of-day, session-history stats |
| Action | LLM picks threshold | parametric: threshold vector ∈ ℝⁿ, n ≈ 5–10 |
| Reward | LLM judges outcome | computed: HITL-agreement − λ₁·latency_p95 − λ₂·budget_violations |
| Policy update | gradient through LLM | CMA-ES, Bayesian opt, or contextual bandit (UCB) over threshold vector |

For a low-dim threshold vector (≤ 20 dims), gradient-free optimizers (CMA-ES, BO) converge in 100–1000 episodes. **No LLM tokens needed for the training loop.** LLM only at inference (which already happens today).

---

## Phased proposal — v10.0 → v10.3

### v10.0 — episode logging (zero risk)

- Log episode tuples `(state_features, action_taken, verdict, HITL_override?, latency, FR-OG-7_pass)` to dedicated `rl_episodes.db` (separate from gov DB to keep ship-gate clean).
- No model. No policy update. Pure data collection.
- Runs alongside v2.x soaks; non-invasive.
- **Exit criterion**: ≥ 200 logged episodes before promoting to v10.1.

### v10.1 — off-hours batch trainer

- `tools/rl_train.py` reads `rl_episodes.db`, fits contextual bandit over confidence thresholds, writes `rl_proposed_thresholds.json`.
- Pure numpy/scipy. No tokens.
- Runs as scheduled task (off-hours).
- **Exit criterion**: trainer converges to stable proposal across N consecutive runs.

### v10.2 — shadow A/B harness

- Proposed thresholds run in parallel "ghost" path on next soak; reward measured but no production effect.
- Promote if reward > baseline + δ for N consecutive soaks.
- **Exit criterion**: sustained reward improvement vs production thresholds.

### v10.3 — writeback authority

- Lift `bias_consult` from advisory to threshold-write authority, gated by ship-gate regression check.
- Closes the loop.
- **Exit criterion**: writeback runs for one full ship cycle without ship-gate regression.

---

## Vague issues / risks — flagged for review

1. **Reward gaming.** Any scalar reward is gameable. "Minimize latency" → policy routes everything ALLOW. Must be multi-objective with **hard constraints** (FR-OG-7=0 always; HITL agreement floor; alignment-eval pass rate floor). Constrained-RL framing required.

2. **Cold-start unsafe.** Random policy in a governance context = unacceptable. Must warm-start from current thresholds and bound perturbations to ε-neighborhood until baseline established.

3. **Data-source bias.** Learn Mode JSONL is ALLOW-dominant (current soaks: 100% ALLOW). RL trained on this overfits ALLOW. Need:
   - HITL override episodes weighted higher
   - Synthetic augmentation from cassette/probe corpus
   - Alignment-eval golden rows as labeled validation set

4. **Sample budget.** Threshold-vector RL needs ~100–1000 episodes. Tier 3 soak = 60 events. Need either Tier 4 (multi-hour) or aggregation across many cycles. v10.0 logging starts the clock.

5. **Overlap with v1.3 Learn Mode + bias_consult.** Partial RL scaffolding already exists (reward-model-shaped categorizer, advisory-bias seam). v10 = closing the loop, not greenfield. Could be argued as v2.x phases rather than separate project — but cadence-split argument above favors separate.

6. **Determinism leaks back to LLM at inference.** Even with deterministic training, the inference-time policy STILL routes to Haiku/Sonnet. Token usage doesn't go away — just the training loop.

7. **Off-hours assumption.** "Off-hours" = local machine idle. If RL training takes > 2 hr and a new session starts, conflicts on `rl_episodes.db` writers. Need WAL-mode + separate writer process (similar to current sync-comms design).

8. **What gets parameterized?** Open question. Candidates:
   - L2/L3/L4 confidence thresholds (currently hardcoded ~0.70)
   - Verdict-fallback fire conditions (currently boolean)
   - bias_consult weights (currently advisory zero-weight)
   - Trigger pattern weights in `classify_trigger_factor`
   
   Choosing wrong parameter set = months of wasted training. Worth a v10.0a scoping phase before logging.

9. **Validation strategy.** RL trained on logs → tested how? Options:
   - Replay through cassette (deterministic but limited corpus)
   - Shadow mode in soak (real but slow)
   - Alignment-eval golden rows (labeled but small n=32)
   
   Likely need all three.

10. **Stop conditions.** When does RL training "win"? Need ship-gate-style criteria for v10 itself: convergence stability, reward improvement floor, no FR-OG-7 regression in shadow, etc.

---

## Open questions to decide before v10.0 starts

- **Repo split**: separate repo `streamManager-rl` vs subdir `rl/` in main repo?
- **Database split**: shared SQLite file with `rl_episodes` table vs dedicated file?
- **Trigger**: when does v10.0 logging start — immediately after v1.9 ship, or after a v2.x cycle that explicitly enables it?
- **Parameter scope (issue #8)**: pick 1–2 parameters to start, or instrument all candidates?
- **Reward weights**: λ₁ (latency), λ₂ (budget) — start with what values?
- **Exploration policy**: ε-greedy on baseline thresholds, or Thompson sampling?
- **Cadence**: nightly retrain, weekly retrain, or on-demand?

---

## Recommendation captured during discussion

1. Finalize v1.9 ship first (clean break).
2. Open v10 design doc (this file is the discussion seed; a formal design doc follows).
3. Start with v10.0 logging — zero risk, instrument-only.
4. Defer v10.1+ until ≥ 200 episodes accumulated.

**Status**: Sean selected option (a) — finalize v1.9 ship, capture this discussion to disk for later review.
