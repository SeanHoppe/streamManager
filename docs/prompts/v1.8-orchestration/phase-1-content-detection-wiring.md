You are implementing **Phase P1 — Content-detection wiring** from the streamManager v1.8 cycle.

> **Historical record — partially ripped at v2.0 P3.** The pre-CLI
> dispatch-site consumer of `is_ambiguous_block` / `is_hitl_synthesis`
> (the route() kwargs) was decommissioned at v2.0 P3 — see
> `docs/adr/ADR-18-mvp-surface-freeze.md` §"Decommissioned".
> Content-detection helpers (`_looks_ambiguous_block`,
> `_looks_hitl_synthesis`, `_AMBIGUOUS_BLOCK_PATTERNS`) wired by this
> phase remain FROZEN per ADR-18 §"Initial classification" and may be
> reused by future work. This prompt is preserved for history; do not
> use it as a do-not-touch reference for current work.

## Branch + base

- Base: `main` with v1.8 P0 (`docs/v1.8-cycle-frame`) merged.
- PR target: `main`.
- Branch: `feat/v1.8-content-detection-wiring` (or operator's choice).
- If P0 is not merged, ABORT (the task plan + phase prompts must be on `main` first so the cycle is self-documenting).

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1 + v1.2 + v1.3 + v1.4 + v1.5 + v1.6 + v1.7 protected-symbol set in `docs/v1.8-task-plan.md` §"CRITICAL: do-not-touch list" applies. P1 must touch ONLY:

- `src/stream_manager/governance.py` — pre-routing call site (`_evaluate_inner_core`); helper additions for content-detection
- `tests/test_governance_content_detection.py` (NEW)

NO edits to `model_router.py`, `cli_governance.py`, `tools/soak_driver.py`, `dashboard/`, or any v1.7 / earlier protected symbol. The v1.7 P2 router + retry surface is reused as-is — wiring change is callsite-only.

Pre-flight grep:

```
grep -nE 'CliPool|CliWorker|RoutingDecision|fallback_model_id|cli_dispatch_fallback_ms|FALLBACK_CONFIDENCE|_publish_bus_message|_parse_envelope_with_meta|_evaluate_once|governance_fallback_routed|governance_envelope_missing_confidence|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|_consult_learn_mode_bias' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP — likely silent-revert trap.

## Task brief

v1.7 P2 shipped the L4 sub-band Haiku-fastpath router infrastructure (`RoutingDecision.fallback_model_id` field + `CliGovernor.evaluate(fallback_model_id=...)` retry path + `governance_fallback_routed` + `governance_envelope_missing_confidence` envelopes + `cli_dispatch_fallback_ms` timing key). v1.7 P3 ship-gate (`reports/soak-20260505T125741Z.md`) recorded **0 fallback fires across 60 events** because the production caller path at `src/stream_manager/governance.py::_evaluate_inner_core` (search for `pre_routing = route(...)`) sets both `is_ambiguous_block` and `is_hitl_synthesis` to `False` unconditionally. The L4 sub-band's Haiku-fastpath branch is therefore unreachable from production code; lever effect cannot be measured.

P1 wires the content-detection seam so the lever fires.

### Deliverables

1. **`src/stream_manager/governance.py`** — wire content-detection at the pre-routing site:

   - **`is_ambiguous_block` heuristic.** Compute from content. Pick one or layer two:
     - regex match on a curated destructive-pattern list (`rm -rf`, `git push --force` / `git push -f`, `drop table`, `truncate`, `delete from`, `chmod 777`, `:(){:|:&};:`, etc.) at low precheck confidence (precheck did not hit but content has destructive intent)
     - learn-mode bias hit on a "likely-block" pattern
     - existing `_classify_ops` machinery if it surfaces destructive-action signal pre-CLI
     - The pattern list lives next to existing precheck patterns or in a new module-private constant; make the source-of-truth singular so it does not drift
   - **`is_hitl_synthesis`.** Thread the existing HITL classify trigger surface (the signal that already gates the `hitl_classify_trigger` timing key) into the pre-routing call. If HITL synthesis context is the active path, set the flag True.
   - **Pre_routing call update.** Pass the computed flags. `requires_alignment` stays untouched. Routing precedence (alignment > L0 > L1 > L2 > L3) is enforced inside `model_router.route()` — do NOT replicate the precedence check at the call site.

2. **Tests:**

   - `tests/test_governance_content_detection.py` (NEW) — unit tests:
     - destructive-pattern content sets `is_ambiguous_block=True` AND `pre_routing.fallback_model_id == get_l4_model()`
     - non-destructive content keeps `is_ambiguous_block=False` AND `pre_routing.fallback_model_id is None` (v1.7 dormant default)
     - HITL synthesis context sets `is_hitl_synthesis=True` AND fallback wiring active
     - alignment-required content keeps `requires_alignment=True` AND `fallback_model_id is None` regardless of the other two flags (FR-OG-7 protected — `requires_alignment` always wins per `model_router.route()`)
     - Scenario coverage for the heuristic patterns: at minimum 5 destructive patterns + 5 negative controls (non-destructive prose / non-action narration / clear ALLOW)
   - Existing v1.7 fast-tier tests MUST stay green: `tests/test_governance_fallback_routing.py`, `tests/test_model_router_l4_subband.py`, `tests/test_cli_governance.py`, `tests/test_model_router.py`, `tests/test_soak_driver_v17_residue_block.py`, `tests/test_alignment_eval_harness.py` (schema test, not the smoke test).

3. **Alignment-eval `--ci-gate`.** Re-run against the new wiring (real `claude -p`, ~42 min). Must exit 0 on FR-OG-7 rows. Attach the report. Verify exactly 0 FR-OG-7 regressions (`requires_alignment` keeps them on Sonnet — by construction the wiring should not regress FR-OG-7).

4. **Local soak smoke** — drive a short cassette/soak run (`tools/soak_driver.py --cli-pool-size 2 --total-seconds 600` or similar short tier) with content that should trigger fallback (curated destructive prompts in the L2/L3/L4 mix). Verify in the resulting report:
   - `cli_dispatch_fallback_ms` p95 > 0 (proves the lever fires)
   - At least one `governance_fallback_routed` envelope captured in the dashboard log (cassette schema unchanged — bus envelopes are out-of-cassette by design; verify via dashboard log or bus message capture mechanism)
   - Fallback fire rate < 30% on the load mix (per `docs/v1.8-backlog.md` risk paragraph)

### Verdict-path invariant

When BOTH new flags are False (the v1.7 default state), behavior MUST be byte-identical to v1.7:
- `pre_routing.fallback_model_id is None`
- `_maybe_cli_evaluate(fallback_model_id=None)`
- Same evaluate path, same residue keys, same envelope counts

550 fast-tier tests must stay passing. Run `pytest tests/ -m "not slow and not alignment_eval" -q` and confirm PASS.

### No new bus envelopes

P1 reuses v1.7 P2 envelopes (`governance_fallback_routed`, `governance_envelope_missing_confidence`). Verify by grep:

```
grep -rn 'governance_' src/stream_manager/ | grep -v 'governance_call\|governance_fallback_routed\|governance_envelope_missing_confidence'
```

Should return zero matches outside legitimate code paths.

### Cassette + beacon

Cassette format does not capture bus envelopes (decision-output records only). Verified at v1.7 P2. No cassette edit required for P1.

### Memory feedback applied

- `feedback_subagent_stale_mental_model.md` — pre-flight grep before any edit
- `feedback_cli_over_sdk.md` — alignment-eval `--ci-gate` drives real `claude -p`
- `feedback_subagent_long_task_abandonment.md` — `--ci-gate` (~42 min) launched from main thread w/ `run_in_background` + `ScheduleWakeup`
- `feedback_cassette_must_cover_new_envelopes.md` — verified P1 introduces NO new envelopes (reuses v1.7 P2)
- `feedback_cross_pr_seam_review.md` — verify the wiring (governance content-detection) ↔ v1.7 P2 router (RoutingDecision.fallback_model_id branch) ↔ v1.7 P2 cli_governance (retry path) lights up end-to-end via the local soak smoke

## DOD

- [ ] `src/stream_manager/governance.py` pre-routing call site computes both flags from content + HITL state
- [ ] `tests/test_governance_content_detection.py` exists; all scenarios pass
- [ ] `pytest tests/ -m "not slow and not alignment_eval" -q` → all pass (no v1.7 regression)
- [ ] Alignment-eval `--ci-gate` baseline run: exit 0, 0 FR-OG-7 regressions, report attached
- [ ] Local soak smoke shows `cli_dispatch_fallback_ms` p95 > 0 AND ≥ 1 `governance_fallback_routed` envelope emitted
- [ ] No edits to `model_router.py`, `cli_governance.py`, `tools/soak_driver.py`, `dashboard/`, or any v1.7 protected symbol — verify with `git --no-pager diff origin/main..HEAD --stat -- src/stream_manager/cli_pool.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py dashboard`
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1 ships, scan the local soak smoke before ticking:
- If `cli_dispatch_fallback_ms` p95 == 0 OR no `governance_fallback_routed` envelope captured: the heuristic did not match the soak content — mint `phase-1a-soak-prompt-coverage.md` (extend soak load mix with destructive content OR widen heuristic patterns) BEFORE P2 cuts.
- If fallback fire rate > 30% on the smoke: mint `phase-1b-fallback-floor-tuning.md` (raise `BRIDGE_L4_FALLBACK_CONFIDENCE` floor or narrow Haiku surface) BEFORE P2 cuts.
- If alignment-eval `--ci-gate` fires on FR-OG-7 rows (which should be impossible because `requires_alignment` keeps them on Sonnet): ABORT — wiring has corrupted the routing precedence; debug `model_router.route()` priority or the call-site flag-passing.
- If neither: P2 (`phase-2-ship-gate-finalize.md`) is unblocked.

Report back when PR is open with: PR URL, diff stat, alignment-eval gate result, local soak smoke summary (fallback fire count + percent + cli_dispatch_fallback_ms p95).
