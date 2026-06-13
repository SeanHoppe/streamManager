# v10 OPE validation report

- candidate manifest: `v10p4-live-20260518`
- baseline  manifest: `v10p4-live-20260518-baseline`
- candidate L4 threshold: 0.900 | baseline L4 threshold: 0.700
- delta: 0.020

## stage_1_golden — PASS (ADVISORY)

10 FR-OG-7 rows checked, 0 regressions

```json
{
  "advisory": true,
  "advisory_reason": "BRIDGE_L4_FALLBACK_CONFIDENCE unwired; bin-distance heuristic not model_router.route replay",
  "baseline_l4_threshold": 0.7,
  "candidate_l4_threshold": 0.9,
  "fr_og_7_total": 10,
  "regressions": []
}
```

## stage_2_ips — PASS (ADVISORY)

no live/soak episodes; skipped (insufficient data)

```json
{
  "advisory_skipped": true,
  "n": 0,
  "skipped": true
}
```

## stage_3_cassette — PASS

p95 regress=0.0% (cap 10%, ADVISORY); action TV-shift=0.0% (cap 20%, ADVISORY)

```json
{
  "action_shift_tv": 0.0,
  "advisory_thresholds": true,
  "baseline": {
    "actions": {
      "ALLOW": 65,
      "AMBIGUOUS": 5
    },
    "fallback_fire_rate": 0.07142857142857142,
    "n": 70,
    "p50_s": 4.6044025,
    "p95_s": 12.073726649999998
  },
  "candidate": {
    "actions": {
      "ALLOW": 65,
      "AMBIGUOUS": 5
    },
    "fallback_fire_rate": 0.07142857142857142,
    "n": 70,
    "p50_s": 4.6044025,
    "p95_s": 12.073726649999998
  },
  "cassette": "tests/fixtures/soak_cassette_latest.jsonl",
  "p95_regression_pct": 0.0
}
```

## stage_4_adversarial — PASS

no adversarial episodes available; stage skipped

```json
{
  "n": 0,
  "skipped": true
}
```

## VERDICT: PASS (all 4 stages)
