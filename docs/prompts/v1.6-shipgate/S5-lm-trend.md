# S5 — Re-check LM trend

**Goal:** Confirm Learn-Mode (categorize) p95 trend stays ≤18s ceiling. Closes
the v1.5-opened LM watch OR carries it into v1.7.

## Context

v1.5 ship-gate: LM p95 trend retreated 19.26s → 15.39s. Watch closed pending
v1.6 re-confirm. Source: soak report's LM breakout / `lm_categorize_ms` percentile.

## Steps

1. From S3 report, locate LM categorize p95 (`lm_categorize_ms` or equivalent
   key — check `_format_lm_breakout` in `tools/soak_driver.py`).
2. Compare vs v1.5 baseline 15.39s.
3. Decision:
   - p95 ≤ 18s AND trending flat/down → watch CLOSED, document in CHANGELOG.
   - p95 ≤ 18s but creeping up → watch EXTENDED into v1.7.
   - p95 > 18s → REGRESSION; mint `S5a-lm-regression-triage.md` (potential
     ship-blocker depending on magnitude).

## Acceptance

- LM p95 number captured.
- Watch decision recorded (closed / extended / regression).

## On-done ack

`- [x] LM p95=<X>s (vs v1.5 15.39s) **S5 — Re-check LM trend** [closed/extended/regression]`

## Mint-new check

- p95 > 18s → mint `S5a-lm-regression-triage.md`.
- If LM block missing from soak report (cassette regression), mint
  `S5b-lm-cassette-coverage.md` (per `feedback_cassette_must_cover_new_envelopes.md`).
