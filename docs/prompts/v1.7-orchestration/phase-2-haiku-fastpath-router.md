You are implementing **Phase P2 — Haiku fastpath router** from the streamManager v1.7 cycle.

## Branch + base

- Base: `main` with P1 (`feat/v1.7-alignment-eval-harness`) merged AND green baseline committed.
- PR target: `main`.
- Branch: `feat/v1.7-haiku-fastpath-router` (or operator's choice).
- If P1 is not merged, ABORT — P2 router change requires the alignment-eval harness as the CI ship-blocker per v1.7 backlog.
- If P1 baseline (`reports/alignment-eval-*Z.md` against v1.6 router config) is not green (control column < 95% or > 5% unstable rows), ABORT — P1's mint rule must fire first.

## ⚠️ CRITICAL: Do-not-touch guard

The following symbols are load-bearing. P2 may extend them additively but MUST NOT replace the existing surface or reorder priority bands.

| From task | File | Symbols/sections |
|-----------|------|------------------|
| J (v1.1) | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, `CliWorker.send`, `CliPool.acquire` |
| v1.4 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.4 keys |
| v1.5 P1 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.5 sub-phase keys; `_sub_timings_in_flight` |
| v1.6 P1 | `src/stream_manager/governance.py` | `_last_phase_timings_ms` v1.6 CLI residue keys |
| v1.6 P1 | `src/stream_manager/cli_governance.py` | `CliGovernor.evaluate` `sub_timings: dict | None = None` kwarg |
| v1.4 + v1.5 + v1.6 | `tools/soak_driver.py` | `_ALLOW_PHASE_ORDER` (extend, never reorder), `_format_allow_phase_breakout`, all three ALLOW breakout blocks |
| v1.1 NFR-M2 | `src/stream_manager/cli_governance.py` | `CliGovernor.evaluate` outer signature (positional `content`, kwarg `model_id`) — extend with optional kwargs only |
| NFR-M1-M5 | `src/stream_manager/model_router.py` | `route()` priority order (alignment > L0 > L1 > L2 > L3) — extend within an existing band, never reorder |
| NFR-M4 | `src/stream_manager/model_router.py` | `ConvergenceMonitor` — do not modify |

Pre-flight grep:

```
grep -nE 'CliPool|CliWorker|cli_setup_ms|cli_pool_send_ms|cli_pool_acquire_ms|cli_dispatch_ms|cli_parse_ms|sub_timings|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|RoutingDecision|ConvergenceMonitor|requires_alignment|is_ambiguous_block|is_hitl_synthesis|get_l2_model|get_l4_model' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP and report — likely silent-revert trap.

## Task brief

v1.6 ship-gate localised the `_evaluate_inner` p95 tail to `cli_pool_send_ms` p95 = 6328.07 ms (~99.98% of `evaluate_inner` p95). The dominant cost is upstream Anthropic model TTFT/decode latency. v1.7 P2 attacks this by widening the Haiku surface in `model_router.route` so more L4 ambiguous-BLOCK and HITL synthesis envelopes ride Haiku instead of Sonnet — with a confidence-gated Sonnet fallback. FR-OG-7 alignment cells STAY on Sonnet (no downgrade); P1's alignment-eval gate enforces this.

### Deliverables

1. **`src/stream_manager/model_router.py`** — additive extension of `route()` and `RoutingDecision`:

   - Add field `RoutingDecision.fallback_model_id: str | None = None`. Existing callers see `None` and behave as v1.6.
   - Update `route()` L4 branch (the `if requires_alignment or is_ambiguous_block or is_hitl_synthesis` block at lines ~80–82). Replace the single-return with a sub-band:
     - `requires_alignment` is True → `RoutingDecision(L4, get_l4_model())` — Sonnet only, no fallback (FR-OG-7 protected).
     - `is_ambiguous_block` is True (and not `requires_alignment`) → `RoutingDecision(L4, get_l2_model(), fallback_model_id=get_l4_model())` — Haiku-first with Sonnet fallback.
     - `is_hitl_synthesis` is True (and not `requires_alignment`) → `RoutingDecision(L4, get_l2_model(), fallback_model_id=get_l4_model())` — Haiku-first with Sonnet fallback.
   - Priority order is preserved exactly: alignment > L0 > L1 > L2 > L3. Only the L4 internal model selection is branched.
   - Add a docstring block under `route()` describing the new sub-band.
   - `ConvergenceMonitor.record()` is unchanged — the L4 layer is unchanged; only the model_id within L4 differs.

2. **`src/stream_manager/cli_governance.py`** — additive extension of `CliGovernor.evaluate`:

   - Accept a new optional kwarg `fallback_model_id: str | None = None`. When non-None AND the primary call's verdict confidence is below an env-configurable floor `BRIDGE_L4_FALLBACK_CONFIDENCE` (default `0.70`), retry once with `model_id=fallback_model_id`. Use the retry's verdict as the final answer.
   - Populate `cli_dispatch_fallback_ms` into the caller-provided `sub_timings` dict (additive new key). Value: `0.0` when no fallback fires; wall-clock duration of the retry call when fallback fires.
   - Add a guard: if the primary call returns confidence ≥ floor OR if `fallback_model_id is None`, no retry — `cli_dispatch_fallback_ms = 0.0`.
   - Fallback path emits a new bus envelope `governance_fallback_routed` with payload `{primary_model, fallback_model, primary_confidence, fallback_confidence, fallback_ms}`. Use the existing `_publish_event` machinery; do NOT add new publish helpers.

3. **`src/stream_manager/governance.py`** — caller threading:

   - In `_maybe_cli_evaluate`, read `RoutingDecision.fallback_model_id` from the routing call and pass it through to `CliGovernor.evaluate(...)` alongside `model_id` and `sub_timings`.
   - Add `cli_dispatch_fallback_ms` to the `_last_phase_timings_ms` dict surface (additive — same pattern as the v1.6 keys).

4. **`tools/soak_driver.py`** — additive extension of `_ALLOW_PHASE_ORDER`:

   - Append `cli_dispatch_fallback_ms` AFTER `cli_parse_ms` in the v1.6 CLI residue block (do NOT reorder existing entries).
   - The `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block now renders 6 rows. Block header text and table columns (n / p50 / p95 / max) unchanged.
   - Suppress `cli_dispatch_fallback_ms` row for pre-v1.7 streams (any record missing the key).

5. **Cassette + beacon coverage** (memory: `feedback_cassette_must_cover_new_envelopes.md`):

   - `tools/cassette_record.py` gains pairs that exercise the new `governance_fallback_routed` envelope. Record from a real CLI run (memory: `feedback_cli_over_sdk.md`), not synthetic.
   - Update any `tests/beacons/` JSONL that lists the canonical envelope set so the new envelope is recognised by the soak driver / cassette replay.

6. **Tests**:

   - `tests/test_governance_fallback_routing.py`:
     - (a) ambiguous-BLOCK row with primary confidence ≥ floor stays on Haiku, no fallback fire, `cli_dispatch_fallback_ms == 0.0`, no `governance_fallback_routed` envelope emitted.
     - (b) ambiguous-BLOCK row with primary confidence < floor triggers Sonnet retry, `cli_dispatch_fallback_ms > 0`, exactly one `governance_fallback_routed` envelope.
     - (c) FR-OG-7 alignment row (`requires_alignment=True`) NEVER sees the fallback path. `fallback_model_id is None` on the routing decision; `cli_dispatch_fallback_ms == 0.0`; primary call uses Sonnet end-to-end.
     - (d) Verdict equality: ambiguous-BLOCK on Haiku-only (no fallback fire) matches a v1.6 baseline run on Sonnet for the same prompt within the alignment-eval ≥ 95% threshold (use the P1 golden-set fixtures).
   - `tests/test_model_router_l4_subband.py`:
     - Asserts the L4 sub-band priority: `requires_alignment=True` always returns Sonnet with no fallback; `is_ambiguous_block=True` (alone) returns Haiku with Sonnet fallback; `is_hitl_synthesis=True` (alone) returns Haiku with Sonnet fallback; the priority order alignment > L0 > L1 > L2 > L3 is unchanged.
   - `tests/test_soak_driver_v17_residue_block.py`:
     - Synthesize a phase-timings stream containing `cli_dispatch_fallback_ms`; assert the 6th row renders correctly in the v1.6 CLI residue block; assert pre-v1.7 streams (missing the key) suppress the row; assert v1.4 + v1.5 + v1.6 blocks still render unchanged.

7. **CI alignment-eval gate**:

   - Wire `python tools/alignment_eval.py --ci-gate` into the PR CI step. The gate must run with the merged P2 router config (i.e. against the new Haiku fastpath path) and exit zero before merge.
   - If the gate fires on any FR-OG-7 row (`model_floor == "sonnet"`): STOP. Per the abandonment rule in `docs/v1.7-task-plan.md`, this is the trigger to abandon Haiku fastpath and rewrite P2 as `phase-2-pool-sizing-burst-tier.md`.
   - If the gate fires on a non-FR-OG-7 row (ambiguous-BLOCK or HITL synthesis): triage — either widen the fallback floor (raise `BRIDGE_L4_FALLBACK_CONFIDENCE`), narrow the Haiku surface, or accept the regression with explicit ADR-5 §"Caveats" entry in P3. Do NOT relax the gate for FR-OG-7 rows.

### Verdict-path invariant

`model_router` additive (new optional dataclass field; new branch internal to L4 — no priority reorder); `cli_governance` additive (new optional kwarg + retry path triggered only when `fallback_model_id is not None` AND confidence < floor); engine timings additive (new key). Verdicts on the unchanged surface (alignment-only rows, precheck, high-confidence graph, L2/L3 graph misses) MUST be byte-identical to v1.6.

### Soak driver flag invariant

`--cli-pool-size 2` MUST remain the ship-gate default (memory: `feedback_soak_cli_pool_flag.md`). The new instrumentation must populate cleanly on both pool-path and spawn-path so a future `--cli-pool-size 0` diagnostic run still produces a valid CLI residue block.

### Cross-PR seam

The P2 writers (`model_router` field, `cli_governance` retry, `governance` thread-through, `_last_phase_timings_ms` key) ↔ P3 readers (soak driver block, ADR-5 v1.7 baseline table) must agree on the new `cli_dispatch_fallback_ms` key + `governance_fallback_routed` envelope. Verify before merge per memory `feedback_cross_pr_seam_review.md`.

## DOD

- [ ] `model_router.RoutingDecision.fallback_model_id` field added; `route()` L4 sub-band branched per spec
- [ ] `CliGovernor.evaluate` accepts `fallback_model_id` kwarg; retry path active when primary confidence < `BRIDGE_L4_FALLBACK_CONFIDENCE` (default `0.70`)
- [ ] `governance_fallback_routed` envelope wired through `_publish_event`; cassette + beacon updated SAME PR
- [ ] `cli_dispatch_fallback_ms` key added to `_last_phase_timings_ms`; soak driver `_ALLOW_PHASE_ORDER` extended; v1.6 CLI residue block renders 6 rows
- [ ] All four test files pass: `test_governance_fallback_routing`, `test_model_router_l4_subband`, `test_soak_driver_v17_residue_block`, `tests/test_alignment_eval_harness` (P1 — still green under v1.7 router)
- [ ] CI alignment-eval `--ci-gate` runs on the PR and exits zero on FR-OG-7 rows
- [ ] No protected-symbol drift — pre-flight grep clean post-merge
- [ ] No reordering of `model_router.route` priority bands
- [ ] No reordering of `_ALLOW_PHASE_ORDER` existing entries
- [ ] Single PR against `main`

## Mint-new-phase rule

After P2 ships, scan for follow-ups before P3 cuts:
- If `--ci-gate` regressed on FR-OG-7 rows during development: ABANDON Haiku fastpath. Replace P2 PR with `phase-2-pool-sizing-burst-tier.md`. Open v1.8 backlog item to retry Haiku fastpath after sync-comms v1.0 lands.
- If fallback fire rate during local soak appears unexpectedly high (> 30% of L4 ambiguous-BLOCK / HITL synthesis rows): mint `phase-2a-fallback-floor-tuning.md` BEFORE P3 cuts. Tune `BRIDGE_L4_FALLBACK_CONFIDENCE` floor, narrow the Haiku surface, or both.
- If new bus envelope test coverage is incomplete (cassette grep does not surface `governance_fallback_routed`): mint `phase-2b-cassette-coverage-fix.md`.

Report back when PR is open with: PR URL, diff stat, alignment-eval CI gate result (control vs candidate pass rates, regressing-row count, FR-OG-7 row gate result), local fallback fire-rate sample.
