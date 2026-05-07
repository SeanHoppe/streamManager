# v10 RL companion — design review (best-practices pass)

**Status**: design review, not formal design. Performed 2026-05-07
against the v10 RL design seed at commit `4be19ad` (branch
`claude/v10-rl-design-seed`) — re-promoted here against the existing
v1.0–v1.9 infrastructure on `main` at `a7d0666`.

**Inputs**:
- `docs/v10-rl-companion-discussion.md` — discussion artefact (raw).
- v10 RL design seed at `4be19ad:docs/v10-rl-design-seed.md` —
  D1–D7 resolved, 5 issues unresolved.
- ADR-5 (latency budget), ADR-17 (soak tiers), ADR-18 (MVP surface
  freeze, on `7c4a30f`), `src/stream_manager/governance.py`,
  `src/stream_manager/cli_governance.py`,
  `src/stream_manager/learn_mode.py`,
  `src/stream_manager/model_router.py`,
  `tools/soak_driver.py`, `tools/alignment_eval.py`.

**Successor**: formal design doc (numbered ADR or
`docs/v10-rl-design.md`) authored under v10 P0 — see phase prompts in
`docs/prompts/v10-orchestration/`.

**Audience**: review at the v10.0 trigger fire (post-v2.0 ship). Rip
this doc once the formal design lands.

---

## Scope of this review

The seed resolves the seven open questions D1–D7 cleanly but leaves
five open issues for the formal design doc:

1. **Episode-count math** — 200-episode promotion gate sized for
   single-scalar L4 bandit; rises to 500–1000 if action scope expands.
2. **Data-source bias** — soaks are 100 % ALLOW; bandit overfits to
   "always ALLOW = max reward" in ≤ 50 episodes.
3. **Validation strategy** — needs four channels (cassette replay,
   shadow soak, alignment-eval golden, adversarial synthetic).
4. **Stop conditions** — concrete v10 ship criteria not yet codified.
5. **Reward gaming** — FR-OG-7 hard constraint settled, but
   HITL-agreement floor + alignment-eval pass-rate floor not yet
   constraint-encoded.

This review converts those five open issues into concrete design
treatments grounded in standard RL best-practice and the existing
streamManager surfaces. Each issue maps to one or more phase prompts
under `docs/prompts/v10-orchestration/`.

---

## Best-practice principles applied

These principles drive the design treatments below. Each is a
mainstream RL practice; the v10 application notes show how it lands
against streamManager's existing seams.

### P1 — Constrained MDP, not scalar reward

**Principle**: when safety constraints exist (FR-OG-7, HITL-agreement,
alignment-eval), formulate as a constrained Markov decision process
(CMDP) with hard constraints, not a single scalar reward with penalty
terms. Penalty-term encoding is gameable; constraint violation rejects
the action.

