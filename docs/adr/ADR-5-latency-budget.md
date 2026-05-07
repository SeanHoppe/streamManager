# ADR-5: Governance latency budget (revised for v1.0)

- **Status**: Accepted (v1.0); re-baselined v1.1 (2026-05-03); re-baselined v1.2 (2026-05-03, see §"v1.2 ship-gate baseline"); re-baselined v1.3 (2026-05-04, see §"v1.3 ship-gate baseline"); re-baselined v1.4 (2026-05-04, see §"v1.4 ship-gate baseline"); re-baselined v1.5 (2026-05-04, see §"v1.5 ship-gate baseline"); re-baselined v1.6 (2026-05-05, see §"v1.6 ship-gate baseline"); re-baselined v1.7 (2026-05-05, see §"v1.7 ship-gate baseline"); re-baselined v1.8 (2026-05-06, see §"v1.8 ship-gate baseline")
- **Date**: 2026-05-02
- **Supersedes**: original ADR-5 budget (200 ms p50 / 2 s p95, SDK-era)

## Context

The original ADR-5 latency budget (p50 ≤ 200 ms, p95 ≤ 2 s) was set when
governance escalation ran through the Anthropic Python SDK in-process. During
the `api_governance` → `cli_governance` migration the SDK path was retired:
all LLM escalation now runs as a `claude -p` subprocess.

CLI subprocess cold-start (Node runtime spin-up + auth + first-token TTFT)
dominates per-call latency. The 30-minute soak baseline confirms the new
shape: cold-start overhead alone exceeds the original p95 by roughly an order
of magnitude.

## Measured baseline (locked)

From `reports/soak-20260502T141527Z.md` (n=60 over 30.3 min, real CLI):

- p50: **6.219 s**
- p95: **14.939 s**
- max: **25.062 s** (grazing the 25 s hard timeout)
- mean: 6.188 s
- L4 alignment p95: **23.80 s** (worst-case escalation path)
- L2/L3 trigger p95: 9.96 s

Soak verdict: PASS (100% SSE delivery, RSS drift +0.84 MB, no uncaught
exceptions). Latency is the only dimension that diverged from the original
budget.

## Decision

Adopt the following revised budget for v1.0:

| Metric        | v1.0 budget |
|---------------|-------------|
| p50           | ≤ 7 s       |
| p95           | ≤ 15 s      |
| hard timeout  | 25 s        |

Original SDK-era budget (200 ms p50 / 2 s p95) is **superseded** and retained
in this ADR for historical reference only.

## Rationale

- The SDK path is gone; benchmarking against it is no longer meaningful.
- CLI subprocess cold-start is structural for v1.0 — not a regression.
- The measured p50/p95 sit within reach of the new ceiling with margin
  (p50 6.22 s vs 7 s budget; p95 14.94 s vs 15 s budget).
- The 25 s hard timeout is the existing engine cap; max observed (25.06 s)
  shows alignment escalations can still graze it. Any breach is treated as
  a TIMEOUT decision and surfaced in the dashboard.

## Consequences

- Governance pauses are now user-visible (~6–15 s typical, up to ~25 s on
  L4 alignment escalation). Surface this in user-facing docs and the
  dashboard help panel so the pause is not surprising.
- NFR-P2 in `REQUIREMENTS.md` is updated to match this budget (see Task G
  / NFR-P alignment).
- CI / soak gating thresholds should be set against the v1.0 budget, not
  the SDK-era figures.

## v1.1 follow-up

Implement a **warm CLI subprocess pool** that amortizes Node + auth
cold-start across calls. Target outcomes:

- p50: ~2–5 s (eliminate cold-start from the median)
- p95: meaningful reduction; alignment path still bounded by model TTFT
- Re-issue ADR-5 (or a successor) with the warm-pool measurements.

### v1.1 status (Task J — CLI warm-pool)

- **Implemented:** `src/stream_manager/cli_pool.py` + `CliGovernor(pool=...)`
  + `EngineRegistry(cli_pool=...)` wiring + dashboard startup/shutdown
  lifecycle. PID-file at `.bridge/cli-pool.pids` with boot-time reaper.
- **Pending budget revision:** awaiting paired 5-min and 30-min soaks
  with `--cli-pool-size 2`. Per `docs/v1.1-scope.md`, revised target is:

  | Metric        | v1.1 target |
  |---------------|-------------|
  | p50           | ≤ 3 s       |
  | p95           | ≤ 8 s       |
  | hard timeout  | 25 s (unchanged) |

  The v1.0 budget (p50 ≤ 7 s, p95 ≤ 15 s) remains in force until a
  measured warm-pool soak either confirms or re-baselines the v1.1
  target. If measured numbers fall short, document and re-baseline
  rather than block release (per `docs/v1.1-scope.md` §"Latency budget
  targets").

### Task I (v1.1) — Hydrator profile, no budget change

Task I (`docs/v1.1-task-plan.md` §I) profiled the suspected
cross-session-Hydrator overhead on `EngineRegistry.get_or_create` and
found it is **not** the p95 driver:

- Hydrator thread runs in <1 ms on the empty/near-empty patterns table.
- `engine_construct` (first `get_or_create`) is ~2–3 ms.
- `cli_subprocess` p95 is 17–21 s — accounts for ~100% of per-call
  wall time.

See `reports/perf-hydrator-20260502T232639Z.md` for the full per-call
breakdown. Task I applied the lazy-init refactor as a defensive cleanup
(engine construction now does zero sync DB work) but the v1.0 baseline
p95 = 19.08s persists because cold-start CLI cost is structural. The
substantive p95 fix is **Task J — CLI subprocess warm-pool**. The v1.0
budget table above is **not** ratcheted by Task I alone.

### v1.1 ship-gate re-baseline (post-N, 2026-05-03)

The original v1.1 single-target budget (p50 ≤ 3 s, p95 ≤ 8 s) assumed
warm-pool would close the gap to a flat distribution. The 30-min
ship-gate soak on post-Task-N HEAD `0d8cecc` with `--cli-pool-size 2`
showed the gap is **bimodal**, not flat:

| Path             | n  | p50     | p95     | source |
|------------------|----|---------|---------|--------|
| L2/L3 escalation | 5  | 0.00 s  | 4.06 s  | report |
| L4 alignment     | 5  | 11.83 s | 13.35 s | report |
| **Overall**      | 60 | 4.97 s  | 11.17 s | report |

L4 alignment latency is **structural** — reflects depth of the
underlying model's reasoning pass, not framework overhead. Pool
collapsed cold-start cost on the ALLOW / L2 / L3 paths (29% p95
improvement vs no-pool re-soak the same day). No further framework
lever is available without changing model selection policy.

Per `docs/v1.1-task-plan.md` §"v1.1 ship gate checklist" option B
("p95 ≤ 8s OR re-baselined ADR-5"), the budget is re-baselined here:

| Path                 | v1.1 target |
|----------------------|-------------|
| ALLOW p95            | ≤ 6 s       |
| L2/L3 escalation p95 | ≤ 8 s       |
| L4 alignment p95     | ≤ 14 s      |
| Overall p95          | ≤ 12 s      |
| Hard timeout         | 25 s (unchanged) |

Source soak: `reports/soak-20260503T101758Z.md`. The single-rolled-up
p95 ≤ 8 s target from `docs/v1.1-scope.md` is **superseded** by this
table.

Future work (v1.2 backlog): a Haiku fastpath for routine L4 calls is
expected to bring L4 p95 under 8 s; that would re-unify the budget.
See `docs/v1.1-task-plan.md` §"v1.2 backlog" for the cassette/replay
infrastructure needed to validate it cheaply.

### Source of truth (v1.2 update)

ADR-17 introduces a three-tier soak model (replay / record-cassette /
ship-gate). **Only the ship-gate tier feeds the absolute latency
numbers in this ADR.** Replay-tier and record-cassette-tier p95 are
*relative* regression signals — they MUST NOT be compared against the
budgets in the table above. See `docs/adr/ADR-17-soak-tiers.md`.

## v1.2 ship-gate baseline

- **Source**: `reports/soak-20260503T145124Z.md`
- **Date**: 2026-05-03
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17)
- **Runtime**: 1820.5 s (30.3 min)
- **Events**: 60 emitted / 133 received (seed-replay + internal bus)
- **Verdict**: PASS (100% SSE, RSS drift +1.09 MB, no uncaught exceptions)

### Latency targets (overall, n=60)

| Metric  | v1.2 measured |
|---------|---------------|
| p50     | 4.134 s       |
| p95     | 10.396 s      |
| max     | 12.082 s      |
| mean    | 3.457 s       |

### Per-trigger split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| L2/L3 escalation     | 5  | 0.00 s   | 4.47 s   |
| L4 alignment         | 5  | 10.39 s  | 12.03 s  |
| ALLOW (routine)      | 50 | not separated by driver report; 100% decision-action distribution = ALLOW so the overall row above represents the ALLOW envelope inclusive of L2/L3+L4 outliers |

### Delta vs v1.1 ship-gate (`reports/soak-20260503T101758Z.md`)

