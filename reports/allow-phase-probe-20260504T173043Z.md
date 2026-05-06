# ALLOW publish-path phase probe — 2026-05-04T17:30:43.601716+00:00

- label: `probe`
- envelopes: 200
- runtime: 0.030 s
- gov DB:  `C:\Users\SeanHoppe\VS\streamManager\tmp\allow_probe_gov.db`
- started: 2026-05-04T17:30:43.601716+00:00
- ended:   2026-05-04T17:30:43.624773+00:00

## Overall wall-clock per evaluate()

- count: 200
- min:   0.071 ms
- p50:   0.098 ms
- p95:   0.155 ms
- max:   5.656 ms
- mean:  0.133 ms

### ALLOW publish-path phase breakout (v1.4)

Per-phase wall-clock for routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.4 instrumentation). Diagnoses ADR-5 v1.3 §"Caveats" ALLOW p95 tail.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| inbound_publish        | 200 |  0.03    |  0.07    |   0.45   |
| evaluate_inner         | 200 |  0.03    |  0.04    |   0.17   |
| bias_consult           | 200 |  0.00    |  0.00    |   0.07   |
| hitl_classify_trigger  |   0 | n/a      | n/a      | n/a      |
| hitl_route             |   0 | n/a      | n/a      | n/a      |
| record_decision        | 200 |  0.03    |  0.05    |   5.57   |
| alert_publish          |   0 | n/a      | n/a      | n/a      |
| total                  | 200 |  0.10    |  0.15    |   5.65   |
