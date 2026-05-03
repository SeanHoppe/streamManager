# ADR-17: Three-tier soak model (replay / record-cassette / ship-gate)

- **Status**: Accepted (v1.2)
- **Date**: 2026-05-03
- **Related**: ADR-5 (latency budget), v1.2 Task A

## Context

The 30-minute ship-gate soak burns 60 real `claude -p` calls per run.
That makes it impossible to gate every CI run on it (quota cost), and
because every run draws from a shared rate-limit bucket, upstream
rate-limit jitter leaks directly into our latency numbers — corrupting
the p95 we use to feed ADR-5.

We need a soak shape where:

- routine CI runs cost 0 quota,
- ship-gate runs remain the source of truth for absolute latency, and
- the gap between them can be refreshed cheaply enough to catch
  model-side envelope drift before it hits ship-gate.

## Decision

Adopt a three-tier soak model.

### Tier 1 — replay (free; every CI run / local dev)

`tools/soak_driver.py --cli-replay <cassette.jsonl>`

- Driver does **not** spawn a real `claude` subprocess.
- Each line of the cassette is one canned envelope; the driver sleeps
  `recorded_latency_ms` then publishes the recorded decision through the
  bus exactly as `GovernanceEngine.evaluate` would.
- Tests pool/bus/governance plumbing only — no model calls, no PATH
  dependency on `claude`.
- Runtime is bounded by the sum of recorded latencies, not by quota.

### Tier 2 — record-cassette (weekly; Haiku model)

`tools/cassette_record.py`

- Runs a real soak with `claude -p --model claude-haiku-4-5-20251001`.
- Writes `tests/fixtures/soak_cassette_<YYYY-MM-DD>.jsonl`.
- Each envelope captures the original prompt, the recorded wall-clock
  latency in ms, and the canonical decision payload (action, confidence,
  reasoning, model_used, layer).
- Cheap baseline refresh: catches model-side envelope drift before
  ship-gate runs into it. Cost: ~60 Haiku calls per refresh.

### Tier 3 — ship-gate soak (minor version cut; default model)

`tools/soak_driver.py --cli-pool-size 2`

- Existing path; no behavioural change in this ADR.
- This tier — and **only** this tier — is the source of truth for the
  absolute latency targets in ADR-5. Numbers from any other tier do not
  feed the budget.

## Cassette is a *relative* signal

> **Warning.** Cassette p95 is a *relative* regression signal, not an
> absolute target. The cassette is recorded against Haiku, not the
> default ship-gate model, and `recorded_latency_ms` snapshots a specific
> moment of the upstream rate-limit/queue state. Do not compare cassette
> p95 to the ADR-5 budget; compare the current cassette p95 to the
> previous cassette p95 to detect plumbing regressions.

ADR-5 absolute latency numbers come from Tier 3 only.

## Implementation notes

- The `--cli-replay` flag short-circuits before the `claude`-on-PATH
  check and before any `cli_pool` or `BRIDGE_API_GOV` setup. Replay is
  guaranteed not to spawn a model process.
- `tests/test_soak_replay.py` runs the driver in replay mode with `PATH`
  scrubbed of any `claude` binary directory and asserts the run still
  passes. This is the regression test: if a future change causes replay
  to need the CLI, this test fails.
- The cassette schema is intentionally minimal so it can survive small
  governance-engine changes. Adding optional fields is safe; renaming or
  removing required fields is a breaking change requiring a new ADR.

## DOD checklist

- `tools/soak_driver.py --cli-replay <path>` runs without `claude` on PATH.
- `tools/cassette_record.py` writes a re-runnable artifact under
  `tests/fixtures/soak_cassette_*.jsonl`.
- A sample cassette is committed.
- `tests/test_soak_replay.py` exercises the replay path.
- ADR-5 cross-references this ADR (only ship-gate feeds the budget).
- No v1.1.0 do-not-touch symbol is modified.
- `pytest -q` passes end-to-end.

## References

- `tools/soak_driver.py` — replay flag implementation
- `tools/cassette_record.py` — cassette recorder
- `tests/fixtures/soak_cassette_*.jsonl` — committed cassette sample(s)
- `tests/test_soak_replay.py` — replay-tier smoke test
- `docs/adr/ADR-5-latency-budget.md` — absolute latency budget (Tier 3)
- `docs/v1.1-task-plan.md` §"v1.2 backlog" — original framing