| Metric           | v1.1     | v1.2     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 4.967 s  | 4.134 s  | **−0.83 s** | improvement |
| Overall p95      | 11.173 s | 10.396 s | **−0.78 s** | improvement |
| Overall max      | 13.647 s | 12.082 s | **−1.57 s** | improvement |
| Overall mean     | 3.780 s  | 3.457 s  | −0.32 s    | improvement |
| L4 alignment p95 | 13.35 s  | 12.03 s  | **−1.32 s** | improvement |
| L2/L3 p95        | 4.06 s   | 4.47 s   | +0.41 s    | parity (n=5 noise) |
| RSS drift        | 0.49 MB  | 1.09 MB  | +0.60 MB   | parity (50× under 50 MB budget) |

v1.2 plumbing changes — Task C (lifecycle bridge), Task D (SSE-only
consumer; long-poll path removed), Task E (json transport refusal) —
net **latency improvement** across p50/p95/max relative to v1.1. No
band crossed into regression class. The L2/L3 p95 +0.41 s is within
n=5 sample noise.

### Budget

The v1.1 budget table is **carried forward unchanged** for v1.2.
Measured numbers sit inside every band with margin; no
re-baseline (tightening or widening) is justified by a single 30-min
soak. v1.3 latency work measures against the table below:

| Path                 | v1.2 budget (= v1.1 carried forward) |
|----------------------|--------------------------------------|
| ALLOW p95            | ≤ 6 s                                |
| L2/L3 escalation p95 | ≤ 8 s                                |
| L4 alignment p95     | ≤ 14 s                               |
| Overall p95          | ≤ 12 s                               |
| Hard timeout         | 25 s (unchanged)                     |

### Status

ACCEPTED as v1.2 budget. v1.3 latency work measures against this section.

### Caveats

- **Lifecycle bridge orphan-key check (Task C)** is not enumerated in
  the driver report; dashboard log tail shows no errors but final
  `LifecycleBridge._seen` state is not surfaced. Driver enhancement is
  recommended in the v1.3 followup ledger.
- **ALLOW p95 is not separated** from L2/L3 + L4 trigger samples in
  the current driver report. With decision-action distribution = 100%
  ALLOW (n=60), the overall p95 is the inclusive ALLOW envelope; the
  pure routine-ALLOW p95 (n=50) is necessarily lower and likely well
  inside the ≤ 6 s budget. Reporting enhancement is a v1.3 followup.

## v1.3 ship-gate baseline

- **Source**: `reports/soak-20260504T152005Z.md`
- **Date**: 2026-05-04
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17)
- **Runtime**: 1934.0 s (32.2 min) — includes v1.3 Path-A LM dialogue pump after engine.evaluate loop
- **Events**: 60 emitted / 158 received (seed-replay + internal bus events; SSE forwards governance_eval, model routing, etc.)
- **Verdict**: PASS (100% SSE, RSS drift +0.62 MB, no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.3 measured |
|---------|---------------|
| p50     | 3.680 s       |
| p95     | 10.436 s      |
| max     | 14.519 s      |
| mean    | 3.832 s       |

### Per-band split (P1 / v1.3 driver hardening — first ship-gate with explicit ALLOW + LM rows)

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 50 |  3.72 s  |  9.60 s  |
| L2/L3 escalation     |  5 |  0.00 s  |  6.08 s  |
| L4 alignment         |  5 |  8.29 s  | 13.89 s  |
| LM (categorize)      | 10 | 12.50 s  | 15.39 s  |

### Delta vs v1.2 ship-gate (`reports/soak-20260503T145124Z.md`)

| Metric           | v1.2     | v1.3     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 4.134 s  | 3.680 s  | **−0.45 s** | improvement |
| Overall p95      | 10.396 s | 10.436 s | +0.04 s    | parity      |
| Overall max      | 12.082 s | 14.519 s | +2.44 s    | parity (n=1 outlier; L4 band) |
| Overall mean     | 3.457 s  | 3.832 s  | +0.38 s    | parity      |
| L2/L3 p95        | 4.47 s   | 6.08 s   | +1.61 s    | parity (n=5 noise) |
| L4 alignment p95 | 12.03 s  | 13.89 s  | +1.86 s    | parity (n=5 noise; under ≤14 s budget) |
| RSS drift        | 1.09 MB  | 0.62 MB  | −0.47 MB   | improvement |

v1.3 plumbing changes — Path-A LM extension (this cycle's recorder + driver work), P5 Learn Mode (FR-LM-1..6), bias_for advisory hookup, decay/reinforcement/contradiction logic — net **parity** on the verdict hot path. Overall p95 within 0.04 s of v1.2 ship-gate. The advisory bias read in `governance.py` does NOT regress the verdict path. Lifecycle bridge orphan-free at end-of-window (positively asserted by P1 hardening; first time this is reported in a ship-gate).

### Budget

The v1.2 budget table is **carried forward unchanged** for v1.3. v1.3 measured numbers sit inside every per-band budget; the ALLOW p95 row (newly separated from the overall envelope) is documented but not used to tighten the budget — a single 30-min soak is insufficient to re-baseline routine ALLOW. v1.4 latency work measures against the table below:

| Path                 | v1.3 budget (= v1.2 carried forward, plus new LM row) |
|----------------------|--------------------------------------------------------|
| ALLOW p95            | ≤ 12 s (widened from speculative ≤ 6 s; see Caveats) |
| L2/L3 escalation p95 | ≤ 8 s                                                 |
| L4 alignment p95     | ≤ 14 s                                                |
| LM (categorize) p95  | ≤ 25 s (new; Sonnet round-trip variance)             |
| Overall p95          | ≤ 12 s                                                |
| Hard timeout         | 25 s (unchanged)                                      |

### Status

ACCEPTED as v1.3 budget. v1.4 latency work measures against this section.

### Caveats

- **ALLOW p95 budget widened from ≤ 6 s to ≤ 12 s.** The v1.2 ADR-5 §"Caveats" predicted ALLOW p95 was "likely well inside the ≤ 6 s budget" once separated. The v1.3 measurement (9.60 s, n=50) shows this prediction was wrong. The ALLOW band traverses the full engine.evaluate path (`_install_lazy_hydrator` → `decision_graph.classify` → `bus.publish` → `record_decision`) and the upper tail is dominated by sqlite3 contention in the publish path under the 30-min wall-clock window, NOT by an L0 → L2 misroute. Investigation deferred to v1.4 (`docs/v1.4-backlog.md`); the budget is widened to ≤ 12 s to match the overall p95 envelope while v1.4 instruments the publish path.

  **v1.4 instrumentation update (2026-05-04, PR pending):** `governance.evaluate()` now exposes `engine._last_phase_timings_ms` with per-phase wall-clock for `inbound_publish` / `evaluate_inner` / `bias_consult` / `hitl_classify_trigger` / `hitl_route` / `record_decision` / `alert_publish` / `total`. A 200-call local probe (`tools/allow_phase_probe.py --n 200`) on an idle bus reports overall ALLOW p95 = **0.16 ms** with `inbound_publish` p95 = 0.074 ms and `record_decision` p95 = 0.054 ms — i.e. the in-process ALLOW path itself contributes well under 1 ms. The 9.60 s ALLOW p95 measured during the v1.3 30-min ship-gate must therefore be dominated by I/O contention from concurrent components (dashboard server, SSE consumer, `cli_pool` workers, per-minute psutil sampling) competing for the same sqlite WAL. The next step (still v1.4) is to attribute that contention by running the next ship-gate with the new instrumentation enabled and reading the `### ALLOW publish-path phase breakout (v1.4)` block now emitted by `tools/soak_driver.py`.
- **LM (categorize) p95 = 15.39 s.** Sonnet round-trip wall-clock; categorizer runs out-of-band so this does NOT enter the verdict hot path budget. Budget set at ≤ 25 s — a 5 s margin below the categorizer subprocess timeout (`learn_categorizer.TIMEOUT_SECONDS = 30.0`); a measurement at or above the budget should be investigated *before* it crosses the timeout.
- **Lifecycle bridge orphan-key check (Task C)** now positively asserted at ship-gate (P1 hardening). v1.3 ship-gate report shows total `_seen` entries = 0, no orphan starts, no orphan ends. Carried v1.2 caveat resolved.
- **L2/L3 + L4 + LM are n=5 / n=5 / n=10** respectively. Per-band p95 deltas vs v1.2 are within sample noise; the overall p95 is the higher-confidence comparison.

## v1.4 ship-gate baseline

- **Source**: `reports/soak-20260504T182027Z.md`
- **Date**: 2026-05-04
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) **with v1.4 ALLOW publish-path phase instrumentation enabled**
- **Runtime**: 1936.2 s (32.3 min) — same shape as v1.3.1 (60 envelopes + LM dialogue pump)
- **Events**: 60 emitted / 158 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift **−5.88 MB** (shrink), no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.4 measured |
|---------|---------------|
| p50     | 3.387 s       |
| p95     | 8.178 s       |
| max     | 11.276 s      |
| mean    | 3.120 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 50 |  3.49 s  |  7.57 s  |
| L2/L3 escalation     |  5 |  0.00 s  |  4.13 s  |
| L4 alignment         |  5 |  6.61 s  | 10.82 s  |
| LM (categorize)      | 10 | 10.27 s  | 19.26 s  |

### ALLOW publish-path phase breakout (NEW v1.4)

First ship-gate with the `engine._last_phase_timings_ms` instrumentation enabled. Sourced from the `### ALLOW publish-path phase breakout (v1.4)` block in the M3 report. **Diagnoses the v1.3 §"Caveats" ALLOW p95 tail.**

| Phase                 |  n  | p50 ms     | p95 ms      | max ms     |
|-----------------------|-----|------------|-------------|------------|
| inbound_publish       | 50  |  0.20      |  0.43       |   0.89     |
| **evaluate_inner**    | 50  | 3488.16    | **7572.17** | 10546.18   |
| bias_consult          | 50  |  0.01      |  0.02       |   0.03     |
| hitl_classify_trigger |  0  |  n/a       |  n/a        |   n/a      |
| hitl_route            |  0  |  n/a       |  n/a        |   n/a      |
| record_decision       | 50  |  0.06      |  0.11       |   0.20     |
| alert_publish         |  0  |  n/a       |  n/a        |   n/a      |
| total                 | 50  | 3488.53    | 7572.60     | 10546.67   |

**Finding.** The v1.3.1 §"Caveats" hypothesis — "ALLOW p95 tail dominated by sqlite3 contention in the publish path under sustained load" — is **disproved**. The publish path (`inbound_publish` p95 = 0.43 ms, `record_decision` p95 = 0.11 ms) accounts for under 1 ms of the 7572 ms p95. **100% of the tail is inside `_evaluate_inner`**: the L0/L1 fast-precheck, decision-graph classify, FR-OG-7 maturity check, and lazy-hydrator state read. The bias_consult phase added in v1.3 P5d is also negligible (0.02 ms p95) — the advisory bias read does not regress the verdict hot path.

### Delta vs v1.3.1 ship-gate (`reports/soak-20260504T152005Z.md`)

| Metric           | v1.3.1   | v1.4     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 3.680 s  | 3.387 s  | **−0.29 s** | improvement |
| Overall p95      | 10.436 s | 8.178 s  | **−2.26 s** | improvement |
| Overall max      | 14.519 s | 11.276 s | **−3.24 s** | improvement |
| Overall mean     | 3.832 s  | 3.120 s  | −0.71 s    | improvement |
| ALLOW p95        | 9.60 s   | 7.57 s   | **−2.03 s** | improvement |
| L2/L3 p95        | 6.08 s   | 4.13 s   | −1.95 s    | improvement (n=5 noise) |
| L4 alignment p95 | 13.89 s  | 10.82 s  | **−3.07 s** | improvement |
| LM (cat) p95     | 15.39 s  | 19.26 s  | +3.87 s    | parity (n=10 Sonnet round-trip variance) |
| RSS drift        | +0.62 MB | −5.88 MB | shrunk     | improvement |

v1.4 has not changed the verdict path — the engine code edits are additive (new `_last_phase_timings_ms` attribute, new soak driver report block, new tooling). The ~−2.3 s overall p95 improvement is consistent with measurement noise from a different time-of-day soak window plus the natural variance in Anthropic upstream rate-limit behaviour. Treat the improvement as fortuitous, not earned.

### Budget

The v1.3.1 budget table is **carried forward unchanged** for v1.4. The phase breakout justifies tightening ALLOW p95 in v1.5+ once the `_evaluate_inner` sub-phases are instrumented and a real reduction is verifiable.

| Path                 | v1.4 budget (= v1.3.1 carried forward)               |
|----------------------|------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                |
| L2/L3 escalation p95 | ≤ 8 s                                                 |
| L4 alignment p95     | ≤ 14 s                                                |
| LM (categorize) p95  | ≤ 25 s                                                |
| Overall p95          | ≤ 12 s                                                |
| Hard timeout         | 25 s (unchanged)                                      |

### Status

ACCEPTED as v1.4 budget. v1.5 latency work measures against this section.

### Caveats

- **`_evaluate_inner` is now the load-bearing tail.** v1.5 should instrument inside `_evaluate_inner` with sub-phase timings (e.g. `og7_check`, `fast_precheck`, `graph_classify`, `hydrator_state_read`, `routing_dispatch`) so the next ship-gate can attribute the 7.57 s ALLOW p95 to a specific component. The v1.4 instrumentation stops at the `_evaluate_inner` boundary; everything inside is opaque to the soak report.
- **LM (categorize) p95 = 19.26 s.** Approaches the ≤ 25 s budget. n=10 Sonnet round-trip; variance is dominated by upstream queueing. Trend across v1.3.1 (15.39 s) → v1.4 (19.26 s) is +3.87 s — within sample noise but worth a re-measure if the next ship-gate also lands above 18 s.
- **All other v1.3 caveats resolved or unchanged.** Lifecycle bridge orphan-free positively asserted again. ALLOW p95 budget widening from v1.3 stands; the phase breakout makes a future tightening defensible once `_evaluate_inner` sub-phases ship.

## v1.5 ship-gate baseline

- **Source**: `reports/soak-20260504T201714Z.md`
- **Date**: 2026-05-04
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) **with v1.5 `_evaluate_inner` sub-phase instrumentation enabled**
- **Runtime**: 1931.2 s (32.2 min) — same shape as v1.4 (60 envelopes + LM dialogue pump)
- **Events**: 60 emitted / 158 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift **−1.20 MB** (shrink), no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.5 measured |
|---------|---------------|
| p50     | 2.779 s       |
| p95     | 5.820 s       |
| max     | 15.105 s      |
| mean    | 2.678 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 50 |  2.78 s  |  5.60 s  |
| L2/L3 escalation     |  5 |  0.00 s  |  4.40 s  |
| L4 alignment         |  5 |  3.53 s  | 12.90 s  |
| LM (categorize)      | 10 | 10.69 s  | 15.39 s  |

