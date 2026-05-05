You are implementing **Phase P1a — Soak prompt coverage** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P1 (`feat/v1.8-content-detection-wiring`) shipped but the local soak smoke recorded `cli_dispatch_fallback_ms` p95 == 0 OR no `governance_fallback_routed` envelope captured. The heuristic did not match the soak load mix; the lever is still effectively dormant.

## Branch + base

- Base: `main` with v1.8 P1 merged.
- PR target: `main`.
- Branch: `feat/v1.8-soak-prompt-coverage` (or operator's choice).
- If P1 is not merged, ABORT.
- If P1 local soak smoke DID show non-zero `cli_dispatch_fallback_ms` p95, this phase is moot — go straight to v1.8 P2.

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.7 protected-symbol set in `docs/v1.8-task-plan.md` §"CRITICAL: do-not-touch list" applies. P1a touches ONLY:

- `tools/cassette_record.py::_LM_DIALOGUE_PAIRS` or the analogous canonical pair list — **EXTEND, do NOT reorder existing entries** (memory: `feedback_cassette_must_cover_new_envelopes.md`)
- soak driver load-mix payload set (search for the prompt corpus that drives ALLOW / L2/L3 / L4 envelopes)
- `tests/test_governance_content_detection.py` — extend with the new content shapes added to the corpus
- OR `src/stream_manager/governance.py` — widen the destructive-pattern heuristic if the soak corpus is correct but the regex / classifier is too narrow

Do NOT touch `model_router.py`, `cli_governance.py`, the v1.6 CLI residue block, or the alignment-eval golden set.

Pre-flight grep:

```
grep -nE 'CliPool|CliWorker|RoutingDecision|fallback_model_id|cli_dispatch_fallback_ms|FALLBACK_CONFIDENCE|_publish_bus_message|_parse_envelope_with_meta|_evaluate_once|governance_fallback_routed|governance_envelope_missing_confidence|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|is_ambiguous_block|is_hitl_synthesis' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP — silent-revert trap.

## Task brief

Triage why the v1.8 P1 wiring did not fire under the soak load mix. Two possible root causes:

1. **Soak corpus too clean.** The cassette / soak driver payload set does not contain prompts that match destructive patterns. Fix: extend the corpus with curated destructive prompts so the heuristic actually has something to match.
2. **Heuristic too narrow.** The cassette already contains destructive prompts, but the v1.8 P1 regex / classifier is too restrictive. Fix: widen the pattern list in `governance.py` so legitimate destructive content matches.

Triage step before fixing:

```
grep -in 'rm -rf\|git push.*--force\|git push -f\|drop table\|truncate\|delete from\|chmod 777\|sudo' tools/cassette_record.py
```

If matches: heuristic is too narrow (fix 2). If no matches: corpus is too clean (fix 1).

### Deliverables (depending on root cause)

**If fix 1 (extend corpus):**
1. `tools/cassette_record.py` — append 3-5 destructive-content prompts to the canonical pair list. EXTEND, never reorder. Each prompt should be a realistic ambig-BLOCK candidate (low precheck-hit likelihood, high destructive intent).
2. Regenerate cassette beacon if needed (per memory `feedback_cassette_must_cover_new_envelopes.md`); update `tests/beacons/learn_mode_categorizer.jsonl` if it consumes the same canonical list.
3. `tests/test_governance_content_detection.py` — add coverage for the new prompts (each new corpus entry gets a unit-test row asserting `is_ambiguous_block=True`).

**If fix 2 (widen heuristic):**
1. `src/stream_manager/governance.py` — extend the destructive-pattern list. Add concrete patterns (regex or substring matches) for the cassette content the soak smoke missed.
2. `tests/test_governance_content_detection.py` — add coverage for the newly-matched patterns (positive + negative controls so the widened pattern doesn't over-trigger).

### Re-soak smoke

Re-run the same local soak smoke from v1.8 P1 (`tools/soak_driver.py --cli-pool-size 2 --total-seconds 600` or similar). Verify:
- `cli_dispatch_fallback_ms` p95 > 0
- ≥ 1 `governance_fallback_routed` envelope captured
- Fallback fire rate < 30% (else go to phase-1b-fallback-floor-tuning)

### Verdict-path invariant

When the new heuristic patterns / corpus prompts are False on a given content (the v1.7-equivalent default), behavior MUST stay byte-identical to v1.7. Run `pytest tests/ -m "not slow and not alignment_eval" -q` and confirm 550 fast-tier tests still pass.

## DOD

- [ ] Triage step run; root cause documented in PR body (fix 1 vs fix 2)
- [ ] Corresponding deliverable shipped (extended corpus OR widened heuristic, NOT both unless root cause is genuinely both)
- [ ] Local re-soak smoke shows `cli_dispatch_fallback_ms` p95 > 0 AND ≥ 1 `governance_fallback_routed` envelope captured
- [ ] Fallback fire rate < 30%
- [ ] 550 fast-tier tests stay passing
- [ ] No edits to `model_router.py`, `cli_governance.py`, `tools/soak_driver.py`, `dashboard/`, alignment-eval golden set, or any v1.7 protected symbol
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1a ships:
- If re-soak smoke STILL shows zero fire rate: the heuristic surface fundamentally does not match the soak driver's content shape. Mint `phase-1c-heuristic-redesign.md` (re-architect detection — possibly use POST-precheck-miss + POST-graph-miss as the trigger instead of content patterns) BEFORE P2 cuts.
- If re-soak smoke shows fire rate > 30%: pivot to `phase-1b-fallback-floor-tuning.md`.
- Otherwise: P2 (`phase-2-ship-gate-finalize.md`) is unblocked.

Report back when PR is open with: root cause classification, deliverable shipped, re-soak smoke summary (fallback fire count + percent + cli_dispatch_fallback_ms p95), 550 fast-tier confirmation.
