# #124 — v10.x: wire `BRIDGE_L4_FALLBACK_CONFIDENCE` at `model_router.route` callsite; promote `_stage_1_golden` from ADVISORY

**Status:** BLOCKED on #131 (ADR-18 freeze-lift cycle not yet minted).
**Bucket:** v10 chain.
**GH:** https://github.com/SeanHoppe/streamManager/issues/124

## Origin

PR #123 post-merge review (severity 🔴, deviation #6). Cross-ref `docs/v10-rl-design.md` §10c.

## Problem

`rl/validate.py:_verdict_under_threshold` = hand-rolled bin-distance heuristic, NOT
`model_router.route` replay against candidate L4 fallback threshold. Borderline non-bin-edge
FR-OG-7 regressions (Δ ∈ (0, 0.05]) won't trip stage 1. `BRIDGE_L4_FALLBACK_CONFIDENCE` env var
documented but NOT wired at any callsite in `src/` or `tools/`.

## Why not in P3

ADR-18 Rule 1 (surface freeze) blocked wiring inside v10 P3. PR demoted stage 1 to ADVISORY.
Ship NOT blocked (`tools/alignment_eval.py` is real-CLI gate). Regression-detection gap inside OPE
harness remains.

## Acceptance

1. `BRIDGE_L4_FALLBACK_CONFIDENCE` (or equivalent threshold param) wired at `model_router.route`
   callsite — likely `governance.py` or `cli_governance.py`. Identify single canonical pre-CLI seam, pass threshold through.
2. `_verdict_under_threshold` replaced by `route()`-based replay re-evaluating each golden row's
   recorded confidence against candidate threshold. Drop bin-distance heuristic.
3. ADR-18 reclassification of touched surfaces (`model_router.route` signature, governance/cli_governance pre-CLI seam) FROZEN → EVOLVING for the wiring change. Document rationale in cycle frame.
4. `_stage_1_golden` ADVISORY tag drops; render reverts to `## stage_1_golden — PASS`.
5. Regression test in `tests/test_rl_validate.py`: synth golden row with confidence ∈
   (baseline_thr − 0.05, baseline_thr) and candidate thr ≥ confidence. Heuristic would PASS;
   `route()`-based replay must FAIL.
6. `docs/v10-rl-design.md` §10c stage-1 ADVISORY paragraph removed/rewritten.

## Out of scope

- Wiring inside live production decision path (this is OPE-replay only; production FR-OG-7 gate is `tools/alignment_eval.py`).
- DR Ridge-Q follow-up = #125.

## ADR-18 posture

Falsify-before-extend Rule 3 path. `_verdict_under_threshold` deletion partially funds `route()` import + replay LOC.

## Refs

- PR #123.
- `docs/v10-rl-design.md` §10c.
- Sibling: #125.
- Cycle parent: #131.