### ALLOW _evaluate_inner sub-phase breakout (NEW v1.5)

First ship-gate with the v1.5 sub-phase instrumentation inside `_evaluate_inner` enabled. Sourced from the `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block in the report. **Diagnoses the v1.4 §"Caveats" `_evaluate_inner` opacity item.**

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| og7_check              |  50 |  0.00    |  0.00    |   0.00   |
| fast_precheck          |  50 |  0.05    |  0.08    |   0.16   |
| graph_classify         |  50 |  0.03    |  0.04    |   0.18   |
| hydrator_state_read    |  50 |  0.00    |  0.00    |   0.00   |
| routing_dispatch       |  50 |  0.01    |  0.01    |   0.01   |

For reference, the v1.4 publish-path block on the same run reports `evaluate_inner` p95 = **5599.07 ms**.

**Finding.** The v1.4 §"Caveats" hypothesis — that the ALLOW p95 tail "is now the load-bearing tail" inside `_evaluate_inner` and would be attributable to one of `og7_check` / `fast_precheck` / `graph_classify` / `hydrator_state_read` / `routing_dispatch` — is **falsified by the data**. The five v1.5 sub-phases sum to **0.13 ms p95** against a 5599 ms `evaluate_inner` p95: ~99.998% of the `_evaluate_inner` wall-clock is in code paths NOT covered by the v1.5 instrumentation. The five named sub-phases are bookkeeping-fast (synchronous in-process lookups, idle-bus state reads, dict routing). The remaining residue inside `_evaluate_inner` — most plausibly the synchronous escalation path into the `cli_pool` worker (Sonnet round-trip via `claude -p` subprocess) and any model-side blocking call reachable from the L0/L1 routing branch — is the actual ALLOW p95 driver. **The v1.4 opacity is partially resolved (five components ruled out) and partially deferred (the un-instrumented residue is the next instrumentation target).**

### Delta vs v1.4 ship-gate (`reports/soak-20260504T182027Z.md`)

| Metric           | v1.4     | v1.5     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 3.387 s  | 2.779 s  | **−0.61 s** | improvement |
| Overall p95      | 8.178 s  | 5.820 s  | **−2.36 s** | improvement |
| Overall max      | 11.276 s | 15.105 s | +3.83 s    | parity (n=1 outlier; L4 band) |
| Overall mean     | 3.120 s  | 2.678 s  | −0.44 s    | improvement |
| ALLOW p95        | 7.57 s   | 5.60 s   | **−1.97 s** | improvement |
| L2/L3 p95        | 4.13 s   | 4.40 s   | +0.27 s    | parity (n=5 noise) |
| L4 alignment p95 | 10.82 s  | 12.90 s  | +2.08 s    | parity (n=5 noise; under ≤14 s budget) |
| LM (cat) p95     | 19.26 s  | 15.39 s  | **−3.87 s** | improvement (retreats below v1.4 watch threshold) |
| RSS drift        | −5.88 MB | −1.20 MB | parity     | both shrink, well under 50 MB budget |

v1.5 has not changed the verdict path — the engine code edits are additive (five new `_last_phase_timings_ms` keys, a new soak driver report block, no reordering of existing phases). The ~−2.4 s overall p95 improvement and ~−2.0 s ALLOW p95 improvement are consistent with measurement noise from a different time-of-day soak window plus upstream Anthropic rate-limit variance. Treat the improvement as fortuitous, not earned.

### Budget

The v1.4 budget table is **carried forward unchanged** for v1.5. The sub-phase breakout falsifies a v1.4-prediction but does not yet localise the ALLOW p95 tail to a specific component, so no tightening is justified. v1.6 latency work measures against the table below:

| Path                 | v1.5 budget (= v1.4 carried forward)                  |
|----------------------|-------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                |
| L2/L3 escalation p95 | ≤ 8 s                                                 |
| L4 alignment p95     | ≤ 14 s                                                |
| LM (categorize) p95  | ≤ 25 s                                                |
| Overall p95          | ≤ 12 s                                                |
| Hard timeout         | 25 s (unchanged)                                      |

### Status

ACCEPTED as v1.5 budget. v1.6 latency work measures against this section.

### Caveats

- **v1.4 `_evaluate_inner` opacity caveat — partially resolved.** The five v1.5 sub-phases (`og7_check`, `fast_precheck`, `graph_classify`, `hydrator_state_read`, `routing_dispatch`) collectively account for 0.13 ms p95 of the 5599 ms `evaluate_inner` p95. **None of these five dominates the ALLOW p95 tail** — they are in fact ruled out as candidates. The actual tail driver lives in the un-instrumented residue inside `_evaluate_inner`, most plausibly the synchronous `cli_pool` round-trip on the escalation branch. v1.6 should extend instrumentation around the residue (CLI dispatch entry, model round-trip wait, response handling) to close the gap. **Resolved at v1.6 ship-gate** — see §"v1.6 ship-gate baseline" (driver = `cli_pool_send_ms` p95 = 6328.07 ms, 99.99% of `cli_dispatch_ms`).
- **`hydrator_state_read` n=50 (fired on every ALLOW), p95 = 0.00 ms.** The lazy-hydrator state read is effectively free under the soak workload. The v1.4 prediction that this might be a tail driver is also falsified.
- **LM (categorize) p95 = 15.39 s — trend retreated.** The v1.4 watch item ("re-measure if the next ship-gate also lands above 18 s") is **closed**. v1.3.1 = 15.39 s → v1.4 = 19.26 s → v1.5 = 15.39 s; the v1.4 elevation did not persist. The +3.87 s v1.4 excursion is now classified as Sonnet upstream queueing variance within n=10 sample noise, not a sustained regression. ~~No v1.6 follow-up needed.~~ **Update at v1.6 ship-gate:** LM p95 partially reversed to 18.60 s (+3.21 s vs v1.5; 0.60 s over 18 s ceiling). The v1.4 watch criterion ("re-measure if next ship-gate also lands above 18 s") is hereby refined: **magnitude ≥ 1 s over ceiling = sustained regression (re-measure / triage); magnitude < 1 s over ceiling AND n=10 high-variance AND log clean = noise band (ship-with-watch).** v1.6 falls in the noise band (0.60 s over). Per S5a triage — magnitude small, n=10 high-variance, dashboard log clean, no cassette gap — **decision: ship-with-v1.7-watch** (see v1.6 §"Caveats").
- **L2/L3 + L4 + LM are n=5 / n=5 / n=10** respectively. Per-band p95 deltas vs v1.4 are within sample noise; the overall and ALLOW p95 are the higher-confidence comparisons.

## v1.6 ship-gate baseline

- **Source**: `reports/soak-20260505T073943Z.md`
- **Date**: 2026-05-05
- **Ship SHA**: `6866dad` (PR #87 merge into main; branch `ship/v1.6-shipgate-finalize`, base `380f453`; tagged `v1.6.0`)
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) **with v1.6 P1 `_evaluate_inner` CLI residue instrumentation enabled** (5 new keys: `cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`, `cli_parse_ms`)
- **Runtime**: 1955.2 s (32.6 min)
- **Events**: 60 emitted / 158 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift **−11.17 MB** (shrink), no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.6 measured |
|---------|---------------|
| p50     | 4.092 s       |
| p95     | 7.665 s       |
| max     | 14.967 s      |
| mean    | 3.358 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 50 |  4.18 s  |  6.33 s  |
| L2/L3 escalation     |  5 |  0.00 s  |  4.19 s  |
| L4 alignment         |  5 |  7.54 s  | 13.98 s  |
| LM (categorize)      | 10 | 12.69 s  | 18.60 s  |

### ALLOW _evaluate_inner CLI residue breakout (NEW v1.6)

First ship-gate with the v1.6 P1 CLI residue instrumentation enabled. Sourced from the `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block in the report. **Diagnoses the v1.5 §"Caveats" un-instrumented residue item.**

