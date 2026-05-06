# ALLOW publish-path phase probe — 2026-05-04T19:33:40.676719+00:00

- label: `probe`
- envelopes: 50
- runtime: 0.010 s
- gov DB:  `C:\Users\SeanHoppe\VS\streamManager\tmp\allow_probe_gov.db`
- started: 2026-05-04T19:33:40.676719+00:00
- ended:   2026-05-04T19:33:40.685471+00:00

## Overall wall-clock per evaluate()

- count: 50
- min:   0.085 ms
- p50:   0.114 ms
- p95:   0.222 ms
- max:   0.263 ms
- mean:  0.126 ms

### ALLOW publish-path phase breakout (v1.4)

Per-phase wall-clock for routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.4 instrumentation). Diagnoses ADR-5 v1.3 §"Caveats" ALLOW p95 tail.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| inbound_publish        |  50 |  0.04    |  0.08    |   0.14   |
| evaluate_inner         |  50 |  0.03    |  0.07    |   0.18   |
| og7_check              |  50 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  50 |  0.02    |  0.03    |   0.13   |
| graph_classify         |  50 |  0.00    |  0.01    |   0.04   |
| hydrator_state_read    |  50 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  50 |  0.00    |  0.00    |   0.00   |
| bias_consult           |  50 |  0.00    |  0.01    |   0.01   |
| hitl_classify_trigger  |   0 | n/a      | n/a      | n/a      |
| hitl_route             |   0 | n/a      | n/a      | n/a      |
| record_decision        |  50 |  0.03    |  0.06    |   0.10   |
| alert_publish          |   0 | n/a      | n/a      | n/a      |
| total                  |  50 |  0.11    |  0.22    |   0.26   |
