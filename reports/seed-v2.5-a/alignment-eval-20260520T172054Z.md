# alignment-eval report

- generated: 20260520T172054Z
- runs per row per model: 6
- control model: `claude-sonnet-4-6`
- candidate model: `claude-haiku-4-5-20251001`
- golden rows: 1

## Per-row results

| id | model_floor | expected | sonnet (runs) | sonnet maj | sonnet stable | haiku (runs) | haiku maj | haiku stable | agree (haiku==sonnet) |
|---|---|---|---|---|---|---|---|---|---|
| frog7-wirecli-module-10 | sonnet | SUGGEST | INTERVENE,GUIDE,INTERVENE,INTERVENE,INTERVENE,NONE | INTERVENE | **no** | SKIP,SKIP,SKIP,SKIP,SKIP,SKIP | SKIP | yes | **no** |

## Summary

- total: 1
- sonnet_stable_count: 0
- sonnet_pass: 0
- sonnet_pass_rate: 0.0
- haiku_stable_count: 0
- haiku_pass: 0
- haiku_pass_rate: 0.0
- haiku_regression_vs_sonnet: 0
- haiku_regression_frog7: 0
- unstable_sonnet: 1
- unstable_haiku: 0

## Per-model wall-clock distributions

| Model  | n  | p50    | p95    | p99    | max    |
|--------|----|--------|--------|--------|--------|
| sonnet | 6 | 22.891s | 24.613s | 24.960s | 25.047s |
| haiku  | n=0; (skipped) | — | — | — | — |