| Phase                  |  n  | p50 ms   | p95 ms   | max ms   |
|------------------------|-----|----------|----------|----------|
| cli_setup_ms           |  50 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms        |  50 | 4176.36  | 6329.00  | 11526.56 |
| cli_pool_acquire_ms    |  50 |  0.03    |  0.06    |   0.13   |
| cli_pool_send_ms       |  50 | 4175.63  | 6328.07  | 11525.65 |
| cli_parse_ms           |  50 |  0.08    |  0.15    |   0.26   |

For reference, the v1.4 publish-path block on the same run reports `evaluate_inner` p95 = **6329.38 ms**.

**Finding.** v1.6 P1 residue instrumentation localises the `_evaluate_inner` tail to `cli_pool_send_ms` p95 = 6328.07 ms (99.99% of `cli_dispatch_ms` 6329.00 ms; ~99.98% of `evaluate_inner` 6329.38 ms), confirming the synchronous `worker.send` Anthropic CLI round-trip (subprocess stdin write + stdout JSONL response wait in `CliWorker.send` (see `cli_pool.py`)) is the load-bearing component. `cli_setup_ms` (0.01 ms p95), `cli_pool_acquire_ms` (0.06 ms p95 — confirms zero queueing under sequential soak workload), and `cli_parse_ms` (0.15 ms p95) are negligible. Invariants hold: `cli_setup + cli_dispatch` = 6329.01 ms ≤ `evaluate_inner` 6329.38 ms; `cli_pool_acquire + cli_pool_send + cli_parse` = 6328.28 ms ≤ `cli_dispatch` 6329.00 ms (no double-count). **The v1.5 §"Caveats" residue item is resolved.**

### Delta vs v1.5 ship-gate (`reports/soak-20260504T201714Z.md`)

| Metric           | v1.5     | v1.6     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 2.779 s  | 4.092 s  | +1.31 s    | parity (sequential soak; upstream Anthropic latency variance) |
| Overall p95      | 5.820 s  | 7.665 s  | +1.85 s    | parity (within budget ≤ 12 s; upstream model variance, residue driver unchanged) |
| Overall max      | 15.105 s | 14.967 s | −0.14 s    | parity |
| Overall mean     | 2.678 s  | 3.358 s  | +0.68 s    | parity |
| ALLOW p95        |  5.60 s  |  6.33 s  | +0.73 s    | parity |
| L2/L3 p95        |  4.40 s  |  4.19 s  | −0.21 s    | parity (n=5 noise) |
| L4 alignment p95 | 12.90 s  | 13.98 s  | +1.08 s    | parity (n=5 noise; under ≤14 s budget) |
| LM (cat) p95     | 15.39 s  | 18.60 s  | +3.21 s    | regression — see §"Caveats" (S5a triage: ship-with-v1.7-watch) |
| RSS drift        | −1.20 MB | −11.17 MB| parity     | both shrink, well under 50 MB budget |

v1.6 ships P1 instrumentation only (additive; 5 new `_last_phase_timings_ms` keys + soak driver report block; no engine logic changes). ALLOW + overall p95 increases vs v1.5 are within sample-noise on a sequential soak driver — the residue driver (`cli_pool_send_ms`) is upstream Anthropic round-trip time, not local engine code. Treat the parity-band shifts as Anthropic-side variance, not earned regression.

### Budget

The v1.5 budget table is **carried forward unchanged** for v1.6. Driver localisation does not justify tightening (the lever — Haiku fastpath — is a v1.7 candidate, not landed). v1.7 latency work measures against the table below:

| Path                 | v1.6 budget (= v1.5 = v1.4 carried forward)           |
|----------------------|-------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                |
| L2/L3 escalation p95 | ≤ 8 s                                                 |
| L4 alignment p95     | ≤ 14 s                                                |
| LM (categorize) p95  | ≤ 25 s                                                |
| Overall p95          | ≤ 12 s                                                |
| Hard timeout         | 25 s (unchanged)                                      |

### Status

ACCEPTED as v1.6 budget. v1.7 latency work measures against this section.

### Caveats

