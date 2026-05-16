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

## v1.3 `learn_dialogue` extension (Path-A)

**Status:** Additive amendment; ratified 2026-05-04 with `ship/v1.3-soak-lm-extension`.

The cassette `kind` enum gains a fourth value, `learn_dialogue`, used by
the recorder to capture Learn Mode (FR-LM-1..6) categorizer round-trips
alongside the existing 60 `engine.evaluate` envelopes. The new envelope
preserves all required v1.2 fields (`kind`, `content`, `recorded_latency_ms`,
`decision`) so v1.2-era replay code and validation paths see no schema
break, and adds four optional fields:

```
desktop_prompt:                  verbatim assistant turn text
user_reply:                      verbatim operator reply text
recorded_categorize_latency_ms:  Sonnet wall-clock per pair
category_result.{category,
                 confidence,
                 reasoning}:     CategoryResult fields
```

Replay (`tools/soak_driver.py::_run_replay`) routes `kind == "learn_dialogue"`
into a new `state.lm_categorize_latencies_s` bucket, surfaced as the
fourth row ("LM (categorize)") in the per-band p50/p95 table. Backward
compat: v1.2 cassettes (zero `learn_dialogue` rows) replay unchanged
and the LM row reads `n=0`.

Ship-gate (`tools/soak_driver.py::main`) runs the same dialogue pump
after the engine.evaluate publish loop with real Sonnet, populating the
LM row in the M3 ship-gate report. Operators may pass `--skip-lm-pump`
on legacy CI runs without Sonnet quota.

See `docs/v1.3-soak-lm-extension.md` for the full design + DOD.

## v2.0 Tier 1.5 amendment — smoke soak (per-PR; pool-warmup gate)

**Status:** Additive amendment; ratified 2026-05-07 with v2.0 P2.

A fast-soak variant sits between Tier 1 (replay, 0 quota) and Tier 3
(32 min, full ship-gate). Tier 1.5 is a **parameter set**, not a new
flag — `tools/soak_driver.py` flag surface is unchanged.

### Invocation

```
python tools/soak_driver.py --cli-pool-size 2 --total-seconds 120 --interval-seconds 20
```

- Wall-clock: ~90 s (~6 publish ticks at `--interval-seconds 20`).
- Token cost: ~6 real `claude -p` calls (Haiku at typical L4 alignment
  band; mix may shift if `_L2_L3_TRIGGER` corpus selects different
  bands).
- Real CLI calls only — does NOT use `--cli-replay`. Tier 1 covers
  cassette-replay regression. Tier 1.5 covers real-CLI plumbing +
  pool-warmup regression, at a fraction of Tier 3 cost.

### Gate semantics

**Binary gate** — pool warmed AND clean shutdown.

- PASS criteria: `cli_pool_send_ms` p95 finite (i.e. pool warmed at
  least one worker), driver exits 0, no panics in soak summary.
- Tier 1.5 is **NOT** a latency gate. Numbers do NOT feed ADR-5.
  ADR-5 absolute latency targets come from Tier 3 only (per the
  Cassette warning above; same rule applies here).
- Tier 1.5 is **NOT** an alignment gate. Alignment-eval `--ci-gate` is
  separate (run at ship-gate per Tier 3 DOD).

### Position relative to other tiers

| Tier | Cost | Purpose | Feeds ADR-5? |
|---|---|---|---|
| Tier 1 (replay) | 0 quota | Cassette plumbing regression | No |
| **Tier 1.5 (smoke)** | **~6 calls** | **Real-CLI plumbing + pool-warmup, per-PR** | **No** |
| Tier 2 (cassette record) | ~60 Haiku calls | Cassette baseline refresh | No |
| Tier 3 (ship-gate) | ~60 calls | Absolute latency source-of-truth | **Yes** |

### Token-reduction estimate

If a typical cycle has 5 hot-path PRs that touch `cli_pool` /
`cli_governance` / `governance` / `model_router` (the four
Tier-1.5-required surfaces — see `docs/soak-trigger-matrix.md`):

- Tier 3 on every hot-path PR: 5 × 60 = **300 calls / cycle**.
- Tier 1.5 on every hot-path PR: 5 × 6 = **30 calls / cycle**.
- Reduction: **~90%** (~270 calls saved per cycle vs Tier-3-on-every-PR
  baseline).

Vs status quo (no gate, regression caught only at ship-gate), Tier 1.5
costs ~30 calls / cycle to catch plumbing breakage one merge earlier.

### Cassette compatibility

Tier 1.5 hits real `claude -p` (just at smaller scale), not replay.
It is not a cassette consumer. Per
`feedback_cassette_must_cover_new_envelopes.md`, the cassette
recorder + replay path must cover every new envelope **type** the
soak emits — Tier 1.5 introduces no new envelope types (it runs the
same `engine.evaluate` loop as Tier 3 with a smaller
`--total-seconds` window), so no `cassette_record.py` extension is
required.

### Trigger matrix

PR-touch-path → required tier mapping lives in
`docs/soak-trigger-matrix.md`. v2.0 P2 codifies the matrix as
**advisory** (operator-driven). CI gate enforcement is a v2.1
backlog candidate if the matrix proves stable in v2.0.

### Mint-new-tier rule

A Tier 4 (large-n smoke for tail-variance triage, flagged in v1.9
ship-gate as a v2.0 backlog candidate) is NOT minted in this
amendment. Codify Tier 1.5 only; Tier 4 lives in v2.1 backlog per
ADR-18 Rule 4 (phase budget at cap).

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
