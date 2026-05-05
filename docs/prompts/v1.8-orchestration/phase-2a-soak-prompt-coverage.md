You are implementing **Phase P2a — Ship-gate soak prompt coverage** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P2 (`ship/v1.8-shipgate-finalize`) is in progress AND the Tier-3 ship-gate soak (~32 min) recorded `cli_dispatch_fallback_ms` p95 == 0 despite v1.8 P1 wiring + a green local soak smoke. The ship-gate load mix did not exercise the lever — the falsification rule re-fires at v1.8 P2 unless this is fixed.

## Branch + base

- Base: `main` with v1.8 P1 merged.
- PR target: `main`.
- Branch: `feat/v1.8-shipgate-prompt-coverage` (or operator's choice).
- BLOCKS v1.8 P2 — do NOT proceed to ADR-5 update until this lands and a re-soak shows non-zero `cli_dispatch_fallback_ms` p95.

## ⚠️ CRITICAL: Do-not-touch guard

Same as `phase-1a-soak-prompt-coverage.md` — extend the canonical pair list / soak driver corpus, do NOT touch v1.7 or v1.8 P1 code surface.

The ship-gate soak load mix lives in the soak driver itself (separate from cassette_record.py, which is for replay). Search for the load-mix payload generation in `tools/soak_driver.py`:

```
grep -nE 'L4|alignment|ambig|destructive|payloads|prompt' tools/soak_driver.py | head -30
```

## Task brief

The local soak smoke at v1.8 P1 close used a short driver run with curated destructive prompts and recorded non-zero fallback fires. The Tier-3 ship-gate uses the standard 60-event load mix (50 ALLOW + 5 L2/L3 + 5 L4 + 10 LM) and recorded zero fallback fires. The standard load mix's L4 / L2/L3 payloads do not contain content that the v1.8 P1 heuristic matches.

Two fixes:

1. **Extend the ship-gate L4 payload set.** Add 1-2 destructive-content prompts to the L4 alignment / L2/L3 escalation payload generators in `tools/soak_driver.py` so the standard ship-gate run exercises the lever.
2. **Widen the v1.8 P1 heuristic.** If extending the soak corpus is undesirable (changes the 60-event baseline shape and breaks v1.6 / v1.7 deltas), instead widen the heuristic to match more of the existing payload content. NOTE this risks breaking the verdict-path invariant — re-run 550 fast-tier tests + alignment-eval `--ci-gate` if going this route.

Prefer fix 1 — extending the soak corpus is additive (new prompts, existing prompts unchanged). The ALLOW p95 / L4 p95 deltas vs v1.7 may shift slightly but the v1.7 baseline shape is preserved for the unchanged 58 events.

### Deliverables

**If fix 1 (extend ship-gate corpus):**
1. `tools/soak_driver.py` — append 1-2 destructive-content prompts to the L4 alignment / ambiguous-BLOCK payload generators. Keep the 60-event total (replace 1-2 existing benign prompts, OR bump the L4 count to 6-7 and document the load-mix shift in the v1.8 ADR-5 baseline §"Caveats"). Decide explicitly which path; do NOT silently bump n.
2. Re-run the Tier-3 ship-gate soak (~32 min, `--cli-pool-size 2`) FROM THE MAIN SESSION via `run_in_background` + `ScheduleWakeup`.
3. Verify the new soak report shows `cli_dispatch_fallback_ms` p95 > 0 AND ≥ 1 `governance_fallback_routed` envelope.
4. Cite the new soak report path; v1.8 P2 ADR-5 update consumes THIS report, not the prior zero-fire one.

**If fix 2 (widen heuristic — discouraged):**
1. `src/stream_manager/governance.py` — extend destructive-pattern heuristic.
2. `tests/test_governance_content_detection.py` — add coverage.
3. Re-run alignment-eval `--ci-gate` — verify still 0 FR-OG-7 regressions.
4. Re-run Tier-3 ship-gate soak (~32 min).
5. Re-run 550 fast-tier tests.

### Verdict-path invariant

For fix 1: the unchanged 58/60 events keep their v1.7 verdict path byte-identical. Only the swapped/added 2 prompts produce new verdicts.

For fix 2: 550 fast-tier tests must stay green; alignment-eval `--ci-gate` must stay clean on FR-OG-7.

## DOD

- [ ] Re-soak Tier-3 ship-gate report shows `cli_dispatch_fallback_ms` p95 > 0
- [ ] ≥ 1 `governance_fallback_routed` envelope captured (verify via dashboard log or bus message capture)
- [ ] If fix 1: load-mix delta from v1.7 documented in PR body (which prompts swapped or n bumped)
- [ ] If fix 2: 550 fast-tier tests + alignment-eval `--ci-gate` stay green
- [ ] No edits to `model_router.py`, `cli_governance.py` (except the floor const if invoking fix 2 path), or v1.6 CLI residue block
- [ ] Single PR against `main`

## Mint-new-phase rule

After P2a ships:
- If re-soak STILL shows zero fire rate: the v1.8 lever fundamentally cannot be exercised under any realistic soak shape. Mint v1.9 backlog item documenting falsification + abandon the lever; v1.8.0 ships as a no-op for latency.
- If fire rate > 30%: pivot to `phase-2c-fallback-floor-tuning.md`.
- Otherwise: v1.8 P2 ship-gate finalize is unblocked.

Report back when PR is open with: which fix taken, re-soak summary (fire count + percent + cli_dispatch_fallback_ms p95), 550 fast-tier confirmation if fix 2.
