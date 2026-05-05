You are implementing **Phase P2c — Ship-gate fallback floor tuning** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P2 (`ship/v1.8-shipgate-finalize`) Tier-3 ship-gate soak recorded fallback fire rate > 30% on L4 ambig-BLOCK / HITL synthesis rows. Haiku-first is mostly retrying on Sonnet at ship-gate scale, despite v1.8 P1 local smoke being under the 30% threshold.

## Branch + base

- Base: `main` with v1.8 P1 merged.
- PR target: `main`.
- Branch: `feat/v1.8-shipgate-floor-tuning` (or operator's choice).
- BLOCKS v1.8 P2 ADR-5 update — do NOT update ADR-5 with the over-firing baseline; the lever signal is muddied.

## ⚠️ CRITICAL: Do-not-touch guard

Same surface as `phase-1b-fallback-floor-tuning.md`:

- `src/stream_manager/cli_governance.py::FALLBACK_CONFIDENCE_DEFAULT` — change default value
- OR `src/stream_manager/governance.py` — narrow heuristic
- `tests/test_governance_fallback_routing.py::test_a_confidence_at_floor_no_fire` — update if floor changed
- `tests/test_governance_content_detection.py` — update if heuristic narrowed

Do NOT modify `_fallback_confidence_floor()` shape, `FALLBACK_CONFIDENCE_ENV` name, or any v1.7 protected symbol.

## Task brief

P1b handled the LOCAL soak smoke fire rate. P2c handles the SHIP-GATE Tier-3 soak fire rate, which uses the standard 60-event load mix. Possible reasons P1b did not catch this:

1. **Local smoke load mix was not representative.** The curated destructive prompts at P1b had different confidence distributions than the ship-gate load. Fix: tune floor based on ship-gate distribution (likely raise floor — Sonnet retries are firing on prompts that Haiku is actually answering competently).
2. **Heuristic too broad on ship-gate prompts.** The destructive-pattern list catches prompts that aren't really destructive in the ship-gate L4 / L2/L3 mix. Fix: narrow the pattern list (P1a/P1b lessons inverted — there the fix was to widen / extend; at P2c the load mix is fixed, so narrow the heuristic instead).

### Triage

```
grep -E 'governance_fallback_routed' tmp/soak-dashboard-<latest-shipgate-timestamp>.log | head -20
```

Inspect the metadata: `primary_model`, `primary_confidence`, `fallback_confidence`, which prompts triggered, did the verdicts agree (fallback was unnecessary) or differ (fallback was justified)?

- If MOST fallback fires resulted in agreement (Haiku and Sonnet returned the same action): the floor is too aggressive. Raise floor.
- If MOST fallback fires resulted in disagreement (Haiku and Sonnet differed): Haiku is genuinely uncertain at ship-gate scale — narrow heuristic so fewer prompts route to Haiku-first.

### Deliverables

**If raise floor:**
1. `src/stream_manager/cli_governance.py` — bump `FALLBACK_CONFIDENCE_DEFAULT` (e.g. 0.70 → 0.85).
2. `tests/test_governance_fallback_routing.py::test_a_confidence_at_floor_no_fire` — update to new boundary.
3. Re-run Tier-3 ship-gate soak; verify fire rate drops to [1%, 30%].

**If narrow heuristic:**
1. `src/stream_manager/governance.py` — refine destructive-pattern list to exclude over-triggering patterns.
2. `tests/test_governance_content_detection.py` — add negative-control coverage for the formerly-matching content.
3. Re-run Tier-3 ship-gate soak; verify fire rate drops to [1%, 30%].

### Verdict-path invariant

When the (newly-tighter) floor or (newly-narrower) heuristic does not gate fallback, behavior is unchanged from prior. 550 fast-tier tests stay green.

## DOD

- [ ] Dashboard-log triage run; root cause documented (floor too aggressive vs heuristic too broad)
- [ ] Corresponding deliverable shipped
- [ ] Re-soak shows fire rate ∈ [1%, 30%] AND `cli_dispatch_fallback_ms` p95 > 0
- [ ] 550 fast-tier tests stay passing
- [ ] No edits to `model_router.py`, `tools/soak_driver.py`, `dashboard/`, or v1.7 protected symbol surface
- [ ] Single PR against `main`

## Mint-new-phase rule

After P2c ships:
- If re-soak shows fire rate now == 0: pivot back to `phase-2a-soak-prompt-coverage.md`.
- If re-soak fire rate ∈ [1%, 30%]: v1.8 P2 ship-gate finalize re-runs from §3 onward (ADR-5 + CHANGELOG + tag).

Report back when PR is open with: triage classification, deliverable shipped, re-soak fire rate (% + count), 550 fast-tier confirmation.
