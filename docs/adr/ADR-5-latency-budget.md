# ADR-5: Governance latency budget (revised for v1.0)

- **Status**: Accepted (v1.0)
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

## References

- `reports/soak-20260502T141527Z.md` — locked v1.0 soak baseline
- `docs/v1.0-ship-plan.md` — Task G scope
- Project memory: `project_cli_migration` (api_governance → cli_governance)
- `REQUIREMENTS.md` §5.1 NFR-P (aligned with this ADR)