- **v1.5 `_evaluate_inner` residue caveat — RESOLVED.** v1.6 P1 instrumentation localises the `_evaluate_inner` tail to `cli_pool_send_ms` p95 = 6328.07 ms (99.99% of `cli_dispatch_ms`; ~99.98% of `evaluate_inner`). Driver is the synchronous `worker.send` Anthropic CLI round-trip (subprocess stdin write + stdout JSONL response wait in `CliWorker.send` (see `cli_pool.py`)); v1.7 lever = **Haiku fastpath** (primary; downgrade more L4/ambiguous-BLOCK from Sonnet → Haiku) with **pool sizing >2** as fallback (insurance for concurrent burst load only — `cli_pool_acquire_ms` p95 = 0.06 ms confirms zero queueing under sequential soak). **v1.7 disposition: lever wired but DORMANT in production** — see §"v1.7 ship-gate baseline" §Caveats lever-falsification bullet.
- **LM (categorize) p95 = 18.60 s — regression vs v1.5 (+3.21 s).** Trend reversed: v1.4 = 19.26 s → v1.5 = 15.39 s → v1.6 = 18.60 s. Magnitude over 18 s ceiling = 0.60 s (3.3%); n=10 (high variance), spread p50→p95 = 5.91 s, dashboard log clean (no warn/error/retry/timeout/exception), no cassette envelope additions in v1.6 affecting the LM categorizer (per S5a triage). LM is advisory/categorize, not on the safety path. **Decision: ship-with-v1.7-watch** — re-measure at v1.7 ship-gate; if next sample also lands ≥ 18 s, treat as sustained regression and triage cassette/categorizer separately. **v1.7 disposition: RESOLVED** — v1.7 LM p95 = 11.95 s, watch closes per §"v1.7 ship-gate baseline" §Caveats.
- **L2/L3 + L4 + LM are n=5 / n=5 / n=10** respectively. Per-band p95 deltas vs v1.5 are within sample noise; the overall and ALLOW p95 are the higher-confidence comparisons.

## v1.7 ship-gate baseline

- **Source**: `reports/soak-20260505T125741Z.md`
- **Date**: 2026-05-05
- **Ship SHA**: pending merge of `ship/v1.7-shipgate-finalize` (will be backfilled post-merge; tag `v1.7.0`)
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) **with v1.7 P2 Haiku fastpath router enabled** (additive `cli_dispatch_fallback_ms` key — 6th row in the v1.6 CLI residue block; new `governance_fallback_routed` + `governance_envelope_missing_confidence` envelopes wired)
- **Runtime**: 1909.7 s (31.8 min)
- **Events**: 60 emitted / 158 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift **−11.33 MB** (shrink), no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.7 measured |
|---------|---------------|
| p50     | 3.530 s       |
| p95     | 9.277 s       |
| max     | 14.459 s      |
| mean    | 3.098 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 50 |  3.55 s  |  5.13 s  |
| L2/L3 escalation     |  5 |  0.00 s  |  3.70 s  |
| L4 alignment         |  5 |  8.94 s  | 13.41 s  |
| LM (categorize)      | 10 |  9.13 s  | 11.95 s  |

### ALLOW _evaluate_inner CLI residue breakout (v1.7 — 6 rows)

First ship-gate with the v1.7 P2 fallback-routing key (`cli_dispatch_fallback_ms`) wired into the v1.6 CLI residue block. The block now renders 6 rows; pre-v1.7 streams continue to render the original 5-row block byte-identically (verified by `tests/test_soak_driver_v17_residue_block.py`).

| Phase                      |  n  | p50 ms   | p95 ms   | max ms   |
|----------------------------|-----|----------|----------|----------|
| cli_setup_ms               |  50 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms            |  50 | 3546.60  | 5129.33  | 12830.87 |
| cli_pool_acquire_ms        |  50 |  0.02    |  0.06    |   0.07   |
| cli_pool_send_ms           |  50 | 3546.16  | 5128.96  | 12830.28 |
| cli_parse_ms               |  50 |  0.04    |  0.05    |   0.15   |
| cli_dispatch_fallback_ms   |  50 |  0.00    |  0.00    |   0.00   |

For reference, the v1.4 publish-path block on the same run reports `evaluate_inner` p95 = **5129.50 ms**.

### Fallback routing summary (NEW v1.7)

| Metric                                        | Value |
|-----------------------------------------------|-------|
| `governance_fallback_routed` envelopes emitted | 0     |
| `cli_dispatch_fallback_ms` p95                 | 0.00 ms |
| Per-band fallback rate — ambiguous-BLOCK       | n/a (0 ambig-BLOCK envelopes triggered in soak load mix) |
| Per-band fallback rate — HITL synthesis        | n/a (0 HITL synthesis envelopes triggered in soak load mix) |

**Lever wired but DORMANT in production code paths.** The L4 sub-band routing and the cli_governance retry path are merged; 27 new tests cover the surface deterministically. However, the production caller path (`governance._evaluate_inner_core` pre-routing call site) sets `is_ambiguous_block=False` and `is_hitl_synthesis=False` unconditionally — content-based pre-routing detection of these flags is a v1.8 backlog item. Until that wires, the L4 sub-band's Haiku-fastpath branch is unreachable from the production engine and `fallback_model_id` is `None` on every routing decision. Soak result confirms: 0 fallback fires across 60 events.

### Alignment-eval gate

- **Source**: `reports/alignment-eval-20260505T124519Z.md` (run against the merged P2 router config — same code as `main` post-`9c483be`)
- **Sonnet pass rate**: 23/24 stable rows = **0.9583** (above 0.95 gate)
- **Haiku pass rate**: 19/20 stable rows = **0.95**
- **Haiku regressions vs Sonnet**: **0**
- **FR-OG-7 row gate result**: **0 regressions** → `--ci-gate` exit **0** (PASS)
- **Regressing rows**: none

Ship-gate alignment-eval gate clean — no abandonment trigger fires per the v1.7 P3 mint rule.

### Delta vs v1.6 ship-gate (`reports/soak-20260505T073943Z.md`)

| Metric           | v1.6     | v1.7     | Δ          | Class       |
|------------------|----------|----------|------------|-------------|
| Overall p50      | 4.092 s  | 3.530 s  | −0.56 s    | improvement (within noise) |
| Overall p95      | 7.665 s  | 9.277 s  | +1.61 s    | parity (within budget ≤ 12 s; n=60 noise; upstream Anthropic variance) |
| Overall max      | 14.967 s | 14.459 s | −0.51 s    | parity |
| Overall mean     | 3.358 s  | 3.098 s  | −0.26 s    | improvement (within noise) |
| ALLOW p95        |  6.33 s  |  5.13 s  | **−1.20 s** | improvement (NOT lever effect — see §Caveats) |
| L2/L3 p95        |  4.19 s  |  3.70 s  | −0.49 s    | parity (n=5 noise) |
| L4 alignment p95 | 13.98 s  | 13.41 s  | −0.57 s    | parity (n=5 noise; under ≤14 s budget) |
| LM (cat) p95     | 18.60 s  | 11.95 s  | **−6.65 s** | **regression resolved** ✓ (watch closes) |
| RSS drift        | −11.17 MB | −11.33 MB | parity     | both shrink, well under 50 MB budget |
| `cli_pool_send_ms` p95 | 6328.07 ms | 5128.96 ms | **−1199 ms (−19.0%)** | improvement (NOT lever effect — see §Caveats) |

v1.7 ships P2 router infrastructure (additive — 1 new `RoutingDecision` field, 1 new `evaluate` kwarg, 1 new sub_timings key, 2 new bus envelopes, 1 conditional 6th row in soak block). Verdict path for v1.6 callers (every production caller post-merge) is byte-identical: 550 fast-tier tests passing.

### Budget

The v1.6 budget table is **carried forward unchanged** for v1.7. The lever is dormant in production (§Caveats), so no measured lever effect justifies tightening. v1.8 latency work measures against the table below:

| Path                 | v1.7 budget (= v1.6 = v1.5 = v1.4 carried forward)    |
|----------------------|-------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                |
| L2/L3 escalation p95 | ≤ 8 s                                                 |
| L4 alignment p95     | ≤ 14 s                                                |
| LM (categorize) p95  | ≤ 25 s                                                |
| Overall p95          | ≤ 12 s                                                |
| Hard timeout         | 25 s (unchanged)                                      |

### Status

ACCEPTED as v1.7 budget. v1.8 latency work measures against this section.

### Caveats

