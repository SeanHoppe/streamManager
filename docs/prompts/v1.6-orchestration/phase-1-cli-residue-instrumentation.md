You are implementing **Phase P1 — `_evaluate_inner` CLI residue instrumentation** from the streamManager v1.6 cycle.

## Branch + base

- Base: `main` (v1.5.0 tagged at `95ffb83`).
- PR target: `main`.
- Branch: `feat/v1.6-cli-residue-timings` (or operator's choice).
- If `main` is unexpectedly behind v1.5.0, ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

The following symbols are load-bearing. Verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, `CliWorker.send`, `CliPool.acquire`, `.bridge/cli-pool.pids` |
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
| v1.4 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.4 keys (`inbound_publish`, `evaluate_inner`, `bias_consult`, `hitl_classify_trigger`, `hitl_route`, `record_decision`, `alert_publish`, `total`) |
| v1.5 P1 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.5 sub-phase keys (`og7_check`, `fast_precheck`, `graph_classify`, `hydrator_state_read`, `routing_dispatch`); `_sub_timings_in_flight` transient slot |
| v1.4 + v1.5 | `tools/soak_driver.py` | `_ALLOW_PHASE_ORDER` (extend, never reorder existing entries), `_format_allow_phase_breakout`, `### ALLOW publish-path phase breakout (v1.4)` block, `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block |
| v1.1 NFR-M2 | `src/stream_manager/cli_governance.py` | `CliGovernor.evaluate` outer signature (positional `content`, kwarg `model_id`) and pool-path / spawn-path branching — **extend with optional kwargs only**, never reorder branches or alter return-type contract |

Pre-flight grep:

```
grep -nE 'CliPool|CliWorker|_install_lazy_hydrator|_run_sse|matched_hash|--cli-replay|LifecycleBridge|_VALID_TRANSPORTS|Literal\["wirecli"\]|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|_consult_learn_mode_bias|_sub_timings_in_flight' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/desktop_command_consumer.py src/stream_manager/lifecycle_bridge.py src/stream_manager/cli_client.py tools/soak_driver.py
```

If any symbol missing, STOP and report — likely silent-revert trap.

## Task brief

v1.5 ship-gate (`reports/soak-20260504T201714Z.md`) FALSIFIED the v1.4 sub-phase-tail hypothesis. ALLOW p95 = 5.60 s, of which the five v1.5 sub-phases sum to **0.13 ms p95** vs `evaluate_inner` p95 = **5599 ms**. ~99.998% of the ALLOW tail lives in code paths NOT covered by v1.5 instrumentation. The driver is most plausibly the synchronous `cli_pool` round-trip on the escalation branch (precheck miss + graph miss → `_maybe_cli_evaluate` → `CliGovernor.evaluate` → `pool.acquire()` → `worker.send()` → response). ADR-5 v1.5 §"Caveats" calls for residue-level instrumentation so the next ship-gate can localize the tail to a specific component (model wall-clock vs pool acquisition vs CLI parse) before any v1.7 lever is chosen.

Implement five sub-phase wall-clocks across `_maybe_cli_evaluate` (governance.py) and `CliGovernor.evaluate` (cli_governance.py):

| Sub-phase key | Spans |
|---|---|
| `cli_setup_ms` | entry of `_maybe_cli_evaluate` (governance.py ~line 970) → just before `CliGovernor.evaluate(...)` invocation. Covers lazy `CliGovernor()` construction (when `self._cli_governor is None`) and `_system_prompt()` cache build on first call. |
| `cli_dispatch_ms` | full duration of `CliGovernor.evaluate(...)` from caller's perspective: entry → return. Captured in `_maybe_cli_evaluate` around the `self._cli_governor.evaluate(...)` call. |
| `cli_pool_acquire_ms` | duration of `with self._pool.acquire() as worker:` block enter → exit (cli_governance.py ~line 214). Pool-path only. Spawn-path: emit `0.0`. |
| `cli_pool_send_ms` | duration of `worker.send(pool_prompt, timeout=TIMEOUT_SECONDS)` (cli_governance.py ~line 215). Pool-path: covers stdin write + stdout drain wait until `result` envelope. Spawn-path: covers `subprocess.run(...)` round-trip (cli_governance.py ~line 245). |
| `cli_parse_ms` | duration of `_extract_usage(stdout)` + `_parse_envelope(stdout)` on success path (cli_governance.py ~lines 217 + 228 pool-path; ~lines 284 + after spawn-path). Both paths populate. |

**Branches that do NOT call the CLI** (precheck-hit, high-confidence graph match in `_evaluate_inner_core`; FR-OG-7 override in `_evaluate_inner`; FR-AR-6 blocked-op short-circuit in `_evaluate_inner`) MUST emit each of the five new keys with value `0.0` so soak rows are dense and percentile math is honest about the precheck-hit ratio.

Implementation rules:

1. **Extend, do not replace.** Add the five new keys to `engine._last_phase_timings_ms` via the v1.5 `_sub_timings_in_flight` transient-slot mechanism. Do NOT remove or rename existing keys. The v1.4 + v1.5 keys land alongside the new ones.

2. **Wall-clock only.** Use `_pc()` (perf_counter) consistent with v1.4 + v1.5 instrumentation. Multiply by 1000.0 for ms.

3. **`CliGovernor.evaluate` signature extension.** Add an optional kwarg:
   ```python
   def evaluate(
       self,
       content: str,
       model_id: str | None = None,
       sub_timings: dict[str, float] | None = None,
   ) -> CliDecision | None:
   ```
   When `sub_timings` is None, behavior is identical to v1.5 (back-compat for existing tests/callers). When non-None, populate `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`, `cli_parse_ms` into the dict from the appropriate timing capture sites.

4. **Caller wiring.** In `governance._maybe_cli_evaluate` (governance.py ~line 970):
   - Capture `_t = _pc()` at function entry.
   - Read `sub = self._sub_timings_in_flight` (the v1.5 transient slot). If non-None, treat as the destination dict; if None, use a local throwaway dict (defensive — `_maybe_cli_evaluate` may be called outside `_evaluate_inner` in tests).
   - Set `sub["cli_setup_ms"] = (_pc() - _t) * 1000.0` immediately before the `self._cli_governor.evaluate(...)` call.
   - Pass `sub_timings=sub` to `evaluate(...)`.
   - Branches that return early WITHOUT calling the CLI (e.g. `_cli_enabled()` False) MUST set all five new keys to `0.0` on `sub`.

5. **Caller-side `0.0` defaults.** In `_evaluate_inner` and `_evaluate_inner_core`, every return path that does NOT traverse `_maybe_cli_evaluate` MUST pre-populate the five new keys with `0.0` on `sub_timings` before the call to `_record_sub_phase_timings`. Pattern: define a small helper `_zero_cli_residue_keys(sub: dict)` near the v1.5 sub-phase capture site and invoke it on every non-CLI branch (FR-OG-7 hit, FR-AR-6 blocked-op, precheck hit, graph high-confidence hit, default ALLOW with no CLI).

6. **Sub-phases sum approximately to `cli_dispatch_ms` on the pool-path.** They will not sum exactly (`cli_dispatch_ms` includes `_publish_event` + Python overhead). That is fine. Document the gap in the soak report block (P2 work).

7. **Zero verdict-path change.** Engine + cli_governance edits are additive (new dict keys, new optional kwarg). Verdicts must be byte-identical to v1.5. Add a regression test that runs a fixed input through the engine with and without the new timing capture and asserts equal `(action, confidence, reasoning, source)`.

8. **Pool path ordering.** Capture `cli_pool_acquire_ms` strictly around `with self._pool.acquire() as worker:` enter → exit (NOT including `worker.send`). Capture `cli_pool_send_ms` strictly around the `worker.send(...)` call inside the `with` block. They are siblings, not nested — `cli_pool_acquire_ms` is the wait-for-worker time, `cli_pool_send_ms` is the model round-trip.

9. **Spawn path mapping.** `cli_pool_acquire_ms = 0.0`. `cli_pool_send_ms` covers `subprocess.run(cmd, ...)`. `cli_parse_ms` covers `_extract_usage` + (success-path only) eventual `_parse_envelope` if you choose to parse-on-success in this PR; if `_parse_envelope` is called outside the timed region, document that as a known gap.

Soak driver work (`tools/soak_driver.py`):

1. Extend `_ALLOW_PHASE_ORDER` with the five new keys, inserted in logical order **after `routing_dispatch`** (NOT inside the v1.5 sub-phase block — they form a new block):
   ```
   "evaluate_inner",
   "og7_check",
   "fast_precheck",
   "graph_classify",
   "hydrator_state_read",
   "routing_dispatch",
   "cli_setup_ms",
   "cli_dispatch_ms",
   "cli_pool_acquire_ms",
   "cli_pool_send_ms",
   "cli_parse_ms",
   "bias_consult",
   ...
   ```
   Do NOT reorder pre-existing entries.

2. Add a third markdown block `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` rendered from the same `engine._last_phase_timings_ms` source. Same n / p50 / p95 / max columns. Header text references ADR-5 v1.5 §"Caveats" as the diagnosing target. Place it directly after the v1.5 sub-phase block in the report.

3. Suppress the new block for pre-v1.6 streams (any record that lacks all five new keys). The v1.4 + v1.5 blocks must still render unchanged on the same input.

New tests:
- `tests/test_governance_cli_residue_timings.py` — assert all five new keys are populated on the CLI escalation branch (precheck=None, graph=None, CLI enabled with a stubbed `CliGovernor` runner that returns a synthetic envelope); assert all five are `0.0` on a precheck-hit branch; assert verdict equality vs a baseline run; assert `cli_dispatch_ms` ≥ `cli_pool_send_ms` (parent ≥ child) on the pool-path; assert v1.4 + v1.5 keys still present.
- `tests/test_soak_driver_cli_residue_block.py` — synthesize a phase-timings stream containing the new keys; assert the new `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block renders with all five rows in canonical code-path order; assert the v1.4 + v1.5 blocks still render unchanged on the same input; assert suppression for pre-v1.6 streams.

## DOD

- [ ] Five new sub-phase keys (`cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`, `cli_parse_ms`) populated on `engine._last_phase_timings_ms` for ALLOW envelopes that traverse the CLI escalation branch
- [ ] All five new keys populated as `0.0` on non-CLI branches (precheck-hit, graph-high-confidence-hit, FR-OG-7 hit, FR-AR-6 blocked-op)
- [ ] `CliGovernor.evaluate` accepts optional `sub_timings: dict | None = None` kwarg; default-None behavior byte-identical to v1.5
- [ ] No existing v1.4 / v1.5 key removed or renamed
- [ ] Verdict path unchanged — regression test passes
- [ ] `tools/soak_driver.py` emits `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block; existing v1.4 + v1.5 blocks unchanged
- [ ] `_ALLOW_PHASE_ORDER` extended (not reordered)
- [ ] Two new tests pass; existing tests stay green
- [ ] `pytest -q` passes end-to-end
- [ ] `git --no-pager diff main..HEAD --stat` shows only intentionally added/modified files
- [ ] No protected-symbol drift

## Cassette + beacon coverage check

Per memory `feedback_cassette_must_cover_new_envelopes.md`: this phase does NOT add new bus envelope types — it adds new keys on an existing in-process attribute. The `governance_call` envelope already emitted by `CliGovernor._publish_event` does NOT gain new fields. No cassette extension required. Verify by grepping for new envelope `type=` strings in the diff:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py src/stream_manager/cli_governance.py | grep -E '^\+.*type="[a-z_]+"'
```

Expect zero matches. If any new envelope type appears, STOP — extend `tools/cassette_record.py` and `tools/soak_driver.py` cassette coverage in this same PR before merging.

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `src/stream_manager/governance.py` (modified — additive timing capture + caller wiring only)
- `src/stream_manager/cli_governance.py` (modified — additive `sub_timings` kwarg + capture sites only)
- `tools/soak_driver.py` (modified — `_ALLOW_PHASE_ORDER` extended + new render block)
- `tests/test_governance_cli_residue_timings.py` (new)
- `tests/test_soak_driver_cli_residue_block.py` (new)

If diff shows any change to symbols in the do-not-touch table, STOP and report — likely silent-revert. Per memory `feedback_subagent_stale_mental_model.md`, run:

```
git --no-pager diff origin/main..HEAD -- src/stream_manager/governance.py src/stream_manager/cli_governance.py tools/soak_driver.py
```

and read every hunk before opening the PR.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail, sample CLI residue numbers from a local 50-call probe (use `tools/allow_phase_probe.py --n 50` against a recorded cassette or a stubbed `CliGovernor` runner — do NOT hit the live CLI for the probe; the soak in P2 is the live measurement) so P2 has a sanity check before the ship-gate soak.
