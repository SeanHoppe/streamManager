# ALLOW publish-path phase probe — 2026-05-04T23:20:50.412790+00:00

- label: `v16-residue`
- envelopes: 50
- runtime: 0.031 s
- gov DB:  `C:\Users\SeanHoppe\VS\streamManager\tmp\allow_probe_gov.db`
- started: 2026-05-04T23:20:50.412790+00:00
- ended:   2026-05-04T23:20:50.441967+00:00

## Overall wall-clock per evaluate()

- count: 50
- min:   0.248 ms
- p50:   0.321 ms
- p95:   0.871 ms
- max:   3.660 ms
- mean:  0.489 ms

### ALLOW publish-path phase breakout (v1.4)

Per-phase wall-clock for routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.4 instrumentation). Diagnoses ADR-5 v1.3 §"Caveats" ALLOW p95 tail.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| inbound_publish        |  50 |  0.11    |  0.23    |   2.73   |
| evaluate_inner         |  50 |  0.06    |  0.56    |   1.08   |
| og7_check              |  50 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  50 |  0.04    |  0.10    |   0.32   |
| graph_classify         |  50 |  0.00    |  0.04    |   0.08   |
| hydrator_state_read    |  50 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  50 |  0.00    |  0.01    |   0.03   |
| cli_setup_ms           |  50 |  0.00    |  0.00    |   0.01   |
| cli_dispatch_ms        |  50 |  0.00    |  0.41    |   0.60   |
| cli_pool_acquire_ms    |  50 |  0.00    |  0.00    |   0.00   |
| cli_pool_send_ms       |  50 |  0.00    |  0.02    |   0.03   |
| cli_parse_ms           |  50 |  0.00    |  0.22    |   0.38   |
| bias_consult           |  50 |  0.01    |  0.02    |   0.04   |
| hitl_classify_trigger  |   0 | n/a      | n/a      | n/a      |
| hitl_route             |   0 | n/a      | n/a      | n/a      |
| record_decision        |  50 |  0.08    |  0.17    |   0.55   |
| alert_publish          |   0 | n/a      | n/a      | n/a      |
| total                  |  50 |  0.32    |  0.87    |   3.65   |

### ALLOW _evaluate_inner sub-phase breakout (v1.5)

Per-phase wall-clock for the interior of `_evaluate_inner` on routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.5 instrumentation). Diagnoses ADR-5 v1.4 §"Caveats" — the ALLOW tail that the v1.4 publish-path block left opaque.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| og7_check              |  50 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  50 |  0.04    |  0.10    |   0.32   |
| graph_classify         |  50 |  0.00    |  0.04    |   0.08   |
| hydrator_state_read    |  50 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  50 |  0.00    |  0.01    |   0.03   |

### ALLOW _evaluate_inner CLI residue breakout (v1.6)

Per-phase wall-clock for the CLI escalation residue inside `_evaluate_inner`. Sourced from `engine._last_phase_timings_ms` (v1.6 P1 instrumentation). Diagnoses ADR-5 v1.5 §"Caveats" — the ALLOW tail that the v1.5 sub-phase block left opaque (~99.998% of `evaluate_inner` p95 sat inside `_maybe_cli_evaluate`).

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| cli_setup_ms           |  50 |  0.00    |  0.00    |   0.01   |
| cli_dispatch_ms        |  50 |  0.00    |  0.41    |   0.60   |
| cli_pool_acquire_ms    |  50 |  0.00    |  0.00    |   0.00   |
| cli_pool_send_ms       |  50 |  0.00    |  0.02    |   0.03   |
| cli_parse_ms           |  50 |  0.00    |  0.22    |   0.38   |