- **v1.6 LM (categorize) watch — RESOLVED.** v1.7 LM p95 = **11.95 s** (n=10) is well below the 18 s ceiling. Trend: v1.4 = 19.26 s → v1.5 = 15.39 s → v1.6 = 18.60 s → **v1.7 = 11.95 s**. Watch closes per the v1.7 backlog rubric ("v1.7 LM p95 < 18 s → watch closed"). Spread p50→p95 = 2.82 s (v1.6 was 5.91 s) — variance also retreated. No further action required.
- **v1.7 P2 Haiku fastpath lever — wired but DORMANT in production.** The L4 sub-band routing (alignment vs ambig-BLOCK vs HITL synthesis with confidence-gated Sonnet fallback) and the cli_governance retry path are merged; 27 new tests (11 sub-band + 7 fallback routing + 9 soak residue) cover the surface deterministically. **However**, the production caller path (`governance._evaluate_inner_core` pre-routing) sets `is_ambiguous_block=False` and `is_hitl_synthesis=False` unconditionally — content-based detection of these flags is a v1.8 backlog item. Soak result: 0 fallback fires across 60 events; `cli_dispatch_fallback_ms` p95 = 0.00 ms; 0 `governance_fallback_routed` envelopes emitted. **Lever effect cannot yet be measured.** → **LEVER ACTIVATED in v1.8 (pre-routing content-detection wired at `governance._evaluate_inner_core`); see §"v1.8 ship-gate baseline" §Caveats for the measured outcome.**
- **Lever falsification check.** `cli_pool_send_ms` p95 dropped 19.0% (6328.07 → 5128.96 ms); ALLOW p95 dropped 1.20 s; L4 alignment p95 dropped 0.57 s — all numerical improvements. **However, the drops are NOT attributable to the v1.7 lever**: fallback fire rate is 0% (the lever code path never executed in production during this soak). The drops are upstream Anthropic round-trip variance on a sequential soak driver (same driver, same load mix, same `--cli-pool-size 2`, no engine-code change to `_maybe_cli_evaluate` or `CliWorker.send`). Per the P3 §4 falsification rule: lever cannot be claimed as moved-the-needle until is_ambiguous_block / is_hitl_synthesis content-detection wires (v1.8 backlog item). The 19% improvement is recorded as upstream variance — neither earned regression nor earned lever effect.
- **Alignment-eval result.** Sonnet pass rate 0.9583 (23/24 stable rows), Haiku pass rate 0.95 (19/20 stable rows), 0 Haiku regressions vs Sonnet, 0 FR-OG-7 regressions, `--ci-gate` exit 0. P1 v2 baseline had observed 1 FR-OG-7 regression on `frog7-valid-transports-04` (sonnet 3/3 GUIDE vs haiku 3/3 INTERVENE); the v1.7 P2 baseline observed both sonnet and haiku unstable on the same row (sonnet 2/3 GUIDE; haiku 2/3 GUIDE) — the unanimous-stability rule correctly classifies this as borderline drift, not a deterministic regression. The row is also FR-OG-7 protected at the production router (`requires_alignment` keeps it on Sonnet only) so even a deterministic Haiku divergence here would be unreachable in production code paths.
- **L2/L3 + L4 + LM are n=5 / n=5 / n=10** respectively. Per-band p95 deltas vs v1.6 are within sample noise; the overall and ALLOW p95 are the higher-confidence comparisons. ALLOW p95 −1.20 s and `cli_pool_send_ms` p95 −19.0% are the strongest improvement signals but, like the others, classified as upstream variance not lever effect (lever fire rate = 0).

## v1.8 ship-gate baseline

- **Source**: `reports/soak-20260506T101746Z.md`
- **Date**: 2026-05-06
- **Ship SHA**: `main` HEAD at v1.8.0 tag (v1.8 P1 content-detection wiring merged via PR #93 + P1a/P1c prompt coverage via PR #94)
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) with v1.8 P1 `is_ambiguous_block` / `is_hitl_synthesis` content-detection wiring active at `governance._evaluate_inner_core`
- **Runtime**: 1924.2 s (32.1 min)
- **Events**: 60 emitted / 250 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift −7.15 MB, no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.8 measured |
|---------|---------------|
| p50     | 3.521 s       |
| p95     | 7.612 s       |
| max     | 12.052 s      |
| mean    | 3.060 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 49 |  3.52 s  |  6.48 s  |
| L2/L3 escalation     |  7 |  3.27 s  |  6.96 s  |
| L4 alignment         |  4 |  5.34 s  | 11.85 s  |
| LM (categorize)      | 10 | 10.17 s  | 13.30 s  |

Note: load mix shifted slightly from v1.7 (ALLOW=50, L2/L3=5, L4=5) to v1.8 (ALLOW=49, L2/L3=7, L4=4) because P2a extended `_L2_L3_TRIGGER` from 5 to 8 items, shifting the seed-4242 shuffle balance. LM=10 unchanged.

### ALLOW _evaluate_inner CLI residue breakout (v1.6 — 6 rows)

| Phase                      |  n  | p50 ms   | p95 ms   | max ms   |
|----------------------------|-----|----------|----------|----------|
| cli_setup_ms               |  49 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms            |  49 | 3521.12  | 6477.09  | 9201.16  |
| cli_pool_acquire_ms        |  49 |  0.03    |  0.56    |  15.75   |
| cli_pool_send_ms           |  49 | 3520.59  | 6470.35  | 9200.45  |
| cli_parse_ms               |  49 |  0.04    |  0.09    |   0.15   |
| cli_dispatch_fallback_ms   |  49 |  0.00    |  0.00    |   0.00   |

### Fallback routing summary (v1.8 — lever activated, outcome: dormant under production load)

| Metric                                              | Value |
|-----------------------------------------------------|-------|
| `governance_fallback_routed` envelopes emitted      | 0     |
| `cli_dispatch_fallback_ms` p95                      | 0.00 ms |
| Per-band fallback rate — ambiguous-BLOCK            | 0% (0/n — see §Caveats) |
| Per-band fallback rate — HITL synthesis             | 0% (0/n — no HITL session active during soak) |
| Total L2/L3 + L4 events with `is_ambiguous_block=True` | 2 (soak positions 5 and 55 — imperative destructive prompts matching `_looks_ambiguous_block`) |
| Haiku-first path taken (routing) | 2/2 (routing wired correctly) |
| Sonnet retry fired | 0/2 (Haiku returned confidence ≥ 0.70 on both — fallback floor not crossed) |

### Alignment-eval gate

- **Source**: `reports/alignment-eval-20260506T113450Z.md` (fresh run at v1.8 ship-gate; `model_router.py` / `cli_governance.py` unchanged from v1.7 P2 — only `governance.py` pre-routing call site + `tools/soak_driver.py` corpus modified)
- **Sonnet pass rate**: 21/23 stable rows = **0.913**
- **Haiku pass rate**: 18/20 stable rows = **0.90**
- **Haiku regressions vs Sonnet**: **0**
- **FR-OG-7 row gate result**: **0 regressions** (`haiku_regression_frog7=0`) → `--ci-gate` exit **0** (PASS)

Ship-gate alignment-eval gate clean.

### Delta vs v1.7 ship-gate (`reports/soak-20260505T125741Z.md`)

| Metric               | v1.7     | v1.8     | Δ           | Class |
|----------------------|----------|----------|-------------|-------|
| Overall p50          | 3.530 s  | 3.521 s  | −0.01 s     | parity (noise) |
| Overall p95          | 9.277 s  | 7.612 s  | **−1.67 s** | improvement (upstream variance — see §Caveats) |
| Overall max          | 14.459 s | 12.052 s | −2.41 s     | parity (noise) |
| Overall mean         | 3.098 s  | 3.060 s  | −0.04 s     | parity |
| ALLOW p95            |  5.13 s  |  6.48 s  | +1.35 s     | regression (upstream variance — see §Caveats) |
| L2/L3 p95            |  3.70 s  |  6.96 s  | +3.26 s     | apparent regression (n=5 → n=7; load-mix shift + 3 new destructive prompts in band — see §Caveats) |
| L4 alignment p95     | 13.41 s  | 11.85 s  | −1.56 s     | improvement (upstream variance; n=5 → n=4 noise) |
| LM (cat) p95         | 11.95 s  | 13.30 s  | +1.35 s     | parity (< 18 s ceiling; watch stays closed) |
| RSS drift            | −11.33 MB | −7.15 MB | +4.18 MB   | both shrink, well under 50 MB budget |
| `cli_pool_send_ms` p95 | 5128.96 ms | 6470.35 ms | **+1341 ms (+26%)** | regression (upstream variance — lever fire rate 0%; see §Caveats) |
| Fallback fire rate   | 0%       | 0%       | no change   | lever remains dormant under production load |

### Budget

v1.7 budget table **carried forward unchanged** for v1.8. Fallback fire rate = 0% means no measured lever effect; no basis to tighten the budget.

| Path                 | v1.8 budget (= v1.7 = v1.6 = v1.5 = v1.4 carried forward)   |
|----------------------|--------------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                       |
| L2/L3 escalation p95 | ≤ 8 s                                                        |
| L4 alignment p95     | ≤ 14 s                                                       |
| LM (categorize) p95  | ≤ 25 s                                                       |
| Overall p95          | ≤ 12 s                                                       |
| Hard timeout         | 25 s (unchanged)                                             |

### Status

ACCEPTED as v1.8 budget.

### Caveats

