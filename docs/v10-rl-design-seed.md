# v10 — RL companion track (design seed)

**Status**: design seed, not yet a formal design doc. Captures decisions made 2026-05-07 against the open questions in [v10-rl-companion-discussion.md](v10-rl-companion-discussion.md).

**Predecessor**: [v10-rl-companion-discussion.md](v10-rl-companion-discussion.md) — discussion artefact captured during v1.9 ship-gate finalize, contains framing, RL-primitives mapping, phased proposal v10.0–v10.3, and risk register.

**Successor**: a formal design doc (numbered ADR or `docs/v10-rl-design.md`) once v2.0 ships and v10.0 logging trigger fires.

---

## Decisions resolved

Resolutions to the seven open questions in §"Open questions to decide before v10.0 starts" of the predecessor doc.

### D1 — Repo layout: subdir `rl/` in main repo

v10 lives as `rl/` subdirectory under existing `streamManager` repo. Not a separate repo.

**Why**: cadence-split (off-hours batch vs ship cadence) is handled by scheduling, not repo boundary. Traceability between gov code change → RL retrain matters more than `git log` cleanliness. RL trainer needs to import gov internals (state-feature extractors, threshold constants) without dual-clone friction.

**Implication for `git log` noise**: RL commits use `rl:` conventional-commit prefix so gov ship history can be filtered with `git log --invert-grep --grep="^rl:"` when needed.

### D2 — Database: dedicated `rl_episodes.db`

RL episodes live in a separate SQLite file from the gov DB. Cross-DB joins via `ATTACH DATABASE` when needed.

**Why**: gov DB participates in ship-gate; schema migrations there are high-risk. RL writer process must not contend with sync-comms WAL writer (per existing single-writer constraint). Isolation matches the "don't pollute ship-gate" thesis from the predecessor doc's §"Reasons to split."

**Writer model**: dedicated writer process for `rl_episodes.db`, WAL mode enabled, separate from sync-comms writer. Mirrors existing pattern.

### D3 — Trigger: post-v2.0 ship

v10.0 logging starts after v2.0 ships. Not immediately post-v1.9.

**Why**: v2.0 lever is `cli_pool` A/B (per `project_v19_cycle_close` memory). That change shifts the latency feature distribution RL trains on. Logging across the v2.0 boundary produces a bimodal state corpus that partially invalidates the early episodes. Cleaner to start the clock on a stable post-v2.0 distribution.

**Cost accepted**: ~1 cycle (weeks) of lost logging time. Mitigated — Tier 3 soak = 60 events/cycle, the v10.0 → v10.1 promotion gate (≥200 episodes) lands inside 3–4 v2.x cycles.

### D4 — Parameter scope

**Logging scope (v10.0)**: log all four candidate parameters' state in every episode tuple.
1. L2/L3/L4 confidence thresholds (currently hardcoded ~0.70)
2. Verdict-fallback fire conditions (currently boolean)
3. `bias_consult` weights (currently advisory zero-weight)
4. Trigger pattern weights in `classify_trigger_factor`

**Why log all**: cheap (extra DB columns), expensive to backfill. Captures full state regardless of which knob is acted on later.

**Action scope (v10.1)**: trainer acts on the **L4 confidence threshold** first. Other three parameters logged but not varied.

**Why L4 first**:
- Highest leverage — L4 alignment-eval is the structural latency floor (per `project_v11_latency_floor` memory)
- Has a labeled validation set (alignment-eval golden, n=32)
- Single scalar action → bandit converges fast (≤200 episodes realistic)
- Reversible — write proposed value to config, ship-gate catches regression

**Cost accepted**: `bias_consult` is the §v10.3 "close the loop" target. Acting on L4 first means v10.3 still requires a fresh training run for `bias_consult`. Staged risk preferred over coupling unfamiliar trainer to writeback authority in one step.

### D5 — Reward weights: λ₁ = λ₂ = 0 at v10.1 start

Reward formula:
```
reward = HITL_agreement − λ₁·latency_p95 − λ₂·budget_violations
```
Hard constraint (independent of weights): FR-OG-7 violation → episode rejected (does not enter training set), not represented as a weighted penalty term.

Initial weights: **λ₁ = 0, λ₂ = 0**. Pure HITL-agreement reward at v10.1 start.

**Why zero**:
1. HITL-agreement scale is unknown until v10.0 logging completes — cannot pick informative λ values without observed reward variance.
2. Soaks are 100% ALLOW (per `project_v19_cycle_close`); HITL-agreement is near-saturated. A non-zero λ₁ would dominate and degenerate the policy toward "always Haiku fastpath = minimum latency."
3. λ₂ stays 0 until budget violations actually appear in the episode log (currently rare).

