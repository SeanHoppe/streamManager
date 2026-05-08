# #131 — v10.x cycle frame: mint trigger for #124 + #125 ADR-18 freeze-lift

**Status:** BLOCKED on #112 (which is BLOCKED on #111).
**Bucket:** v10 chain.
**GH:** https://github.com/SeanHoppe/streamManager/issues/131

## Summary

#124 + #125 ADR-18-blocked while `model_router.py` + `cli_governance.py` pre-CLI seam stays FROZEN.
No parent issue tracking the cycle that lifts those classifications. This is that parent.

## Trigger conditions (all 3)

1. **#112 closed** — bandit + shadow-A/B observed under stable production ≥ 1 cycle, ship criteria met.
2. **v2.x slot opens** — no overlapping v2.x feature cycle in P0–P3 (concurrent freeze-lifts fragment seam-touch surface).
3. **#124 + #125 still open** — confirm not retired by alt seam.

When all 3 hold → mint `docs/prompts/v10x-orchestration/phase-0-cycle-frame.md`, open v10.x bundle PR.

## Cycle scope sketch

- P0: cycle frame + ADR-18 amendment for pre-CLI seam reclassification.
- P1: #124 — wire `BRIDGE_L4_FALLBACK_CONFIDENCE` + promote `_stage_1_golden`.
- P2: #125 — restore Ridge-Q DR estimator.
- P3: cassette + soak coverage for now-EVOLVING seam.
- P4: ship-gate.

## Acceptance

- [ ] All 3 trigger conditions checked at cycle-planning juncture; result recorded here.
- [ ] If trigger met: v10.x cycle frame minted + P0 prompt drafted under `docs/prompts/v10x-orchestration/`.
- [ ] If trigger met: ADR-18 §"Amendments" entry drafted (pre-CLI seam: FROZEN → EVOLVING with EVOLVING scope constraint).
- [ ] #124 + #125 cross-linked as P1/P2.
- [ ] If trigger NOT met after #112 close: re-evaluate at next cycle planning.

## Refs

- #124, #125 (ADR-18-blocked deliverables).
- #112 (predecessor).
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Initial classification".
- Memory `project_v10_rl_track.md`.
