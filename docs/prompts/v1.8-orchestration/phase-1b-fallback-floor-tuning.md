You are implementing **Phase P1b — Fallback floor tuning** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P1 (`feat/v1.8-content-detection-wiring`) shipped AND the local soak smoke recorded fallback fire rate > 30%. Haiku-first is mostly retrying on Sonnet, which means minimal latency win and possible quality loss; the floor is too tight.

## Branch + base

- Base: `main` with v1.8 P1 merged.
- PR target: `main`.
- Branch: `feat/v1.8-fallback-floor-tuning` (or operator's choice).
- If P1 is not merged, ABORT.
- If P1 fire rate ≤ 30%, this phase is moot — go straight to v1.8 P2.

## ⚠️ CRITICAL: Do-not-touch guard

The v1.7 P2 fallback floor surface is load-bearing. P1b touches ONLY:

- `src/stream_manager/cli_governance.py::FALLBACK_CONFIDENCE_DEFAULT` — change the default value (currently `0.70`)
- OR `src/stream_manager/governance.py` — narrow the destructive-pattern heuristic so fewer prompts mark `is_ambiguous_block=True`
- `tests/test_governance_fallback_routing.py` — update the test that asserts the floor default if changed
- `tests/test_governance_content_detection.py` — update unit tests if the heuristic narrows

Do NOT modify:
- `cli_governance.FALLBACK_CONFIDENCE_ENV` env-var name (operators rely on `BRIDGE_L4_FALLBACK_CONFIDENCE`)
- `_fallback_confidence_floor()` function shape
- The retry-path logic in `evaluate()` orchestrator
- Any v1.7 protected symbol per `docs/v1.8-task-plan.md` §"CRITICAL: do-not-touch list"

Pre-flight grep:

```
grep -nE 'FALLBACK_CONFIDENCE_DEFAULT|FALLBACK_CONFIDENCE_ENV|_fallback_confidence_floor|fallback_model_id|cli_dispatch_fallback_ms|governance_fallback_routed' src/stream_manager/cli_governance.py src/stream_manager/governance.py tests/test_governance_fallback_routing.py tests/test_governance_content_detection.py
```

If any symbol missing, STOP — silent-revert trap.

## Task brief

Fallback fire rate > 30% means one of two things:

1. **Floor too tight.** The 0.70 default catches too many primary-call results that Haiku would have answered confidently enough. Raise floor toward 0.80 / 0.85 so only genuinely-low-confidence Haiku verdicts retry on Sonnet.
2. **Heuristic too broad.** The destructive-pattern detection in `governance.py` is matching too liberally; non-destructive content gets marked `is_ambiguous_block=True` unnecessarily. Narrow the pattern list.

Triage step:
- Compute fallback fire rate split by content shape (which patterns triggered the most fallback fires?). If a single pattern dominates, that pattern is over-broad → fix 2.
- If fires distribute evenly across patterns AND most retries flip the verdict (Haiku and Sonnet disagree on action), Haiku is genuinely uncertain on this content → fix 1.
- If fires distribute evenly AND most retries do NOT flip the verdict (Haiku and Sonnet agree), the floor is too aggressive → fix 1, raise floor.

### Deliverables (depending on root cause)

**If fix 1 (raise floor):**
1. `src/stream_manager/cli_governance.py` — change `FALLBACK_CONFIDENCE_DEFAULT` from `0.70` to a tuned value (likely `0.80` or `0.85`).
2. `tests/test_governance_fallback_routing.py::test_a_confidence_at_floor_no_fire` — update the boundary value to match new default.
3. Re-run local soak smoke to verify fire rate dropped below 30%.

**If fix 2 (narrow heuristic):**
1. `src/stream_manager/governance.py` — remove or refine the over-triggering pattern(s) from the destructive-pattern list.
2. `tests/test_governance_content_detection.py` — add negative-control tests for the formerly-matching content (assert `is_ambiguous_block=False` now).
3. Re-run local soak smoke to verify fire rate dropped below 30%.

### Verdict-path invariant

When fallback does not fire, behavior MUST be identical to v1.8 P1. 550 fast-tier tests must stay green.

## DOD

- [ ] Triage step run; root cause documented in PR body (fix 1 vs fix 2)
- [ ] Corresponding deliverable shipped
- [ ] Re-soak smoke shows fallback fire rate < 30% AND `cli_dispatch_fallback_ms` p95 > 0 (lever still fires, just less often)
- [ ] 550 fast-tier tests stay passing
- [ ] No edits to `model_router.py`, `tools/soak_driver.py`, `dashboard/`, alignment-eval golden set, the cli_governance retry-path logic, or any v1.7 protected symbol
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1b ships:
- If re-soak smoke now shows fire rate == 0 (over-corrected): pivot back to `phase-1a-soak-prompt-coverage.md` to re-extend the corpus or re-widen the heuristic.
- If re-soak smoke shows fire rate ∈ [1%, 30%]: P2 (`phase-2-ship-gate-finalize.md`) is unblocked.

Report back when PR is open with: root cause classification, deliverable shipped, re-soak smoke fire rate (% + count), 550 fast-tier confirmation.
