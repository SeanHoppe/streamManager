You are implementing **Phase P1 — `_evaluate_inner` sub-phase instrumentation** from the streamManager v1.5 cycle.

## Branch + base

- Base: `main` (v1.4.0 tagged at `8b50f47`).
- PR target: `main`.
- Branch: `feat/v1.5-evaluate-inner-phase-timings` (or operator's choice).
- If `main` is unexpectedly behind v1.4.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

The following symbols are load-bearing. Verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, `.bridge/cli-pool.pids` |
| I (v1.1) | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` |
| K (v1.1) | `src/stream_manager/desktop_command_consumer.py` | `_run_sse`, `_consume_sse_stream`, `transport` kwarg |
| K (v1.1) | `dashboard/server.py` | `/api/commands/stream` SSE endpoint |
| L (v1.1) | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column |
| M (v1.1) | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status` |
| N (v1.1) | `src/stream_manager/wirecli.py` | entire module |
| A (v1.2) | `tools/soak_driver.py` | `--cli-replay` flag, `--cli-pool-size` flag (extend, never remove) |
| C (v1.2) | `src/stream_manager/lifecycle_bridge.py` | `LifecycleBridge` outer surface |
| D (v1.2) | `src/stream_manager/desktop_command_consumer.py` | `_VALID_TRANSPORTS = frozenset({"sse"})` |
| E (v1.2) | `src/stream_manager/cli_client.py` | `Transport = Literal["wirecli"]`, `_JSON_REMOVED_MSG` |
| v1.3 P5d | `src/stream_manager/governance.py` | `_consult_learn_mode_bias`, bias_consult timing capture, `_emit_learn_mode_bias_applied` |
| v1.4 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` dict (extend keys, never remove existing keys: `inbound_publish`, `evaluate_inner`, `bias_consult`, `hitl_classify_trigger`, `hitl_route`, `record_decision`, `alert_publish`, `total`) |
| v1.4 | `tools/soak_driver.py` | `_ALLOW_PHASE_ORDER` (extend, never reorder existing entries), `_format_allow_phase_breakout`, `### ALLOW publish-path phase breakout (v1.4)` block |

Pre-flight grep:

```
grep -nE 'CliPool|_install_lazy_hydrator|_run_sse|matched_hash|--cli-replay|LifecycleBridge|_VALID_TRANSPORTS|Literal\["wirecli"\]|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|_consult_learn_mode_bias' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/desktop_command_consumer.py src/stream_manager/lifecycle_bridge.py src/stream_manager/cli_client.py tools/soak_driver.py
```

If any symbol missing, STOP and report — likely silent-revert trap.

## Task brief

v1.4 ship-gate (`reports/soak-20260504T182027Z.md`) disproved the v1.3.1 publish-path I/O hypothesis. ALLOW p95 = 7.572 s, of which `inbound_publish` p95 = 0.43 ms and `record_decision` p95 = 0.11 ms. **100% of the ALLOW tail now sits inside `_evaluate_inner`** and is opaque to the soak report. ADR-5 v1.4 §"Caveats" calls for sub-phase timings inside `_evaluate_inner` so the next ship-gate can attribute the tail to a specific component before any ALLOW p95 budget tightening is attempted.

Implement five sub-phase wall-clocks inside `_evaluate_inner` (and any helpers it calls before returning):

| Sub-phase key | Spans |
|---|---|
| `og7_check` | `_check_fr_og7(msg, active_profile_slug)` call (governance.py around line 378) |
| `fast_precheck` | the `_evaluate_inner_core` precheck path — wrap the precheck portion of `_evaluate_inner_core` (governance.py near line 782) |
| `graph_classify` | the decision-graph classify call inside `_evaluate_inner_core` (look for the graph match invocation; in v1.4 it is the part that produces a `source` rooted in the decision graph) |
| `hydrator_state_read` | any `engine.hydrated` / `_install_lazy_hydrator`-fed state read consumed during evaluate (read-only timing — do NOT touch the hydrator implementation) |
| `routing_dispatch` | the `route(...)` call + `_apply_profile_constraints` tail (governance.py around lines 412–425) — i.e. everything from `_evaluate_inner_core` return to the `_evaluate_inner` `return decision` |

Implementation rules:

1. **Extend, do not replace.** Add the five new keys to `timings` dict via `engine._last_phase_timings_ms`; do NOT remove or rename existing keys. The outer `evaluate_inner` aggregate timing stays — sub-phase keys land alongside it.
2. **Wall-clock only.** Use `_pc()` (perf_counter) consistent with v1.4 instrumentation. Multiply by 1000.0 for ms.
3. **Sub-phases sum approximately to `evaluate_inner`.** They will not sum exactly (interleaved Python overhead) — that is fine. Document the gap in the soak report block (P2 work).
4. **Zero verdict-path change.** Engine code edits are additive (new `_t = _pc(); ... ; timings[...] = ...` calls). Verdicts must be byte-identical. Add a regression test that runs a fixed input through the engine with and without the new timing capture and asserts equal `(action, confidence, reasoning, source)`.
5. **`_consult_learn_mode_bias` is OUT of scope.** Bias is consulted AFTER `_evaluate_inner` returns (already timed as `bias_consult`).

Soak driver work (`tools/soak_driver.py`):

1. Extend `_ALLOW_PHASE_ORDER` with the five new keys, inserted in logical order after `evaluate_inner`:
   ```
   "evaluate_inner",
   "og7_check",
   "fast_precheck",
   "graph_classify",
   "hydrator_state_read",
   "routing_dispatch",
   "bias_consult",
   ...
   ```
   Do NOT reorder pre-existing entries.

2. Add a second markdown block `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` rendered from the same `engine._last_phase_timings_ms` source. Same n / p50 / p95 / max columns. Header text references ADR-5 v1.4 §"Caveats" as the diagnosing target. Place it directly after the v1.4 `### ALLOW publish-path phase breakout (v1.4)` block in the report.

3. Keep the v1.4 block intact and producing the same numbers for back-compat with v1.4 baseline diffs.

New tests:
- `tests/test_governance_evaluate_inner_phase_timings.py` — assert all five new keys are populated on a representative ALLOW path; assert verdict equality vs a baseline run; assert `evaluate_inner` ≥ sum-of-sub-phases minus a small tolerance (sub-phases should not exceed parent).
- `tests/test_soak_driver_evaluate_inner_block.py` — synthesize a phase-timings stream containing the new keys; assert the new `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block renders with all five rows; assert the v1.4 block still renders unchanged.

## DOD

- [ ] Five new sub-phase keys (`og7_check`, `fast_precheck`, `graph_classify`, `hydrator_state_read`, `routing_dispatch`) populated on `engine._last_phase_timings_ms` for ALLOW envelopes
- [ ] No existing key removed or renamed
- [ ] Verdict path unchanged — regression test passes
- [ ] `tools/soak_driver.py` emits `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block; existing v1.4 block unchanged
- [ ] `_ALLOW_PHASE_ORDER` extended (not reordered)
- [ ] Two new tests pass; existing tests stay green
- [ ] `pytest -q` passes end-to-end
- [ ] `git --no-pager diff main..HEAD --stat` shows only intentionally added/modified files
- [ ] No protected-symbol drift

## Cassette + beacon coverage check

Per memory `feedback_cassette_must_cover_new_envelopes.md`: this phase does NOT add new bus envelope types — it adds new keys on an existing in-process attribute. No cassette extension required. Verify by grepping for new envelope `type=` strings in the diff:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py | grep -E '^\+.*type="[a-z_]+"'
```

Expect zero matches. If any new envelope type appears, STOP — extend `tools/cassette_record.py` and `tools/soak_driver.py` cassette coverage in this same PR before merging.

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `src/stream_manager/governance.py` (modified — additive timing capture only)
- `tools/soak_driver.py` (modified — `_ALLOW_PHASE_ORDER` extended + new render block)
- `tests/test_governance_evaluate_inner_phase_timings.py` (new)
- `tests/test_soak_driver_evaluate_inner_block.py` (new)

If diff shows any change to symbols in the do-not-touch table, STOP and report — likely silent-revert. Per memory `feedback_subagent_stale_mental_model.md`, run:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py tools/soak_driver.py
```

and read every hunk before opening the PR.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail, sample sub-phase numbers from a local 50-call probe (`tools/allow_phase_probe.py --n 50` or equivalent) so P2 has a sanity check before the ship-gate soak.
