You are framing **Phase P0 — v10.x cycle frame** for the streamManager
v10.x ADR-18 freeze-lift cycle.

> **SKELETON — do not fire until trigger conditions met.** This file is
> minted in advance per [#131](https://github.com/SeanHoppe/streamManager/issues/131)
> so the chain has a parking spot. Verify ALL THREE trigger conditions
> before treating this prompt as live.

## Trigger conditions (all 3 required to fire)

1. **v10 P5 [#112](https://github.com/SeanHoppe/streamManager/issues/112)
   closed** — bandit trainer (#111) + shadow A/B under stable
   production ≥ 1 cycle, all 6 ship criteria PASS (shadow reward
   improvement ≥ 0.02; FR-OG-7 violations = 0; HITL agreement ≥
   baseline − 2%; alignment pass rate ≥ baseline; posterior CI ≤
   0.10; |Δθ| ≤ 0.02).
2. **v2.x cycle slot opens** — no overlapping v2.x feature cycle in
   P0–P3. Concurrent freeze-lifts fragment seam-touch surface.
3. **#124 + #125 still open** — confirm not retired by alt seam since
   last review.

If ANY condition fails → re-evaluate at next cycle planning juncture.
Record outcome in #131 comment thread.

## Branch + base

- Base: `main` after v10.0 ship (P5 close).
- PR target: `main`.
- Branch: `feat/v10x-cycle-frame`.

## Cycle inheritance

v10.x inherits **ADR-18 cycle-discipline rules in full force**:

1. Surface freeze (FROZEN / EVOLVING / EXPERIMENTAL classifications).
   **This cycle's distinguishing act is reclassifying
   `model_router.route` + `cli_governance` pre-CLI seam from FROZEN
   to EVOLVING.** Reclassification must land at P0 as ADR-18
   amendment.
2. DORMANT-N falsify-before-extend (cumulative dormant counter).
3. Consolidation discipline: net LOC ≤ 0 — **does NOT apply here**.
   v10.x is feature-shaped (wires + restores). LOC offsets per #124
   (delete `_verdict_under_threshold` heuristic) + #125 (Ridge-Q
   restoration; +80 LOC source) partially balance.
4. Phase budget: 4 phases (P0/P1/P2/P3 + P4 ship-gate).
5. Backlog hard cap.

## Operator decisions recorded at P0

**Cycle type: FEATURE (freeze-lift).** Two ADR-18-blocked
deliverables (#124, #125) graduate from blocked-by-classification
state.

**P0 deliverable: ADR-18 amendment.** Reclassify the
`model_router.route` callsite + `cli_governance` pre-CLI seam from
FROZEN → EVOLVING with scope-of-EVOLVING constraint (write to
`docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendments"; cite v10.x
cycle as authority; bound the EVOLVING window to this cycle).

**P1 — wire BRIDGE_L4_FALLBACK_CONFIDENCE + un-ADVISORY stage-1
golden** (closes [#124](https://github.com/SeanHoppe/streamManager/issues/124)).
- Wire env var at `model_router.route` callsite (likely inside
  `governance.py` or `cli_governance.py` — confirm at P1 start).
- Replace `rl/validate.py:_verdict_under_threshold` bin-distance
  heuristic with `route()`-based replay.
- Drop `metrics["advisory"] = True` + restore plain `## stage_1_golden
  — PASS`.
- Regression test in `tests/test_rl_validate.py` per #124 AC.

**P2 — restore Ridge-Q DR estimator** (closes
[#125](https://github.com/SeanHoppe/streamManager/issues/125)).
- Implement `q_hat(state, action) = state_features @ θ` Cholesky
  closed-form `θ = (XᵀX + αI)⁻¹ Xᵀr`.
- Implement Hájek DR + 5-fold CV-DR.
- Restore DR rendering in `_stage_2_ips`.
- Drop alias tests, add real DR-vs-IPS variance tests.

**P3 — cassette + soak coverage for now-EVOLVING seam.** Extend
`tools/cassette_record.py` + `tools/soak_driver.py` to exercise the
threshold-pass path (per `feedback_cassette_must_cover_new_envelopes.md`).

**P4 — ship-gate.** Full Tier-3 soak; verify P3 OPE gauntlet stage-1
flips from ADVISORY → real PASS; verify p95 unchanged vs v10.0;
re-freeze touched surfaces unless v10.3 amendment promotes them
further.

## Pivot rationale (record at P0 fire)

[Fill at fire time.] If alternative un-ADVISORY path or alt DR
estimator surfaced between hold-lift (2026-05-11) and cycle-frame
fire, document the decision against the original #124/#125 plan.

## LOC ledger (estimated)

| Phase | Add | Delete | Net |
|---|---|---|---|
| P0 (ADR-18 amendment) | ~30 docs | 0 | +30 |
| P1 (#124) | ~60 src + ~40 tests | ~25 (heuristic) | +75 |
| P2 (#125) | ~80 src + ~30 tests | ~10 (alias tests) | +100 |
| P3 (cassette+soak) | ~40 | 0 | +40 |
| **Cycle total** | **~280** | **~35** | **+245** |

Feature cycle posture: LOC unbounded but tracked.

## Cross-references

- Predecessor: v10.0 ship (P5 close).
- Hold-lift memory: `project_v10_p4_hold_lifted.md`.
- ADR-18: `docs/adr/ADR-18-mvp-surface-freeze.md` §"Initial
  classification" + (new) §"Amendments — v10.x pre-CLI seam".
- Blocked issues: [#124](https://github.com/SeanHoppe/streamManager/issues/124),
  [#125](https://github.com/SeanHoppe/streamManager/issues/125).
- Tracker: [#131](https://github.com/SeanHoppe/streamManager/issues/131).
- v10 design doc: `docs/v10-rl-design.md`.
- Status doc: `docs/v10-mvp-status.md` §4 "Held-chain map".

## DOD (P0 only)

- [ ] All 3 trigger conditions verified + recorded in #131 thread.
- [ ] ADR-18 amendment drafted at `docs/adr/ADR-18-mvp-surface-freeze.md`
      §"Amendments".
- [ ] `docs/v10x-task-plan.md` written (P1–P4 scope + LOC ledger).
- [ ] Phase prompts P1/P2/P3/P4 stubbed under
      `docs/prompts/v10x-orchestration/`.
- [ ] Memory `project_v10x_cycle_frame.md` written.
- [ ] Single PR `feat(v10x):` against `main`.

Report back when P0 PR is open with: PR URL, ADR-18 amendment
language, P1 phase-1 prompt link.