**Calibration plan**: after v10.1 baseline lands, set λ₁ such that the latency term magnitude is ≈ 10–20% of the HITL term magnitude observed in v10.0 logs. λ₂ similarly when budget violations become non-rare.

### D6 — Exploration policy: Thompson sampling

Thompson sampling over the action space, not ε-greedy or UCB.

**Why**:
- Sample budget is tight (Tier 3 = 60 events/cycle vs ~200–1000 needed). Sample efficiency dominates.
- Action space is 1-D continuous (L4 threshold ∈ [0.5, 0.95]); Thompson over a Gaussian-process or binned-Beta posterior is ~50 lines of numpy.
- ε-greedy at small n burns episodes on uniform-random actions far from the safe baseline — unsafe in a governance context (cold-start risk, predecessor doc issue #2).
- Thompson naturally warm-starts from a prior centered on the current production threshold; bounded perturbation matches the ε-neighborhood requirement from issue #2.

### D7 — Cadence: on-demand → weekly

**Phase 1 (v10.1 trainer not yet stable)**: on-demand. Human triggers retrain when N new episodes accumulated or when debugging the trainer.

**Phase 2 (after v10.1 trainer converges across ≥N consecutive on-demand runs)**: weekly retrain, tied to the ship cycle. Proposed thresholds available before each Tier 3 soak.

**Why not nightly**: posterior delta per night is negligible at current episode arrival rate (~60/soak, ≤1 soak/day, often 0). Nightly retrain wastes compute on near-stale data.

**Off-hours WAL conflict (predecessor issue #7)**: trivially handled at weekly cadence — pick a slot known to be session-idle (e.g., Sunday 02:00 local). Already mitigated by D2 (dedicated DB + writer).

---

## Decision summary table

| # | Question | Decision |
|---|----------|----------|
| D1 | Repo split | subdir `rl/` in main repo |
| D2 | DB split | dedicated `rl_episodes.db`, separate writer |
| D3 | v10.0 trigger | post-v2.0 ship |
| D4a | Logging scope | all 4 candidate parameters |
| D4b | Action scope (v10.1) | L4 confidence threshold first |
| D5 | Reward weights | λ₁=λ₂=0 at start; FR-OG-7 hard constraint |
| D6 | Exploration | Thompson sampling, baseline-warm-start |
| D7 | Cadence | on-demand → weekly post-stability |

---

## Issues NOT resolved by these 7 decisions

The decisions above cover the §"Open questions" list. Several risks from the predecessor doc remain open and must be addressed before v10.1 is greenlit. Captured here so they are not lost.

1. **Episode count math (predecessor issue #4)** — v10.0 promotion gate of 200 episodes is sufficient for L4-only single-scalar bandit (D4b limits action space). If action scope expands beyond L4, gate must rise to 500–1000.

2. **Data-source bias (predecessor issue #3)** — soaks are 100% ALLOW; bandit on this corpus learns "always ALLOW = max reward" in ≤50 episodes. Mitigation deferred to v10.0 design: synthetic BLOCK/AMBIGUOUS injection from the cassette/probe corpus must augment the training set, not just validation. Alignment-eval golden (n=32) is too small to serve alone as validation.

3. **Validation strategy (predecessor issue #9)** — needs four channels, not three:
   1. Cassette replay (deterministic, frozen distribution)
   2. Shadow-mode soak (real but slow)
   3. Alignment-eval golden (labeled but small)
   4. Adversarial synthetic generated from caveman-review findings corpus (catches reward hacking on novel inputs)

4. **Stop conditions (predecessor issue #10)** — concrete v10 ship criteria needed before v10.3 writeback:
   - ≥N consecutive shadow soaks where reward > baseline + δ
   - Zero FR-OG-7 violations across the shadow corpus
   - HITL-agreement floor maintained
   - Parameter drift < ε across 3 consecutive retrains

5. **Reward gaming (predecessor issue #1)** — D5 sets FR-OG-7 as a hard constraint (episode rejection, not penalty term). HITL-agreement floor and alignment-eval pass-rate floor must be added as additional hard constraints in the formal design doc.

These issues are tracked here so the formal design doc can pick them up directly.

---

## Next actions

1. Ship v2.0 (cli_pool A/B). v10 work is paused until then.
2. After v2.0 ship: open formal v10 design doc (numbered ADR or `docs/v10-rl-design.md`), promoting this seed and resolving the five open issues above.
3. v10.0 logging implementation lands as the first PR on the formal design.

**Branch**: `claude/v10-rl-design-seed` (off `main` at a7d0666).
