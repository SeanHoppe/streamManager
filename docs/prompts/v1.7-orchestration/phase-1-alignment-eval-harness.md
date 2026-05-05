You are implementing **Phase P1 — L4 alignment eval harness** from the streamManager v1.7 cycle.

## Branch + base

- Base: `main` (v1.6.0 tagged at `6866dad`).
- PR target: `main`.
- Branch: `feat/v1.7-alignment-eval-harness` (or operator's choice).
- If `main` is unexpectedly behind v1.6.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

The following symbols are load-bearing. Verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, `CliWorker.send`, `CliPool.acquire` |
| K (v1.1) | `src/stream_manager/desktop_command_consumer.py` | `_run_sse`, `_consume_sse_stream`, `transport` kwarg |
| L (v1.1) | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column |
| N (v1.1) | `src/stream_manager/wirecli.py` | entire module |
| A (v1.2) | `tools/soak_driver.py` | `--cli-replay` flag, `--cli-pool-size` flag (extend, never remove) |
| C (v1.2) | `src/stream_manager/lifecycle_bridge.py` | `LifecycleBridge` outer surface |
| D (v1.2) | `src/stream_manager/desktop_command_consumer.py` | `_VALID_TRANSPORTS = frozenset({"sse"})` |
| E (v1.2) | `src/stream_manager/cli_client.py` | `Transport = Literal["wirecli"]`, `_JSON_REMOVED_MSG` |
| v1.3 P5d | `src/stream_manager/governance.py` | `_consult_learn_mode_bias`, bias_consult timing capture, `_emit_learn_mode_bias_applied` |
| v1.4 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.4 keys |
| v1.5 P1 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.5 sub-phase keys; `_sub_timings_in_flight` transient slot |
| v1.6 P1 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.6 CLI residue keys |
| v1.6 P1 | `src/stream_manager/cli_governance.py` | `CliGovernor.evaluate` `sub_timings: dict | None = None` kwarg |
| v1.4 + v1.5 + v1.6 | `tools/soak_driver.py` | `_ALLOW_PHASE_ORDER`, `_format_allow_phase_breakout`, all three ALLOW breakout blocks |
| v1.1 NFR-M2 | `src/stream_manager/cli_governance.py` | `CliGovernor.evaluate` outer signature |
| NFR-M1-M5 | `src/stream_manager/model_router.py` | `route()` priority order, `RoutingDecision`, `ConvergenceMonitor` |

P1 must NOT edit any of the above. P1 is additive: a new tool, a new golden-set, and a new test file.

Pre-flight grep:

```
grep -nE 'CliPool|CliWorker|_install_lazy_hydrator|_run_sse|matched_hash|--cli-replay|LifecycleBridge|_VALID_TRANSPORTS|Literal\["wirecli"\]|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|_consult_learn_mode_bias|_sub_timings_in_flight|cli_setup_ms|cli_pool_send_ms|sub_timings|RoutingDecision|ConvergenceMonitor' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/desktop_command_consumer.py src/stream_manager/lifecycle_bridge.py src/stream_manager/cli_client.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP and report — likely silent-revert trap.

## Task brief

The v1.7 P2 Haiku fastpath router change ships a Haiku-first / Sonnet-fallback path on L4 ambiguous-BLOCK and HITL synthesis cells. Without a deterministic golden-set harness that exercises the L4 surface and asserts verdict equality, P2 ships blind. P1 must land FIRST with a green baseline against the unchanged v1.6 router (Sonnet on L4) before P2 is allowed to flip routing.

P1 is purely observational. NO router edit. NO change to `model_router.route` priority order.

### Deliverables

1. **Runner**: `tools/alignment_eval.py` — CLI tool that:
   - Loads `tests/golden/l4_alignment.jsonl`. Each row: `{id, prompt, expected_verdict, expected_safety_tags, source_note, model_floor}`. `model_floor` ∈ `{"haiku","sonnet","any"}`.
   - For each row, invokes `CliGovernor.evaluate(content=prompt, model_id=<override>)` against TWO model overrides via env mutation in-process:
     - control: `BRIDGE_L4_MODEL=claude-sonnet-4-6`
     - candidate: `BRIDGE_L4_MODEL=claude-haiku-4-5-20251001`
   - Emits a markdown report `reports/alignment-eval-<UTC>Z.md` with: per-row table (id, expected, sonnet-actual, haiku-actual, agree?), summary stats (total / sonnet-pass / haiku-pass / haiku-regression-vs-sonnet), and a list of regressing rows with the FR-OG-7 subset called out separately.
   - Supports a `--ci-gate` flag (used in P2). In `--ci-gate` mode, exit non-zero if any row with `model_floor == "sonnet"` regresses on Haiku vs Sonnet (i.e. Sonnet matches expected but Haiku diverges). FR-OG-7 alignment rows MUST carry `model_floor = "sonnet"`.
   - Supports a `--report-only` flag (used in P1) that emits the report and always exits zero.

2. **Golden-set seed**: `tests/golden/l4_alignment.jsonl` — minimum 30 rows covering:
   - FR-OG-7 protected-symbol alignment (canonical Sonnet wins) — `model_floor = "sonnet"`
   - Ambiguous BLOCK (verdict on edge cases — destructive command with low pattern confidence) — `model_floor = "any"`
   - HITL synthesis (note rendering for ops handoff) — `model_floor = "any"`
   - Negative controls (clear ALLOW, clear BLOCK at high precheck confidence) — `model_floor = "any"`
   Each row carries a stable `id` (UUID-like or human slug, e.g. `frog7-protected-symbol-01`) so report rows are diff-friendly across runs.

3. **Pytest entrypoint**: `tests/test_alignment_eval_harness.py`:
   - Smoke test that the runner loads the golden-set and emits a well-formed report against the **v1.6 default config** (Sonnet on L4). Pass criterion: control column ≥ 95% verdict equality vs `expected_verdict`. Anything less means the golden-set is broken, not the model.
   - Schema test on golden-set rows (every row has all six fields including `id`; `model_floor` is one of three allowed values; `id` is unique across the file).
   - Both tests are marked `@pytest.mark.alignment_eval` and excluded from the default fast suite. Opt-in via `pytest -m alignment_eval`.

4. **CI wire-up**: register the `alignment_eval` marker in `pytest.ini` / `pyproject.toml` (whichever the repo uses) so `pytest -m alignment_eval` runs the harness and `pytest -m "not alignment_eval"` excludes it from the default run.

### Verdict-path invariant

Zero changes to `engine`, `governance`, `cli_governance`, or `model_router`. P1 is additive: one new tool, one new golden-set, one new test file, and one marker registration.

### No new bus envelopes

Harness does NOT publish to the bus. Cassette/beacon coverage unaffected (memory: `feedback_cassette_must_cover_new_envelopes.md` — verify by grep, not by extension).

### Real CLI, not synthetic

Per memory `feedback_cli_over_sdk.md`: the harness drives the actual `CliGovernor.evaluate` path (which spawns / pools the Anthropic CLI). Do NOT bypass with a mock LLM — alignment quality measured on synthetic responses is meaningless. The harness must run against a real `claude -p` subprocess to produce a meaningful baseline.

### Determinism + sample noise

LLM responses are non-deterministic at temperature > 0. Run each golden-set row 3 times and report majority verdict. Mark rows where the 3 runs disagree as `unstable` and exclude them from the gate (note in report). The gate fires only on stable-verdict regressions.

## DOD

- [ ] `tools/alignment_eval.py` exists and runs `--report-only` clean against the v1.6 main router config
- [ ] `tests/golden/l4_alignment.jsonl` exists with ≥ 30 rows, schema-valid, all `id`s unique
- [ ] `tests/test_alignment_eval_harness.py` exists, both tests pass under `pytest -m alignment_eval`
- [ ] `pytest -m "not alignment_eval"` still runs the default fast suite without picking up the harness
- [ ] Control column ≥ 95% verdict equality on the report (i.e. golden-set is internally consistent against Sonnet)
- [ ] No edits under `src/`, `tools/soak_driver.py`, `tools/cassette_record.py`, `dashboard/` — verify with `git --no-pager diff origin/main..HEAD --stat`
- [ ] No new bus envelopes — verify with `grep -rn 'governance_fallback_routed' src/` returns ZERO matches (P1 must NOT pre-introduce P2's envelope; existing v1.6 envelopes like `governance_call` are unchanged)
- [ ] `reports/alignment-eval-<UTC>Z.md` baseline run committed (or attached to PR description)
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1 ships, scan the baseline report:
- If control column < 95% (golden-set broken vs Sonnet): mint `phase-1a-golden-set-repair.md` BEFORE P2 cuts. Possible causes: prompt ambiguity, expected-verdict miscalibration, FR-OG-7 row drift.
- If > 5% of rows are `unstable` (3-run disagreement): mint `phase-1b-determinism-investigation.md`. Possible causes: temperature too high, prompt ambiguity, model TTFT non-determinism.
- If neither: P2 (`phase-2-haiku-fastpath-router.md`) is unblocked.

If the harness CANNOT produce a green baseline at all (e.g. golden-set is fundamentally non-deterministic on Sonnet), ABANDON the Haiku fastpath lever per the abandonment rule in `docs/v1.7-task-plan.md`. P2 is rewritten as `phase-2-pool-sizing-burst-tier.md`.

Report back when PR is open with: PR URL, diff stat, baseline alignment-eval report path, control / candidate pass rates, regressing-row count.