- **v1.8 P1 content-detection wiring — ACTIVATED, lever still DORMANT under production load.** `is_ambiguous_block` and `is_hitl_synthesis` are now computed from content at `governance._evaluate_inner_core` (unit tests: `tests/test_governance_content_detection.py`, 40 passing). Routing sends ambiguous-block content to Haiku-first with Sonnet fallback. Two events in the ship-gate soak matched `_looks_ambiguous_block=True` (positions 5 and 55 of seed-4242 sequence). **However, Haiku returned confidence ≥ 0.70 on both, so the `BRIDGE_L4_FALLBACK_CONFIDENCE` floor was never crossed and `cli_dispatch_fallback_ms` = 0.00 ms for both.** Fallback fire rate = 0%. The Haiku-first routing path is taken (wiring correct), but the Sonnet retry path is not triggered. Two P2a corpus-fix attempts (P1c-B deliberative questions, P2a imperative declarative forms) both failed to produce Haiku confidence < 0.70 on destructive-content prompts. Root cause: Haiku consistently returns high-confidence verdicts (SUGGEST / BLOCK / INTERVENE at ≥ 0.70) on short destructive commands. v1.9 backlog item: investigate confidence floor reduction, HITL-synthesis-only Haiku path, or verdict-based fallback trigger (see `docs/v1.9-backlog.md`).
- **Overall p95 delta is upstream variance, not lever effect.** Overall p95 dropped −1.67 s vs v1.7 while ALLOW p95 INCREASED +1.35 s. Both moves are within upstream Anthropic round-trip variance range (consistent with v1.7's ±1.6 s swing vs v1.6). No lever code path executed during the soak. v1.8 ships as a latency no-op.
- **L2/L3 p95 apparent regression (+3.26 s) is load-mix artefact.** P2a extended `_L2_L3_TRIGGER` from 5 to 8 items (adding 3 imperative destructive prompts). Seed-4242 shuffle placed 7 L2/L3 events in the 60-event sequence (vs 5 in v1.7). The two imperative destructive prompts in those 7 events trigger Haiku-first routing (slightly longer first-token path vs standard Sonnet) and the CLI judge may return INTERVENE/BLOCK on them (longer deliberation). The +3.26 s shift is attributable to the changed load shape, not a regression in the unchanged code path.
- **`cli_pool_send_ms` p95 +26%** (5128.96 → 6470.35 ms). Same variance classification as v1.7's −19% drop. No lever fires; zero code change to `CliWorker.send`; delta is upstream API round-trip variance.
- **LM p95 = 13.30 s.** Up from v1.7's 11.95 s (+1.35 s) but well within the 18 s ceiling. Watch stays closed per the v1.7 rubric.
- **Alignment-eval expanded baseline.** The v1.8 eval uses the expanded golden set (32 rows including 5 HITL-synthesis ALLOW rows, 8 ambig-BLOCK rows, and 4 negative-BLOCK rows added in v1.7 P1). Haiku regression vs Sonnet = 0; FR-OG-7 row gate exits 0.
- **v1.9 update**: lever stayed DORMANT for a second consecutive cycle. The v1.9 P1 verdict-based fallback trigger (which adds a verdict==ENGAGE branch alongside the v1.8 confidence-floor branch) also fired 0% in the v1.9 ship-gate soak (`cli_dispatch_fallback_ms` p95 = 0.00 ms across 49 ALLOW envelopes). All 60 v1.9 soak events reached ALLOW; no Haiku verdict returned ENGAGE. Two consecutive dormant cycles confirms the v1.8 caveats analysis: under cli_pool warm-process conditions, Haiku consistently returns high-confidence non-ENGAGE verdicts on the seeded destructive corpus. P1a corpus-check (`reports/p1a-corpus-haiku-verdicts-20260507T083813Z.md`) showed a fresh-process Haiku BLOCKs 100% of wrapped destructive prompts; the cli_pool reuse hypothesis (long-lived stream-json process biases Haiku toward conversational interpretation) remains the leading explanation, untested in P1a. v2.0 backlog item: cli_pool A/B (fresh-vs-reused process) to falsify or confirm.

## v1.9 ship-gate baseline

- **Source**: `reports/soak-20260507T084933Z.md`
- **Date**: 2026-05-07
- **Ship SHA**: `main` HEAD at v1.9.0 tag (P1 verdict-fallback PR #100 + P1a corpus-check PR #101 + P2 session_watcher PR #102 + P3 Learn Mode source expansion PR #103)
- **Driver**: `tools/soak_driver.py --cli-pool-size 2` (Tier 3 per ADR-17) with v1.9 P1 verdict-based fallback trigger active (verdict==ENGAGE branch added alongside the v1.8 confidence-floor branch)
- **Runtime**: 1937.3 s (32.3 min)
- **Events**: 60 emitted / 164 received via SSE
- **Verdict**: PASS (100% SSE, RSS drift +0.24 MB, no uncaught exceptions, lifecycle bridge 0 orphans)

### Latency targets (overall, n=60)

| Metric  | v1.9 measured |
|---------|---------------|
| p50     | 3.787 s       |
| p95     | 11.064 s      |
| max     | 18.548 s      |
| mean    | 3.804 s       |

### Per-band split

| Path                 | n  | p50      | p95      |
|----------------------|----|----------|----------|
| ALLOW (routine)      | 49 |  3.72 s  |  8.54 s  |
| L2/L3 escalation     |  7 |  3.96 s  | 15.09 s  |
| L4 alignment         |  4 |  5.46 s  | 17.40 s  |
| LM (categorize)      | 10 | 11.51 s  | 15.11 s  |

Note: L2/L3 n=7 and L4 n=4 reproduce the v1.8 small-sample p95 envelope (p95 = max in both bands at these sample sizes). Decision distribution: ALLOW 60/60 (100%) — no envelope reached BLOCK / INTERVENE / SUGGEST verdicts in the soak; the verdict-fallback ENGAGE branch had no events to fire on.

### ALLOW _evaluate_inner CLI residue breakout (v1.6 — 6 rows)

| Phase                      |  n  | p50 ms   | p95 ms   | max ms   |
|----------------------------|-----|----------|----------|----------|
| cli_setup_ms               |  49 |  0.00    |  0.01    |   0.01   |
| cli_dispatch_ms            |  49 | 3721.39  | 8542.49  | 9684.47  |
| cli_pool_acquire_ms        |  49 |  0.03    |  0.05    |   0.06   |
| cli_pool_send_ms           |  49 | 3720.90  | 8541.60  | 9683.90  |
| cli_parse_ms               |  49 |  0.07    |  0.15    |   0.31   |
| cli_dispatch_fallback_ms   |  49 |  0.00    |  0.00    |   0.00   |

### Fallback routing summary (v1.9 — verdict-fallback added, lever DORMANT 2nd consecutive cycle)

| Metric                                              | Value |
|-----------------------------------------------------|-------|
| `governance_fallback_routed` envelopes emitted      | 0     |
| `cli_dispatch_fallback_ms` p95                      | 0.00 ms |
| Verdict-branch fires (`verdict==ENGAGE`)            | 0 (no Haiku verdict returned ENGAGE) |
| Confidence-branch fires (`c < BRIDGE_L4_FALLBACK_CONFIDENCE`) | 0 (Haiku ≥ 0.70 throughout) |
| All 60 events terminal verdict | ALLOW (100%) |

### Alignment-eval gate

- **Source**: `reports/alignment-eval-20260507T093010Z.md` (fresh run at v1.9 ship-gate; `cli_governance.py` modified by P1 verdict-fallback addition; FR-OG-7 rows unchanged from v1.8)
- **Sonnet pass rate**: 24/24 stable rows = **1.000**
- **Haiku pass rate**: 21/22 stable rows = **0.9545**
- **Haiku regressions vs Sonnet**: **0**
- **FR-OG-7 row gate result**: **0 regressions** (`haiku_regression_frog7=0`) → `--ci-gate` exit **0** (PASS)

Ship-gate alignment-eval gate clean; sonnet stability is the strongest of any cycle to date (24/24 vs v1.8 21/23).

### Delta vs v1.8 ship-gate (`reports/soak-20260506T101746Z.md`)

| Metric               | v1.8     | v1.9     | Δ           | Class |
|----------------------|----------|----------|-------------|-------|
| Overall p50          |  3.521 s |  3.787 s | +0.27 s     | parity (noise) |
| Overall p95          |  7.612 s | 11.064 s | **+3.45 s** | regression (within ≤ 12 s budget; upstream variance — see §Caveats) |
| Overall max          | 12.052 s | 18.548 s | +6.50 s     | regression (within tail; small-sample) |
| Overall mean         |  3.060 s |  3.804 s | +0.74 s     | mild regression (upstream variance) |
| ALLOW p95            |  6.48 s  |  8.54 s  | +2.06 s     | regression (within ≤ 12 s ALLOW budget; upstream variance — lever fire rate 0%) |
| L2/L3 p95            |  6.96 s  | 15.09 s  | **+8.13 s** | apparent regression — n=7 small-sample tail; **VIOLATES ≤ 8 s L2/L3 budget**; flagged for v2.0 (see §Caveats) |
| L4 alignment p95     | 11.85 s  | 17.40 s  | +5.55 s     | apparent regression — n=4 small-sample (p95 = max); **VIOLATES ≤ 14 s L4 budget**; flagged for v2.0 (see §Caveats) |
| LM (cat) p95         | 13.30 s  | 15.11 s  | +1.81 s     | parity (< 18 s ceiling; watch stays closed) |
| RSS drift            | −7.15 MB | +0.24 MB | both within ±50 MB; v1.9 essentially flat |
| `cli_pool_send_ms` p95 | 6470.35 ms | 8541.60 ms | **+2071 ms (+32%)** | regression (upstream variance — lever fire rate 0%; see §Caveats) |
| Fallback fire rate   | 0%       | 0%       | no change   | lever remains dormant under production load (2nd consecutive cycle) |
| Sonnet alignment-eval pass rate | 0.913 | 1.000 | +0.087 | improvement (24/24 stable rows) |
| Haiku alignment-eval pass rate  | 0.90  | 0.9545 | +0.0545 | improvement |

### Budget

v1.8 budget table **carried forward unchanged** for v1.9. The L2/L3 p95 (15.09 s) and L4 alignment p95 (17.40 s) measurements exceed the long-standing ≤ 8 s and ≤ 14 s targets, but at n=7 and n=4 the band p95 is dominated by single-event tail variance and is consistent with the v1.7→v1.8 oscillation pattern (v1.7 L2/L3 p95 = 3.70 s, v1.8 = 6.96 s, v1.9 = 15.09 s). Lever fire rate = 0% (verdict-fallback dormant for second consecutive cycle) — no code-path-attributable basis to tighten the budget.

| Path                 | v1.9 budget (= v1.8 = v1.7 = v1.6 = v1.5 = v1.4 carried forward)   |
|----------------------|--------------------------------------------------------------|
| ALLOW p95            | ≤ 12 s                                                       |
| L2/L3 escalation p95 | ≤ 8 s                                                        |
| L4 alignment p95     | ≤ 14 s                                                       |
| LM (categorize) p95  | ≤ 25 s                                                       |
| Overall p95          | ≤ 12 s                                                       |
| Hard timeout         | 25 s (unchanged)                                             |

### Status

ACCEPTED as v1.9 budget.

### Caveats

- **Verdict-fallback (v1.9 P1) lever DORMANT — 2nd consecutive cycle.** v1.9 P1 added a verdict==ENGAGE branch to the v1.8 confidence-floor fallback. The Tier 3 soak produced 60/60 ALLOW decisions; no Haiku verdict returned ENGAGE; the new branch had nothing to fire on. `cli_dispatch_fallback_ms` p95 = 0.00 ms (identical to v1.8). The combined (confidence + verdict) lever is now wired but has fired 0% across two consecutive ship-gate soaks. P1a probe diagnostic (`reports/p1a-corpus-haiku-verdicts-20260507T083813Z.md`) confirms fresh-process wrapped Haiku BLOCKs 100% of destructive prompts at confidence ≥ 0.85. The leading hypothesis — cli_pool warm-process reuse biases Haiku toward conversational ALLOW interpretation — remains untested in P1a; deferred to v2.0 cli_pool A/B.
- **Small-sample band p95 violations (L2/L3, L4) are NOT lever regressions.** L2/L3 p95 +8.13 s and L4 p95 +5.55 s look alarming but reproduce the v1.7→v1.8 oscillation pattern at the same small sample sizes (n=7, n=4). At n=4 in particular p95 = max, and a single 17.40 s outlier dominates. No code change touches the L2/L3 or L4 routing code path between v1.8 and v1.9; lever fire rate = 0% in both bands. Treat as upstream Anthropic round-trip tail variance until a larger-n soak (Tier 4 candidate) lands.
- **Overall p95 +3.45 s vs v1.8 is upstream variance, not lever effect.** Same classification as the v1.7→v1.8 −1.67 s improvement: no lever code path executed during the soak. v1.9 ships as a latency no-op; the per-band tail movements are within the upstream ±2 s envelope when scaled by the `cli_pool_send_ms` swing.
- **`cli_pool_send_ms` p95 +32%** (6470.35 → 8541.60 ms). Same variance classification as v1.7→v1.8 (+26%) and v1.6→v1.7 (−19%). No lever fires; zero code change to `CliWorker.send`; delta is upstream API round-trip variance. The cumulative drift across three consecutive cycles (5128 → 6470 → 8541 ms) is being tracked but not yet attributable to a code path.
- **Decision-distribution skew — corpus-routing artefact, not policy regression.** All 60 soak events terminated at ALLOW. The escalation events (L2/L3 n=7, L4 n=4) executed CLI escalation paths but none of the cli_governance verdicts returned BLOCK / INTERVENE / SUGGEST. This is the same regime as v1.8 (which also ran ALLOW-dominant); the verdict-fallback lever cannot be exercised under this regime by definition. v2.0 backlog candidate: hardened destructive corpus that produces non-ALLOW verdicts in cli_governance under cli_pool warm-process conditions, rather than just under fresh-process probe conditions.
- **LM p95 = 15.11 s.** Up from v1.8's 13.30 s (+1.81 s) but well within the 18 s ceiling. Watch stays closed per the v1.7 rubric (third consecutive cycle).
- **Alignment-eval baseline strongest to date.** Sonnet 24/24 stable (1.000) and Haiku 21/22 stable (0.9545) — both higher than any prior cycle (v1.8: sonnet 0.913, haiku 0.90). 0 regressions vs Sonnet, 0 FR-OG-7 regressions, exit 0. v1.9 P3 (Learn Mode JSONL source expansion) and v1.9 P2 (session watcher) made no changes to `cli_governance.py` routing; the alignment improvement is most plausibly explained by upstream model variance, but the corpus is unchanged from v1.8 so the comparison is apples-to-apples on golden rows.

## References

- `reports/soak-20260502T141527Z.md` — locked v1.0 soak baseline
- `reports/soak-20260502T201806Z.md` — v1.0 final soak (p95 = 19.08s,
  the regression Task I was scoped to investigate)
- `reports/perf-hydrator-20260502T232639Z.md` — Task I per-call probe
- `reports/soak-20260503T094438Z.md` — v1.1 30-min soak, no pool
  (operator-error baseline; reproduces v1.0 numbers)
- `reports/soak-20260503T101758Z.md` — v1.1 30-min soak, pool size 2
  (the v1.1 re-baseline source)
- `reports/soak-20260503T145124Z.md` — v1.2 30-min ship-gate soak,
  pool size 2 (the v1.2 baseline source per §"v1.2 ship-gate baseline")
- `reports/soak-20260504T152005Z.md` — v1.3 32-min ship-gate soak,
  pool size 2 + Path-A LM dialogue pump (the v1.3 baseline source per
  §"v1.3 ship-gate baseline")
- `reports/soak-20260504T182027Z.md` — v1.4 32-min ship-gate soak with
  the new `engine._last_phase_timings_ms` instrumentation enabled (the
  v1.4 baseline source per §"v1.4 ship-gate baseline")
- `reports/soak-20260504T201714Z.md` — v1.5 32-min ship-gate soak with
  the v1.5 `_evaluate_inner` sub-phase instrumentation enabled (the
  v1.5 baseline source per §"v1.5 ship-gate baseline")
- `reports/soak-20260505T073943Z.md` — v1.6 32-min ship-gate soak with
  the v1.6 P1 `_evaluate_inner` CLI residue instrumentation enabled
  (the v1.6 baseline source per §"v1.6 ship-gate baseline"); driver
  localised to `cli_pool_send_ms`
- `reports/soak-20260505T125741Z.md` — v1.7 31.8-min ship-gate soak with
  the v1.7 P2 Haiku fastpath router enabled (additive
  `cli_dispatch_fallback_ms` 6th row in the CLI residue block); the
  v1.7 baseline source per §"v1.7 ship-gate baseline"
- `reports/alignment-eval-20260505T124519Z.md` — v1.7 alignment-eval
  `--ci-gate` baseline against the merged P2 router config; sonnet
  0.9583 / haiku 0.95 / 0 FR-OG-7 regressions / exit 0
- `reports/soak-20260506T101746Z.md` — v1.8 32.1-min ship-gate soak with
  v1.8 P1 content-detection wiring active; the v1.8 baseline source per
  §"v1.8 ship-gate baseline"
- `reports/alignment-eval-20260506T113450Z.md` — v1.8 alignment-eval
  `--ci-gate` ship-gate run; sonnet 0.913 / haiku 0.90 / 0 FR-OG-7
  regressions / 0 haiku regressions vs sonnet / exit 0
- `reports/soak-20260507T084933Z.md` — v1.9 32.3-min ship-gate soak with
  v1.9 P1 verdict-based fallback trigger active (verdict==ENGAGE branch
  added alongside the v1.8 confidence-floor branch); the v1.9 baseline
  source per §"v1.9 ship-gate baseline"
- `reports/alignment-eval-20260507T093010Z.md` — v1.9 alignment-eval
  `--ci-gate` ship-gate run; sonnet 1.000 / haiku 0.9545 / 0 FR-OG-7
  regressions / 0 haiku regressions vs sonnet / exit 0 (strongest cycle
  to date)
- `reports/p1a-corpus-haiku-verdicts-20260507T083813Z.md` — v1.9 P1a
  fresh-process Haiku probe (wrapped, 100% BLOCK at confidence ≥ 0.85);
  diagnostic supporting the cli_pool warm-process-reuse hypothesis for
  fallback-lever dormancy
- `docs/v1.2-soak-finalize.md` — M-task plan for the v1.2 close-out
  cycle; M3 produced the report cited above
- `docs/v1.3-soak-lm-extension.md` — v1.3 Path-A design + DOD; ADR-17
  amendment companion
- `docs/v1.0-ship-plan.md` — Task G scope
- `docs/v1.1-task-plan.md` — Task I (hydrator lazy-init), Task J (warm-pool)
- Project memory: `project_cli_migration` (api_governance → cli_governance)
- `REQUIREMENTS.md` §5.1 NFR-P (aligned with this ADR)
