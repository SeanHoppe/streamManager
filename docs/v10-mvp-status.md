# v10 — RL companion track: MVP status, requirements, tasks, progress

**Track:** v10 RL companion (parallel to v1.x/v2.x main cycle).
**Design source:** `docs/v10-rl-design.md` (Accepted v10 P0, 2026-05-07).
**Authoring date:** 2026-05-08. **Last refresh:** 2026-05-22 (post v2.8 P1 P5-infra ship, `07ee05c`).
**Peer doc:** `docs/v2.1-p1-scope.md` (v2.1 P1 main-cycle scope).

---

## 1. Goal + non-goals

### Goal (design §1)

Close the streamManager governance loop with a **deterministic-Python contextual bandit** over the L4 confidence threshold. Off-policy trained on logged Tier 3 + cassette + golden + probe episodes, gated by a 5-stage validation gauntlet, with three hard constraints (FR-OG-7, HITL-agreement floor, alignment-eval pass-rate floor).

### Non-goals (design §2)

- Parameterising more than the L4 threshold in v10.1.
- LLM tokens in training loop (trainer = pure `numpy` / `scipy` / `sqlite3`).
- Modifying any FROZEN gov surface (per ADR-18).
- Auto-writeback before v10.3 (trainer outputs proposals only; production threshold unchanged).

---

## 2. Phase ledger — status snapshot

