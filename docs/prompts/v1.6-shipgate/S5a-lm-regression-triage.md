# S5a — LM regression triage

**Goal:** Triage v1.6 LM (categorize) p95 = **18.60s** vs ceiling 18s
(+0.60s, +3.3%). Decide: ship-block + re-soak, ship-with-v1.7-watch, or
no-op (sample noise).

## Context

- v1.4 ship-gate: LM p95 = 19.26s.
- v1.5 ship-gate: LM p95 = 15.39s (watch conditionally closed).
- v1.6 ship-gate: LM p95 = **18.60s** (n=10 in soak).
- Trend reversed: down 19.26 → 15.39, then back up 15.39 → 18.60.
- Still below v1.4 baseline; over v1.5 ceiling by 0.60s.
- LM is **advisory/categorize**, not on critical decision path
  (per `project_learn_mode.md`, "advisory bias only; never overrides safety").
- v1.6 P1 driver attribution (S4) shows `cli_pool_send_ms` is the
  evaluate_inner driver; LM categorize is a separate code path
  (categorizer subprocess, not the gov decision CLI worker).

## Steps

1. Confirm sample size: re-read soak report's `LM (categorize)` row,
   capture `n=` count. n<15 = high variance, lean ship-with-watch.
2. Variance check: if soak report has p50 + max for LM, compute spread.
   Report `lm_categorize_ms` p50=12.69s p95=18.60s — spread 5.91s.
3. Cross-check: scan `tmp/soak-dashboard-20260505T073943Z.log` for any
   LM-related warnings, retries, timeouts, or worker churn.
4. Compare to v1.5 cassette coverage (per
   `feedback_cassette_must_cover_new_envelopes.md`): did v1.6 add any
   new envelopes that LM categorizer must classify? If yes, that's
   plausible cause for cold-classify spike. Check
   `tools/cassette_record.py` and `tools/soak_driver.py` diff vs v1.5
   ship-gate base (`95ffb83`).
5. Decision rubric:
   - magnitude ≤ 1s over ceiling AND n ≤ 10 AND no log anomaly
     → **ship-with-v1.7-watch** (mint v1.7 backlog item, ship v1.6).
   - magnitude > 1s over ceiling OR log anomaly OR cassette gap
     → **ship-block + re-soak** (mint S5b-lm-resoak.md, requires S2 redo).
   - LM block structurally broken (n=0, cassette missing)
     → mint `S5b-lm-cassette-coverage.md` (per
     `feedback_cassette_must_cover_new_envelopes.md`).

## Acceptance

- Triage decision recorded in checklist with magnitude + n + log finding.
- If ship-with-v1.7-watch: v1.7 backlog seed item drafted for S8 paste-in
  (LM p95 watch with re-baseline target).
- If ship-block: S2 re-launch authorized, prior gates rolled back.

## On-done ack

`- [x] LM p95=18.60s n=<N> log=<clean|anomaly> **S5a — LM regression triage** [ship-with-v1.7-watch / ship-block]`

## Mint-new check

- Re-soak required → mint `S5b-lm-resoak.md` (rolls S2/S3/S5 back).
- Cassette gap found → mint `S5c-lm-cassette-fill.md` (in-cycle fix
  before re-soak).
