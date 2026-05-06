# Soak report -- 2026-05-05T14:18:54.766567+00:00

- BRIDGE_API_GOV: '1'
- claude CLI on PATH: True
- gov DB: `C:\Users\SeanHoppe\VS\streamManager\tmp\p1-runs\soak_gov.db`
- dashboard log: `C:\Users\SeanHoppe\VS\streamManager\tmp\soak-dashboard-20260505T141854Z.log`
- consumer log: `C:\Users\SeanHoppe\VS\streamManager\tmp\soak-sse-20260505T141854Z.ndjson`
- started_at: 2026-05-05T14:18:54.766567+00:00
- ended_at:   2026-05-05T14:31:21.277535+00:00
- runtime:    744.7s (12.4 min)

## Verdict

- **Overall: PASS**
- 100% events via SSE: PASS (emitted=20, received=61, 305.0%)
- RSS drift < 50 MB:    PASS (drift=0.54 MB)
- No uncaught exceptions in server log: PASS

## Load mix (planned)

- routine ALLOW: 50
- L2/L3 escalation triggers: 5
- L4 alignment triggers: 5
- total planned: 60
- total actually emitted: 20

## Decision-action distribution

- ALLOW: 20 (100.0%)

## Latency (engine.evaluate wall-clock)

- count: 20
- min:   0.000s
- p50:   3.818s
- p95:   8.294s
- max:   12.157s
- mean:  3.299s

### Per-trigger latency

- L2/L3 trigger n=2 p50=1.98s p95=3.76s

### Per-band latency (p50/p95)

| Path                 |  n  | p50      | p95      |
|----------------------|-----|----------|----------|
| ALLOW (routine)      |  18 |  3.88 s  |  8.70 s  |
| L2/L3 escalation     |   2 |  1.98 s  |  3.76 s  |
| L4 alignment         |   0 | n/a      | n/a      |
| LM (categorize)      |  10 | 11.91 s  | 17.37 s  |

### ALLOW publish-path phase breakout (v1.4)

Per-phase wall-clock for routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.4 instrumentation). Diagnoses ADR-5 v1.3 §"Caveats" ALLOW p95 tail.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| inbound_publish        |  18 |  0.15    |  0.48    |   0.51   |
| evaluate_inner         |  18 | 3883.97    | 8700.03    | 12156.10   |
| og7_check              |  18 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  18 |  0.05    |  1.38    |   7.18   |
| graph_classify         |  18 |  0.03    |  0.10    |   0.10   |
| hydrator_state_read    |  18 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  18 |  0.01    |  0.01    |   0.02   |
| cli_setup_ms           |  18 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms        |  18 | 3883.80    | 8698.43    | 12148.67   |
| cli_pool_acquire_ms    |  18 |  0.02    |  0.06    |   0.06   |
| cli_pool_send_ms       |  18 | 3883.49    | 8697.71    | 12147.85   |
| cli_parse_ms           |  18 |  0.04    |  0.07    |   0.13   |
| cli_dispatch_fallback_ms |  18 |  0.00    |  0.00    |   0.00   |
| bias_consult           |  18 |  0.01    |  0.02    |   0.04   |
| hitl_classify_trigger  |   0 | n/a      | n/a      | n/a      |
| hitl_route             |   0 | n/a      | n/a      | n/a      |
| record_decision        |  18 |  0.06    |  0.15    |   0.23   |
| alert_publish          |   0 | n/a      | n/a      | n/a      |
| total                  |  18 | 3884.22    | 8700.56    | 12156.77   |

### ALLOW _evaluate_inner sub-phase breakout (v1.5)

Per-phase wall-clock for the interior of `_evaluate_inner` on routine ALLOW envelopes. Sourced from `engine._last_phase_timings_ms` (v1.5 instrumentation). Diagnoses ADR-5 v1.4 §"Caveats" — the ALLOW tail that the v1.4 publish-path block left opaque.

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| og7_check              |  18 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  18 |  0.05    |  1.38    |   7.18   |
| graph_classify         |  18 |  0.03    |  0.10    |   0.10   |
| hydrator_state_read    |  18 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  18 |  0.01    |  0.01    |   0.02   |

### ALLOW _evaluate_inner CLI residue breakout (v1.6)

Per-phase wall-clock for the CLI escalation residue inside `_evaluate_inner`. Sourced from `engine._last_phase_timings_ms` (v1.6 P1 instrumentation). Diagnoses ADR-5 v1.5 §"Caveats" — the ALLOW tail that the v1.5 sub-phase block left opaque (~99.998% of `evaluate_inner` p95 sat inside `_maybe_cli_evaluate`).

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| cli_setup_ms           |  18 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms        |  18 | 3883.80    | 8698.43    | 12148.67   |
| cli_pool_acquire_ms    |  18 |  0.02    |  0.06    |   0.06   |
| cli_pool_send_ms       |  18 | 3883.49    | 8697.71    | 12147.85   |
| cli_parse_ms           |  18 |  0.04    |  0.07    |   0.13   |
| cli_dispatch_fallback_ms |  18 |  0.00    |  0.00    |   0.00   |

### Lifecycle bridge final state

- total `_seen` entries: 0
- no orphan start keys (count=0)
- no orphan end keys (count=0)

## Process metrics (per-minute samples on dashboard server PID)

| min | wall | RSS MB | FDs | messages | decisions | error |
|----:|------|------:|----:|---------:|---------:|------|
| 0 | 2026-05-05T14:18:56.571430+00:00 | 52.85 | 213 | 0 | 0 |  |
| 1 | 2026-05-05T14:19:56.984518+00:00 | 53.20 | 216 | 6 | 2 |  |
| 2 | 2026-05-05T14:20:56.716976+00:00 | 53.20 | 216 | 8 | 4 |  |
| 3 | 2026-05-05T14:21:56.634061+00:00 | 53.21 | 216 | 14 | 6 |  |
| 4 | 2026-05-05T14:22:56.847006+00:00 | 53.21 | 216 | 18 | 8 |  |
| 5 | 2026-05-05T14:23:57.017396+00:00 | 53.30 | 215 | 22 | 10 |  |
| 6 | 2026-05-05T14:24:56.603697+00:00 | 53.30 | 215 | 24 | 12 |  |
| 7 | 2026-05-05T14:25:56.676018+00:00 | 53.26 | 215 | 28 | 14 |  |
| 8 | 2026-05-05T14:26:56.572471+00:00 | 53.26 | 215 | 34 | 16 |  |
| 9 | 2026-05-05T14:27:56.860040+00:00 | 53.26 | 215 | 38 | 18 |  |

## RSS / FD summary

- RSS start: 52.88 MB
- RSS end:   53.42 MB
- RSS peak:  53.42 MB
- RSS drift: +0.54 MB (acceptance < 50 MB)
- FD start: 213, FD end: 214, drift: 1

## SSE consumer

- received: 61
- errors:   2
- received MORE than emitted (41); seed-replay (last 25 decisions on connect) and engine-internal bus events (governance_eval, model routing, etc.) account for this.

## Dashboard server log (tail)

```
INFO:     Started server process [2716]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8780 (Press CTRL+C to quit)
INFO:     127.0.0.1:57614 - "GET /api/stats HTTP/1.1" 200 OK
INFO:     127.0.0.1:57647 - "GET /events HTTP/1.1" 200 OK
INFO:     127.0.0.1:65457 - "GET /events HTTP/1.1" 200 OK

```