| Phase | Scope | Status | PR | LOC budget | % complete |
|---|---|---|---|---:|---:|
| **P0** | Formal design (`docs/v10-rl-design.md`) + task plan | ✅ SHIPPED | seed PR #106 | docs only | 100 |
| **P0a** | Seed reconcile (16 doc fixes) | ✅ SHIPPED | (bundled w/ P0) | docs only | 100 |
| **P1** | Episode logging (`rl/__init__.py`, `rl/schema.sql`, `rl/state_features.py`, `rl/episode_logger.py`) | ✅ SHIPPED | #108 → bundle-merged via #121 (2026-05-07) | ≤ 500 | 100 |
| **P2** | Corpus augmentation (`rl/corpus_augment.py`, `rl/sources/{cassette,probe,golden,review}.py`) | ✅ SHIPPED | (P2 PR) | ≤ 500 | 100 |
| **P3** | OPE harness 5-stage gauntlet (`rl/ope.py`, `rl/validate.py`, `rl/cli/validate.py`) | ⚠ SHIPPED with 2 known gaps | #123 (`fa4a55f`) | ≤ 600 | 85 |
| **P4** | Bandit trainer (Thompson + CMDP + promotion gate) | ✅ SHIPPED + #111 CLOSED | trainer at v2.3 PR #176 (`cf7d003`); close-out at v2.4 P0 PR #179 (`b35e982`) | ≤ 700 | 100 |
| **P5** | Shadow A/B + ship criteria | [DONE] INFRA SHIPPED (`rl/shadow.py` + `rl/stop_conditions.py` + CLI + soak-driver hook); empirical shadow soak pending (#112) | #214 (`07ee05c`, 2026-05-22) | <= 600 | ~95 (infra complete, 24/24 tests; empirical soak outstanding) |

### Aggregate v10 track completeness

Phase-weighted (P0 + P0a + P1 + P2 + P4 shipped; P3 partial; P5 infra shipped at #214, empirical shadow soak outstanding):

- **Equal-weighted:** (100x5 + 85 + 95) / 7 = **97.1%**
- **Foundation-weighted** (P0/P0a/P1/P2/P3 = foundation at 1x, P4/P5 = training+shadow at 1.5x): foundation 96.7% x 5 = 483.5; P4 100% x 1.5 = 150; P5 95% x 1.5 = 142.5; total 776 / (5 + 1.5x2) = ~97.0%.
- Post-v2.8 P1 baseline sits in the ~95-97% range (was ~80% pre-v2.8 P1). Gain driven by P5 infra ship at #214 (`07ee05c`) on top of P4 ship at v2.3 PR #176 + issue #111 close at v2.4 P0 PR #179.

**v10 MVP completeness: ~95-96% infra (track ships at v10.0; P5 shadow recorder + ship-criteria harness landed at #214 with 24/24 tests; the remaining true MVP blocker is the empirical Tier-3 shadow soak that closes #112 -> #131 -> #124/#125; v10.1+ is post-MVP refinement).**

---

## 3. Per-phase detail

### P0 — Formal design (✅ SHIPPED, 100%)

- `docs/v10-rl-design.md` (192 lines): goal, state-feature schema, action space, reward formula, CMDP, posterior family, cadence, phase ledger, pre-registered ship criteria, v10.3 ADR-18 amendment DRAFT, reproducibility manifest spec.
- Predecessors: `docs/v10-rl-design-seed.md` (D1–D7) + `docs/v10-rl-design-review.md` (5-issue treatments).
- Owner gates: ADR-18 surface freeze observed; no FROZEN gov surface modified.

### P0a — Seed reconcile (✅ SHIPPED, 100%)

- 16 doc fixes across `docs/prompts/v10-orchestration/phase-{0..5}-*.md` + `docs/v10-rl-design-review.md`.
- Bundled into seed PR #106.

### P1 — Episode logging (✅ SHIPPED, 100%)

- `rl/__init__.py`, `rl/schema.sql`, `rl/state_features.py` (134 lines, pure feature extractor), `rl/episode_logger.py` (225 lines, dedicated DB writer).
- Bundle-merged via PR #121 (2026-05-07).
- Closes #108. Unblocks #118 (rl_test_helper schema parity — UNBLOCKED 2026-05-08, ready to land parallel).
- ADR-5 §"v10 logging overhead" appended.
- **Live-subscriber gap:** writer + ingest CLI shipped; `EpisodeLogger` NOT wired into `governance.py`/`message_bus.py` as live bus subscriber. Corpus-fill is two-step (see P4 detail).

### P2 — Corpus augmentation (✅ SHIPPED, 100%)

- `rl/corpus_augment.py` (175), `rl/sources/{cassette,golden,probe,review}.py` (68/71/97/22).
- Synthesizes training episodes from 4 sources without live-only bias.

### P3 — OPE harness (⚠ SHIPPED with 2 known gaps, 85%)

- `rl/ope.py` (177), `rl/validate.py` (363), `rl/cli/validate.py` (60).
- 5-stage validation gauntlet shipped at PR #123 / commit `fa4a55f`.
- **Known gap 1 (stage-1 ADVISORY):** `_verdict_under_threshold` is bin-distance heuristic, NOT `model_router.route` replay. Borderline non-bin-edge FR-OG-7 regressions (Δ ∈ (0, 0.05]) won't trip it. ADR-18 Rule 1 (surface freeze) blocked wiring inside P3. Tracked in **#124**. Promotion gate: ADR-18 reclassification of `model_router.route` callsite (FROZEN → EVOLVING).
- **Known gap 2 (DR alias to IPS):** `doubly_robust_estimate` + `cross_validated_dr` are forward-compat aliases of IPS; Ridge-Q + Cholesky solver scoped out at P3 to fit 600-LOC cap (full draft was 771). Tracked in **#125**. Restoration estimated +80 LOC, requires offset funding.
- **Promotion to non-advisory:** wire `BRIDGE_L4_FALLBACK_CONFIDENCE` + replace heuristic with `route()`-based replay (#124) + restore Ridge-Q (#125).

### P4 — Bandit trainer (✅ SHIPPED + #111 CLOSED, 100%)

- Phase prompt: `docs/prompts/v10-orchestration/phase-4-bandit-trainer.md`.
- Scope: Thompson sampler over 9-bin L4 action space; CMDP safety filter (FR-OG-7 + HITL-floor + alignment-pass-floor); posterior-CI promotion gate (`is_ready_for_shadow()` iff `best_arm_posterior_ci ≤ 0.10` AND `total_episodes ≥ 200`); proposal manifest output (`rl_proposals/<UTC>Z.json`).
- **Trainer implementation shipped at v2.3 PR #176 (`cf7d003`).** Constrained-Thompson bandit + CMDP filter + promotion-gate envelope (`is_ready_for_shadow()`).
- **Issue #111 CLOSED at v2.4 P0 merge (PR #179, `b35e982`).** Closure paired with the v2.4 P0 cycle frame; consolidation cycle absorbed the close-out as docs-side bookkeeping. The trainer code itself landed at v2.3.
- **Q4 hold lifted 2026-05-11 by operator** (historical: see [#111 comment](https://github.com/SeanHoppe/streamManager/issues/111#issuecomment-4427854788)).
- **Corpus growth (200-row gate cleared with margin):**
  - 2026-05-12: total=0, live=0 (`rl_episodes.db` absent — soak-fill pending).
  - 2026-05-17 (post v2.2 ship-gate piggyback soak): total=60, live=60 — 30 % of gate.
  - 2026-05-17 (post v2.3 ship-gate piggyback): total=240, live=240 — gate cleared (+40 over 200).
  - 2026-05-19 (post v2.4 P2 ship-gate Run 4 piggyback): total=360, live=360 — 160-row margin over 200-gate.
  - 2026-05-19 (v2.5 P2 ship-gate BLOCKED at S4 alignment-eval; Run 5 NOT a clean piggyback — episode delta not isolable in the BLOCKED-state soak run; trajectory skips to Run 6).
  - 2026-05-20 (post v2.5.1 P2 ship-gate Run 6 piggyback; PR #190 / `c1e9070`): total=548, live=548 — 348-row margin over 200-gate.
  - 2026-05-20 (post v2.6 P2 ship-gate Run 7 piggyback; PR #198 / `c3a964c`): **total=608, live=608 — 200-row gate cleared with 408-episode margin (608 / 200 = 3.04× gate clearance).** Corpus continues to grow on every subsequent ship-gate piggyback.

  ```bash
  sqlite3 rl_episodes.db "SELECT COUNT(*) FROM episodes WHERE source='live';"
  ```

- **ADR-18 Amendment D context.** v10 P5 entry-gate split (v10.1-mode vs v10.3-mode) clarified that the original `is_ready_for_shadow()` semantics belong to v10.3 mode; a sibling v10.1-mode predicate covers deterministic-policy (current v10.1) operation. See `docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendments" 2026-05-18 — v2.4 P0 Amendment D. P4 trainer itself remains correct under both modes; the gate split is a P5 entry-condition change, not a P4 trainer change.

### P5 - Shadow A/B + ship criteria ([DONE] INFRA SHIPPED at #214 / `07ee05c`, 2026-05-22; empirical shadow soak outstanding, ~95%)

- Phase prompt: `docs/prompts/v10-orchestration/phase-5-shadow-stop-conditions.md`.
- Scope: `rl/shadow.py` (ghost-path candidate exec), `rl/cli/shadow.py`, `rl/cli/check_criteria.py`, `rl/stop_conditions.py` (6 pre-registered ship criteria), tests, ADR append.
- **Implementation shipped at v2.8 P1 PR #214 (`07ee05c`, 2026-05-22 15:11):** `rl/shadow.py` `ShadowRecorder` (non-invasion budget 50 ms, WAL-mode `rl_shadow.db`, split `_dropped` vs `_budget_violations` counters), `rl/stop_conditions.py` six pre-registered ship criteria (`shadow_reward_improvement`, `fr_og_7_violations`, `cand_prod_agreement`, `alignment_pass_rate`, `posterior_ci`, `parameter_drift`; constants frozen, not env-overridable), `rl/cli/{shadow,check_criteria}.py` CLI surfaces, `tools/soak_driver.py` opt-in `--shadow-recorder` + `--shadow-proposal` flags. 24/24 shadow + 30/30 sibling RL tests pass; CodeQL clean. ADR-5 §"v10 shadow overhead" + ADR-18 v2.8 P1 amendment appended.
- NON-INVASIVE: shadow subscribes to bus, runs candidate in-process, writes `rl_shadow.db`. Never affects production decision flow.
- Strategy: in-process via `tools/soak_driver.py --shadow-recorder rl_shadow.db --shadow-proposal <path>`. Fallback if `soak_driver` freezes between P3 and P5 = sidecar JSONL-tail post-run write.
- Exit: shadow run on Tier-3 soak produces (production, candidate, state, ground-truth) tuples; all 6 ship criteria evaluated; ship/no-ship verdict reproducible.
- **Remaining gap (NOT infra):** the empirical Tier-3 shadow soak that produces real (production, candidate, state, ground-truth) tuples and exercises the criteria checker end-to-end is still outstanding. This is the true MVP blocker - it closes #112 -> #131 -> #124/#125. The synthetic-fixture harness validates the infrastructure offline (`--mode=v10.1` infra-validation only) but does NOT satisfy the pre-registered v10.3 ship criteria; a real Tier-3 soak does (robin owns the criteria read).

#### Docs-side gate cleared via ADR-18 Amendment D (2026-05-18, v2.4 P0)

The original P5 entry gate (`is_ready_for_shadow()` requiring non-baseline `best_arm` with posterior CI ≤ 0.10) was structurally unreachable under v10.1's deterministic production policy — off-baseline arms received zero on-support data and CI stayed at the warm-start floor regardless of episode count (root cause documented in `project_v10_p5_gate_deadlock.md` and issue #177, closed at v2.4 P0). **ADR-18 Amendment D splits the gate into two modes:**

| Mode | Active when | Gate condition |
|---|---|---|
| **v10.1-mode** | v10.x stages 0-2 (deterministic production policy) | baseline arm `_total >= 200` AND `posterior_ci_width(baseline_arm) <= 0.10`; P5 runs as infrastructure validation (baseline-vs-baseline) |
| **v10.3-mode** | v10.3 stochastic propensity writeback active | original gate: non-baseline `best_arm` clears `_total >= 200 AND best_arm_posterior_ci() <= 0.10`; ship criteria checker may exit 0 (ALL PASS) |

See `docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendments" 2026-05-18 — v2.4 P0 Amendment D for full mechanism (sibling `is_ready_for_shadow_v10_1()` method, additive `ready_v10_1` + `mode` keys on `proposals.promotion_gate` envelope, `--mode=v10.1` `soak_run_id` suffix to keep infrastructure-validation runs out of v10.3 writeback promotion accounting).

#### Implementation-side gate: Seed v2.6-C (Path-D synthetic-fixture P5, ~600 LOC) - [DONE] SHIPPED at v2.8 P1 PR #214 (`07ee05c`)

Implementation was deferred across 4 consecutive cycles (v2.4 + v2.5 + v2.5.1 + v2.6), renamed across cycles: Seed v2.4-C -> Seed v2.5-C (v2.5 P0 backlog) -> Seed v2.6-C (v2.6 P2 close-out per `docs/v2.6-backlog.md` section "Carry-forwards from v2.6" item 1). It **landed at v2.8 P1 PR #214 (`07ee05c`, 2026-05-22)** as the Path-D synthetic-fixture P5 implementation: shadow recorder, six-criteria stop-condition harness, two CLI surfaces, and the `soak_driver` hook, with 24/24 shadow tests + 30/30 sibling RL tests passing. The Path-D synthetic-fixture validates the infrastructure offline; it does NOT close #112, because the pre-registered ship criteria require a real Tier-3 shadow soak (`--mode=v10.1` is infra-validation only).

The **remaining head-of-chain blocker** is therefore no longer the P5 implementation - it is the empirical Tier-3 shadow soak. Closing it advances the entire downstream tail (#112 -> #131 -> #124 + #125).

---

## 4. Held-chain map

**Chain collapsed from 5-deep to 4-deep at the v2.4 boundary, then the P5-implementation link cleared at v2.8 P1.** Issue #111 (P4 trainer) closed at v2.4 P0 PR #179 (`b35e982`); corpus 200-row gate cleared with margin (608 episodes post v2.6 P2 Run 7). Seed v2.6-C (Path-D synthetic-fixture P5 implementation) **SHIPPED at v2.8 P1 PR #214 (`07ee05c`)**. Head-of-chain is now the **empirical Tier-3 shadow soak** (the only thing that satisfies the pre-registered ship criteria and closes #112).

```
Empirical Tier-3 shadow soak (real production/candidate/state/ground-truth tuples) - OUTSTANDING
   (P5 infra SHIPPED v2.8 P1 PR #214 `07ee05c`; synthetic-fixture --mode=v10.1 validates infra only)
   \-- #112 (P5 shadow) - BLOCKED on empirical Tier-3 shadow soak
        \-- #131 (v10.x cycle frame: ADR-18 freeze-lift trigger) - BLOCKED on #112
             +-- #124 (wire BRIDGE_L4_FALLBACK_CONFIDENCE + un-ADVISORY stage-1) - BLOCKED on #131
             \-- #125 (restore Ridge-Q DR estimator) - BLOCKED on #131
```

Tail-end (#124 + #125) remains constrained to **env-flag wiring only** by ADR-18 surface-freeze (Rule 1) until #131 mints the freeze-lift cycle frame.

**Cycle-frame skeleton:** `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md` minted 2026-05-11 (PR #140 merged at `568b72e`); do-not-fire until 3 trigger conds hold. Skeleton itself is EXPERIMENTAL under ADR-18 (pre-trigger; FROZEN/EVOLVING decision deferred to P0 fire-time per skeleton L35).

**Trigger conditions for #131 cycle frame mint** (all 3 required):

1. **#112 closed** - bandit + shadow A/B observed under stable production >= 1 cycle, ship criteria met. (P5 infra shipped at v2.8 P1 PR #214; now gated on the empirical Tier-3 shadow soak that satisfies the pre-registered ship criteria.)
2. **v2.x slot opens** — no overlapping v2.x feature cycle in P0–P3 (concurrent freeze-lifts fragment seam-touch surface).
3. **#124 + #125 still open** — confirm not retired by alt seam.

When all 3 hold → mint `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md` + open v10.x bundle PR.

---

## 5. Open follow-ups (non-held)

| # | Title | Status | Bucket |
|---|---|---|---|
| #111 | v10 P4 — Bandit trainer (Thompson + CMDP + promotion gate) | ✅ CLOSED v2.4 P0 PR #179 (`b35e982`); trainer shipped v2.3 PR #176 (`cf7d003`) | — |
| #118 | `rl_test_helper` schema-parity vs `rl/schema.sql` | ✅ CLOSED (`52e8874`, PR #139) | — |
| #177 | v10 P5 entry-gate deadlock (Amendment D) | ✅ CLOSED v2.4 P0 PR #179 (`b35e982`) | — |
| #112 | v10 P5 - Shadow A/B + ship criteria | [BLOCKED] on empirical Tier-3 shadow soak (P5 infra SHIPPED v2.8 P1 PR #214 `07ee05c`) | v10 chain (head) |
| #124 | Wire `BRIDGE_L4_FALLBACK_CONFIDENCE` + promote `_stage_1_golden` from ADVISORY | 🔒 BLOCKED on #131 | v10 chain |
| #125 | Restore Ridge-Q DR estimator | 🔒 BLOCKED on #131 | v10 chain |
| #131 | v10.x cycle frame mint trigger | 🔒 BLOCKED on #112 | v10 chain |

---

## 6. Robin agent (companion side-track)

- **Status:** SHIPPED at commit `24bc1d6` / PR #115.
- **Role:** v10 RL track testing lifecycle (P1–P5). Collects requirements from phase prompts, monitors specified sessions, summarises `rl_episodes.db` / `rl_shadow.db`, ingests validation reports, produces ship/dormant verdict.
- **Boundaries:** read-only against governance + DBs; refuses FROZEN edits; refuses to launch long-running soaks (main thread owns those per `feedback_subagent_long_task_abandonment.md`).

### Open robin issues (low-pri side track)

| # | Title | Status |
|---|---|---|
| #116 | PreToolUse hook enforce Bash < 5min | OPEN (low pri) |
| #117 | Deny direct `sqlite3` against RL DBs | OPEN (low pri) |

Pre-spike for #116: confirm PreToolUse can distinguish calling agent (main vs robin) before hook implementation. If not, scope deny to specific commands.

---

## 7. ADR-18 posture (v10 surfaces)

| Surface | State | Source cycle | Notes |
|---|---|---|---|
| `rl/state_features.py` | EVOLVING | v10 P1 | pure feature extractor; no FROZEN coupling |
| `rl/schema.sql` + `rl/episode_logger.py` | EVOLVING | v10 P1 | dedicated DB writer (D2 invariant) |
| `rl/corpus_augment.py` + `rl/sources/*` | EVOLVING | v10 P2 | additive |
| `rl/ope.py` + `rl/validate.py` + `rl/cli/validate.py` | EVOLVING | v10 P3 | gauntlet shipped with stage-1 ADVISORY tag |
| `model_router.route` + pre-CLI seam (governance / cli_governance) | FROZEN | v1.x/v2.x | reclassification to EVOLVING required for #124 → handled by #131 cycle frame |
| `tools/soak_driver.py` | EVOLVING | v2.0 P1 | re-verify at P5 start; if flipped to FROZEN, re-mint P5 prompt with sidecar fallback |
| `governance.GovernanceConfig.l4_confidence_threshold` | FROZEN | v1.x | reclassification deferred to v10.3 amendment (DRAFT in design §11; not enacted) |

---

## 8. Hard constraints (CMDP) — ship gate per shadow

A candidate threshold is INFEASIBLE and dropped from the action set BEFORE Thompson sampling if ANY:

1. **FR-OG-7 violation count > 0** on alignment-golden replay (every shadow-evaluated candidate; zero-tolerance).
2. **HITL agreement < baseline − 2 %** absolute on logged subset (computed via IPS over `rl_episodes.db`).
3. **Alignment-eval pass rate < baseline pass rate** (golden replay, n=32).

Constraint violations REJECT the candidate; they do NOT modify the reward. Constraint-violating EPISODES remain in the log for observability.

---

## 9. Pre-registered ship criteria (P5 / v10 → v10.1)

Per design §10. NOT relaxed based on observed data (p-hacking guard). 3 retrains × 3 shadows failing = v10 enters DORMANT-N per ADR-18 Rule 2.

| Criterion | Threshold | Window |
|---|---|---|
| Shadow reward improvement | reward(candidate) ≥ reward(baseline) + 0.02 | 3 consecutive Tier 3 shadows |
| FR-OG-7 violations | 0 | every shadow (full alignment-golden + adversarial) |
| HITL agreement | ≥ baseline − 2 % absolute | every shadow |
| Alignment-eval pass rate | ≥ baseline pass rate | every shadow |
| Posterior CI on best arm | ≤ 0.10 | computed at retrain |
| Parameter drift between retrains | \|Δθ\| ≤ 0.02 | 3 consecutive retrains |

Advisory observability signals (NOT ship gates) per §10a:
- Cassette p95 ≤ 10 % regress
- Action-distribution ≤ 20 % shift

Re-evaluation in v10.3 if cassette regression empirically correlates with shadow regression.

---

## 10. v10.3 RL writeback — DRAFT amendment (NOT ENACTED)

Per design §11. Lands ONLY when §9 ship criteria PASS for ≥ 1 cycle.

> **ADR-18 Amendment §"v10.3 RL writeback authority"** (DRAFT v10 P0; not enacted).
>
> Reclassify FROZEN → EVOLVING:
> - `governance.GovernanceConfig.l4_confidence_threshold` (read site → write site).
>
> All other gov symbols remain FROZEN. Trainer writes `rl_proposals/<UTC>Z.json`; separate `rl/cli/writeback.py` applies manifest. Writeback gated on:
>
> 1. `rl.cli.check_criteria` exit code 0.
> 2. Human approval (HITL gate; no auto-promotion).
> 3. Post-writeback Tier 3 soak validates against same 6 criteria.
>
> Rollback: `rl/cli/writeback.py --rollback` restores prior threshold. Automatic on post-writeback Tier 3 criteria failure.

Refinement deferred to v10.3 phase prompt after ≥ 200 episodes of v10.0–v10.2 observation.

---

## 11. Reproducibility

Per design §12. Every train run writes:

- `rl_proposals/<UTC>Z.json` — top-3 feasible candidates, posterior summary, IPS per candidate.
- `rl_proposals/<UTC>Z.manifest.json` — seed, `rl_episodes.db` SHA, hyperparams, full per-arm posterior, candidate set.

Shadow runs reference manifests by SHA. End-to-end traceability: episode → manifest → proposal → shadow → criteria report.

---

## 12. Cross-references

- Design: `docs/v10-rl-design.md` (P0 accepted).
- Phase prompts: `docs/prompts/v10-orchestration/phase-{0,0a,1,2,3,4,5}-*.md`.
- Master TODO: `docs/jobs/MASTER.md` §"v10 chain — held".
- Per-issue jobs: `docs/jobs/issue-{111,112,118,124,125,131}.md`.
- Memory: `project_v10_rl_track.md`; `project_v10_p5_gate_deadlock.md` (Amendment D resolution path; status FILED at v2.4 P0, AMENDMENT-LANDED docs-side, implementation DEFERRED v2.5).
- ADR-18: `docs/adr/ADR-18-mvp-surface-freeze.md` §"Initial classification"; §"Amendments" 2026-05-18 — **v2.4 P0 Amendment D** (v10 P5 entry-gate split, v10.1-mode vs v10.3-mode).
- ADR-5: `docs/adr/ADR-5-latency-budget.md` §"v10 logging overhead" + §"v10 shadow overhead" (landed at v2.8 P1 PR #214, `07ee05c`).
- ADR-17: `docs/adr/ADR-17-soak-tiers.md` (Tier 3 = shadow vehicle).
- Robin agent: PR #115, commit `24bc1d6`.
- v2.4 backlog (carries Seed v2.4-C Path-D synthetic-fixture P5 implementation forward): `docs/v2.4-backlog.md` §"Carry-forwards from v2.4" + §"NEW v2.4 ship-gate seeds".
- v2.6 backlog (carries Seed v2.6-C Path-D synthetic-fixture P5 implementation forward — 4th consecutive deferral; ground truth for v2.6 P2 corpus + dispositions): `docs/v2.6-backlog.md` §"Carry-forwards from v2.6" item 1 + §"v2.6 P2 measurement summary".
- 2026-05-19 status snapshot (Bucket 2 — v10 RL chain): `docs/2026-05-19-status.md`.
- v2.4 P0 PR #179 (`b35e982`): bundles #111 close + Amendment D + Amendment E.
- v2.3 PR #176 (`cf7d003`): bandit trainer implementation (P4 code-side ship).
- v2.8 P1 PR #214 (`07ee05c`, 2026-05-22): Path-D synthetic-fixture P5 implementation (shadow recorder + six-criteria stop-condition harness + 2 CLI surfaces + soak-driver hook + ADR-5 section "v10 shadow overhead" + ADR-18 v2.8 P1 amendment); 24/24 shadow + 30/30 sibling RL tests pass.
- v2.5 / v2.5.1 cycle close memory (corpus Run 5 absence + Run 6 piggyback; first v2.x corrective sub-phase; Seed v2.4-C → v2.5-C rename): `project_v25_cycle_close.md`.
- v2.6 cycle close memory (Run 7 piggyback to 608; Seed v2.5-C → v2.6-C rename; lever ledger BUMP 1 → 2; first lever-wire since v2.3): `project_v26_cycle_close.md`.

---

## 13. v10 vs v2.1 P1 — orthogonality note

v10 is a **companion track** to the v1.x/v2.x main cycle. v2.1 P1 (PPP audit harness Layer 1) is independent of v10 P4/P5. PPP `audit.probe` envelopes are NOT logged into `rl_episodes.db` — they are governance trust signals, not bandit observations. v10 episode logger reads from production `governance.evaluate()` outcomes; PPP probe acks resolve a separate provenance question (which JSONL stream is being driven). The two tracks share `MessageBus` SQLite WAL but write to peer tables (`rl_episodes.db` vs `provenance_assertions`).

Cross-cycle sequencing (historical -> current): v2.1 P1 landed while v10 P4 was held; no scheduling collision. v10 P4 implementation shipped at v2.3 PR #176 (`cf7d003`); issue #111 closed at v2.4 P0 PR #179 (`b35e982`). v2.5 + v2.5.1 ran as consolidation (v2.5 P2 BLOCKED at S4 Sonnet floor breach -> v2.5.1 corrective sub-phase shipped at PR #190 / `c1e9070`); neither sub-phase advanced P5 implementation, and Seed v2.4-C renamed to Seed v2.5-C in `docs/v2.5-backlog.md`. v2.6 ran as feature with Seed v2.5-G step (1) wall-clock instrumentation lever-wire at PR #196 / `7220b33` (first lever-wire since v2.3; ledger 1 -> 2); v2.6 P2 shipped at PR #198 / `c3a964c` with Run 7 piggyback bringing the corpus to 608 episodes, but P5 implementation remained deferred and Seed v2.5-C renamed again to Seed v2.6-C per `docs/v2.6-backlog.md` (4th consecutive deferral across v2.4 + v2.5 + v2.5.1 + v2.6). **P5 implementation then shipped at v2.8 P1 PR #214 (`07ee05c`, 2026-05-22)** as the Path-D synthetic-fixture P5 implementation (Seed v2.6-C cleared). The remaining open item is the **empirical Tier-3 shadow soak** - the only artefact that satisfies the pre-registered ship criteria and closes #112 -> #131 -> #124 + #125 in sequence; the synthetic-fixture harness validates the infrastructure offline but does not substitute for the real soak.
