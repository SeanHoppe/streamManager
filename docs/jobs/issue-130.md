# #130 — ADR-18 amendment: feature-cycle LOC soft target (Rule 3 extension)

**Status:** OPEN — mint at v2.2 P0 (paired with #133).
**Bucket:** v2.2 P0.
**GH:** https://github.com/SeanHoppe/streamManager/issues/130

## Summary

ADR-18 Rule 3 caps consolidation cycles at net LOC ≤ 0. Feature cycles uncapped.
v1.9 (+2800 LOC) triggered ADR-18; v2.1 estimate ~+750–1400. No anchoring ground.

## Proposed Rule 3 extension

> Consolidation cycles ≤ 0. Feature cycles target ≤ 1500 LOC by default; exceeding requires
> operator override recorded in cycle frame. Threshold PROVISIONAL through v2.3 P0 — re-calibrate
> at ≥4 feature-cycle data points.

| Cycle | Net LOC | Type | Notes |
|---|---|---|---|
| v1.9 | +2800 | feature | trigger |
| v2.0 | −1031 | consolidation | passes |
| v2.1 | ~+750–1400 | feature | passes proposed 1500 |

## Acceptance (folded refinements)

- [ ] ADR-18 §"Amendments" entry minted with Rule 3 extension.
- [ ] §C1 threshold marked PROVISIONAL + re-calibration trigger at v2.3 P0 (≥4 feature data points; recompute via p75 or median+stddev).
- [ ] §C3 "Net LOC" measurement scope: 3 buckets — production (`src/`), test (`tests/`), docs (`docs/` + `*.md`). Production load-bearing; test+docs advisory.
- [ ] §C4 cycle-start commit = prior cycle's release tag SHA (e.g. v2.0.0 = `401ae47` for v2.1). NOT P0 merge SHA. Ship-gate: `git diff <prior-tag>...HEAD --stat`.
- [ ] §C5 BLOCK threshold = 1.5× soft target (= 2250 LOC), NOT 2×. Reason: 2× = 3000, retro-permits v1.9.
- [ ] Override mechanism specified (cycle-frame doc / cycle-close memory / ADR-18 amendments table).
- [ ] §C2 per-phase sub-question DROPPED (insufficient data; defer post-v2.3).
- [ ] LOC threshold finalised against historical + v2.1 actual at P4.
- [ ] `tools/soak_driver.py` post-soak LOC delta summary updated to compute against new threshold (additive output only).

## Timing

Defer til v2.1 P4 close-out — calibrate against v2.1 actual delta. v2.2 P0 mints.

## Refs

- `docs/v2.1-task-plan.md` §"Cross-cutting risks" item 7.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Rule 3".
- `project_v20_cycle_close.md`.
- Companion: #133.