**v10 application**: seed D5 already does this for FR-OG-7
(constraint-violating episodes are rejected from the training set, not
penalised). Extend the same treatment to two more constraints
(issue #5):

| Constraint | Floor | Source signal |
|---|---|---|
| FR-OG-7 violations | 0 (hard) | `tools/alignment_eval.py --ci-gate` |
| HITL agreement | ≥ baseline − 2 % | `hitl_overrides` table |
| Alignment-eval pass | ≥ baseline pass rate | golden-row replay |

A candidate threshold vector that violates ANY constraint is dropped
from the proposed-action set BEFORE Thompson sampling, not after.

### P2 — Pessimistic offline RL, given small batch

**Principle**: with sample budget << 1000, off-policy offline methods
(CQL, BCQ, IPS-corrected contextual bandit) outperform vanilla online
methods because they are conservative outside the data support. Tier 3
soak yields ~60 events/cycle; cumulative budget after 3–4 cycles is
~200, which is why the seed sets the L4-only gate at 200.

**v10 application**: the trainer in v10.1 must be off-policy. Episode
log captures the *production* policy's action (current threshold) and
its propensity (always 1.0 in v10.0 — deterministic policy) so that
later off-policy correction (IPS / doubly robust) is well-defined when
exploration starts.

### P3 — Class-imbalance handling, not just weighting

**Principle**: when class distribution is heavily skewed (100 % ALLOW
in current soaks), reward-model learning collapses. Standard mitigations:
synthetic minority oversampling (SMOTE-style), curriculum / staged
exposure, reward re-weighting *after* support is established.

**v10 application** (issue #2): synthetic BLOCK / INTERVENE / AMBIGUOUS
injection from the cassette + P1a probe + caveman-review findings
corpus. Inject *into the training set*, not only the validation set —
the seed's note is correct on this point. See phase-2.

### P4 — Off-policy evaluation (OPE) before shadow

**Principle**: shadow A/B is real but expensive (one extra Tier 3 soak
per candidate). OPE methods (importance sampling, doubly-robust
estimators) let you screen *many* candidate policies on logged data
before committing to a shadow soak. This is the standard preflight
filter in production RL.

**v10 application** (issue #3): the four validation channels from the
seed (cassette / shadow / alignment-golden / adversarial) become a
*pipeline*, not a parallel array. Cheap channels filter candidates
before expensive channels see them. See phase-3.

| Stage | Channel | Cost | Reject criterion |
|---|---|---|---|
| 1 | Alignment-eval golden replay | seconds | any FR-OG-7 row regresses |
| 2 | IPS estimate over `rl_episodes.db` | seconds | reward < baseline + δ |
| 3 | Cassette replay (Tier 1) | minutes | reward < baseline + δ |
| 4 | Adversarial synthetic | minutes | reward < baseline + δ on adversarial subset |
| 5 | Shadow Tier 3 soak | ~32 min | reward < baseline + δ OR any constraint floor breached |

Stages 1–4 reject ≥ 90 % of bad candidates without running stage 5.
Stage 5 promotion gate is unchanged from the seed (N consecutive
shadow soaks).

### P5 — Reproducibility primitives

**Principle**: every published RL result requires a recipe that
reproduces it: deterministic seed, training-set snapshot,
hyperparameter manifest, model card.

**v10 application**: each `rl_train.py` run writes a manifest
(`rl_proposals/<UTC>Z.manifest.json`) capturing seed,
`rl_episodes.db` snapshot SHA, hyperparameters, candidate set, IPS
estimate per candidate. Shadow runs reference the manifest by SHA so
results are traceable end-to-end.

### P6 — Concept-drift monitoring

**Principle**: if the state distribution shifts (model upgrade, lever
flip, prompt-corpus change), past episodes become off-policy in a way
the trainer cannot correct. Standard monitor: KL divergence on the
state-feature distribution between consecutive cycles.

**v10 application**: emit a `state_kl_alert` envelope when the per-cycle
state distribution drifts > τ from the rolling baseline. v2.0 boundary
already triggers this by construction (the seed's D3 trigger choice
acknowledges this). Post-v2.0 the monitor protects against silent
distribution shift, e.g. a future model upgrade that re-bands
confidence values.

---

## Treatment of the five open issues

### Issue #1 — Episode-count math (best-practice: power analysis)

**Current seed disposition**: 200-episode gate for L4-only single
scalar action; 500–1000 if scope expands.

**Refinement**: replace the bare integer with an explicit *power
analysis*. For a Beta-Bernoulli Thompson sampler over a binned action
space (k bins), the posterior 95 % credible-interval width on the best
arm's reward shrinks below δ at:

```
n ≥ k · ceil( p̂(1-p̂) · (1.96/δ)^2 )
```

For L4 (k = 9 bins on [0.5, 0.95] step 0.05), δ = 0.05, p̂ ≈ 0.5
worst case → n ≥ 9 · 384 = 3456 *if* exploration is uniform.
Thompson sampling concentrates exploration on near-optimal arms, which
empirically reduces this by ~5×, putting the realistic gate at
~200–700 episodes.

**Decision**: keep the seed's 200-gate as a *minimum*; gate promotion
to v10.2 shadow on a separate criterion: posterior credible interval
on the best arm < 0.10 wide. Computed at retrain time. Phase 4
deliverable.

### Issue #2 — Data-source bias (best-practice: synthetic minority oversampling + reward weighting in two stages)

**Current seed disposition**: deferred to v10.0 design.

**Treatment**:

1. **Synthetic minority injection**. Source list (in priority order):
   - `tools/p1a_haiku_probe.py` BLOCK corpus (fresh-process probe;
     v1.9 P1a authored 27 wrapped + 27 bare destructive prompts).
   - `tests/fixtures/soak_cassette_*.jsonl` BLOCK / INTERVENE /
     AMBIGUOUS rows (cassette envelopes with non-ALLOW recorded
     decisions).
   - `tools/alignment_eval.py` golden rows where action ≠ ALLOW
     (n=32 total; the non-ALLOW subset is the highest-quality labeled
     minority).
   - caveman-review findings JSONL (when available; lower priority,
     unlabeled).

   Injection ratio: synthetic episodes constitute up to 30 % of the
   training set, no more (preserves real-distribution signal). Real
   episodes always weighted ≥ 1× synthetic.

2. **Two-stage reward**. Stage A reward = `1 if HITL_agreement(action)
   else 0`, computed against the *recorded* HITL outcome on real
   episodes and the *labeled* outcome on synthetic. Stage B (post v10.1
   stability) adds latency and budget terms once λ₁/λ₂ calibration is
   known.

3. **Provenance tagging**. Every episode in `rl_episodes.db` carries
   a `source: 'soak' | 'cassette' | 'probe' | 'golden' | 'review'`
   column. Trainer logs class balance per retrain. Deviation > 10 %
   from target ratio fires a warning; > 25 % aborts retrain.

Phase 2 deliverable.

### Issue #3 — Validation strategy (best-practice: 5-stage gauntlet)

**Current seed disposition**: 4 channels listed, used in parallel.

**Treatment**: 5-stage gauntlet (per P4 above), structured as a
pipeline. Each candidate threshold vector must pass stage N to reach
stage N+1. Cheap stages reject early. Phase 3 deliverable.

### Issue #4 — Stop conditions (best-practice: ship-gate-style criteria with pre-registered thresholds)

**Current seed disposition**: 4 criteria listed (consecutive shadow
wins; zero FR-OG-7; HITL floor; parameter drift bound).

**Refinement**:

| Criterion | Threshold | Measurement window |
|---|---|---|
| Shadow reward improvement | reward(candidate) ≥ reward(baseline) + 0.02 | 3 consecutive Tier 3 shadows |
| FR-OG-7 violations | 0 across full alignment-golden + adversarial sets | every shadow |
| HITL agreement | ≥ baseline − 2 % absolute | every shadow |
| Alignment-eval pass rate | ≥ baseline pass rate | every shadow |
| Posterior CI width on best arm | ≤ 0.10 | computed at retrain |
| Parameter drift between retrains | |Δθ| ≤ 0.02 | 3 consecutive retrains |

Pre-registered thresholds matter — pick once, before data collection,
and write into the formal design doc. Phase 5 deliverable.

### Issue #5 — Reward gaming (best-practice: CMDP with multiple hard constraints)

**Current seed disposition**: FR-OG-7 = hard constraint via episode
rejection. HITL floor + alignment-eval pass not yet hard.

**Refinement**: per P1 above, all three become hard constraints. A
candidate threshold vector violating ANY is dropped from the
proposed-action set *before* Thompson sampling. No penalty-term
encoding. The trainer outputs only feasible candidates. Phase 4
deliverable.

---

## Mapping to phase prompts

| Phase | Open issue(s) | File |
|---|---|---|
| P0 — formal design | meta (promotes seed → ADR-numbered design) | `docs/prompts/v10-orchestration/phase-0-formal-design.md` |
| P1 — episode logging | (foundation; touches all issues) | `docs/prompts/v10-orchestration/phase-1-episode-logging.md` |
| P2 — corpus augmentation | issue #2 | `docs/prompts/v10-orchestration/phase-2-corpus-augmentation.md` |
| P3 — OPE harness | issue #3 | `docs/prompts/v10-orchestration/phase-3-ope-harness.md` |
| P4 — bandit trainer | issues #1, #5 | `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md` |
| P5 — shadow + stop | issue #4 | `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md` |

Each phase prompt is self-contained per the v1.x format invariant
(copy-pasteable verbatim into a fresh Claude Code session via the
matching action prompt).

---

## Key constraints carried into formal design

These are non-negotiable inputs to the formal design doc; the phase
prompts already reflect them.

1. **Surface-freeze (ADR-18)** applies to v10. RL writer NEVER
   modifies governance.py, cli_governance.py, model_router.py,
   cli_pool.py, or any FROZEN symbol. RL reads gov state, writes only
   to `rl_episodes.db` and `rl_proposals/*.json`. Writeback authority
   (v10.3) lives behind a future explicit ADR-18 amendment.
2. **No self-monitor** (memory: `feedback_no_self_monitor.md`). RL
   trainer NEVER ingests SM's own JSONL or bus envelopes describing
   SM's own decisions about RL — same rule that applies to Learn Mode
   (v1.9 P3 source-label guard).
3. **Single-writer per DB** (sync-comms v1.0 design memory). Dedicated
   writer process for `rl_episodes.db`, separate from sync-comms
   writer. WAL mode mandatory.
4. **No tokens for the training loop** (seed's deterministic-Python
   thesis). Trainer is numpy/scipy only. LLM tokens used only for
   inference, which already happens in production.
5. **Cycle-LOC budget (ADR-18 Rule 3)** applies. v10.0 logging phase
   target ≤ 500 net add. v10.1 trainer ≤ 500 net add. Phase prompts
   include LOC budget per phase.
6. **Falsify-before-extend (ADR-18 Rule 2)** applies. If v10.1 trainer
   does not converge across N consecutive runs, RL track enters
   DORMANT-2 → DORMANT-3 → rip rather than expanding action scope to
   compensate.

---

## Open after this review

The five seed issues are now addressed by phase prompts. Remaining
open items belong in the formal design doc itself (phase 0) and are
NOT pre-decided here:

- Concrete state-feature vector schema (which numerical fields, with
  what discretisation).
- Concrete reward-component formula post-calibration (λ₁, λ₂ once
  v10.0 logs supply the variance estimate).
- Choice of Thompson posterior family (Beta-Bernoulli over binned
  arms vs. Gaussian-process over continuous threshold).
- Trainer cadence calendar (specific weekday/hour for the weekly slot
  in the steady-state cadence).
- v10.3 writeback authority's ADR-18 amendment text.

These belong inside the formal design (phase 0 deliverable) once
v10.0 logging has supplied at least 200 episodes of real data.

---

## Recommendation

1. Ship v2.0 (per seed D3).
2. Open v10 phase 0 (formal design) as the first PR after v2.0 tag.
3. Land phases 1–5 strictly in order. Do NOT parallelise — each phase
   gates the next.
4. Treat this review as ripable once the formal design lands. Keep
   the phase prompts; rip this review.
