You are implementing **Phase P1c — Ambiguous-block trigger redesign** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint after v1.8 P1a (`feat/v1.8-soak-prompt-coverage`) shipped and the P1a re-soak smoke STILL shows zero `governance_fallback_routed` events despite `_looks_ambiguous_block` firing on L4 content.

**Root cause carried from P1a:** L4 soak item index 2 ("Going to delete the legacy precheck table...") correctly triggers `is_ambiguous_block=True` via the new prose patterns, but the CLI evaluator (Haiku) returns ALLOW with confidence ≥ 0.70 — Sonnet fallback never fires. The soak driver's content shape (long architectural planning prose) is not ambiguous enough to produce Haiku-uncertain governance decisions. A content-pattern pre-routing trigger cannot force low-confidence Haiku verdicts; it only changes which model is called.

## Branch + base

- Base: `main` with v1.8 P1a merged.
- PR target: `main`.
- Branch: `feat/v1.8-heuristic-redesign` (or operator's choice).
- If P1a is not merged, ABORT.

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.8 P1 protected-symbol set in `docs/v1.8-task-plan.md` §"CRITICAL: do-not-touch list" applies. P1c touches ONLY:

- `src/stream_manager/governance.py` — redesign the `is_ambiguous_block` trigger signal (pre-routing site `_evaluate_inner_core`)
- `tests/test_governance_content_detection.py` — update unit tests to match new trigger semantics
- `tools/soak_driver.py::_L2_L3_TRIGGER` or `_L4_ALIGNMENT` — ADD new genuinely-ambiguous destructive prompts **only** (do NOT reorder existing entries, do NOT reduce list size)
- `tests/beacons/` — update cassette beacon if soak driver additions require it

Do NOT touch `model_router.py`, `cli_governance.py` (the retry-path logic, `FALLBACK_CONFIDENCE_DEFAULT`, `FALLBACK_CONFIDENCE_ENV`), alignment-eval golden set, or `tools/cassette_record.py`.

Pre-flight grep (verify all symbols still present):

```
grep -nE 'CliPool|CliWorker|RoutingDecision|fallback_model_id|cli_dispatch_fallback_ms|FALLBACK_CONFIDENCE|_publish_bus_message|_parse_envelope_with_meta|_evaluate_once|governance_fallback_routed|governance_envelope_missing_confidence|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|is_ambiguous_block|is_hitl_synthesis' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP — silent-revert trap.

## Task brief

Two complementary root causes must both be addressed:

### Root cause A — Trigger redesign (governance.py)

The content-pattern trigger (`_looks_ambiguous_block`) fires too early — before the precheck and graph classify have run — and fires based on surface text rather than actual pipeline miss. A more reliable signal: activate the Haiku-fastpath sub-band when **both** `fast_precheck` and `graph_classify` produce no escalation (i.e., they agree the content is routine) **but** the content additionally carries ambiguous-destructive prose signals (the existing `_looks_ambiguous_block` patterns). The conjunction is tighter and reduces false-positive activations on benign content that happens to mention "delete" or "drop".

Alternatively, consider triggering `is_ambiguous_block` POST-evaluation: after the primary CLI call returns, if the returned confidence is in a specific mid-range window (e.g., 0.65–0.85), retroactively flag for a Sonnet review pass. This redesign requires restructuring `_maybe_cli_evaluate` so the ambiguous-block signal is computed from the decision rather than injected before the call. Evaluate which of these redesigns is feasible without touching the protected symbols.

### Root cause B — Soak driver content shape (soak_driver.py)

The current `_L2_L3_TRIGGER` and `_L4_ALIGNMENT` content is too benign for the CLI evaluator to be uncertain. Add 2–3 new prompts to `_L2_L3_TRIGGER` that are:

- Genuinely ambiguous destructive actions (operator is about to do something potentially harmful but the intent is not fully clear)
- Short enough that Haiku cannot reason to a high-confidence conclusion in one pass
- Low precheck-hit likelihood (do NOT include literal `rm -rf /`, `git push --force origin main`, or `DROP TABLE` — these would be caught by fast_precheck)

Good candidates:
- "Should I wipe the staging DB and replay from the prod snapshot? The last migration left it inconsistent."
- "Going to force the push — the PR CI is stuck in a loop and the branch is rebased. Safe?"
- "Deleting the user_events table in the next migration window; analytics only, no writes. OK to proceed?"

These are realistic governance asks where the CLI evaluator might return confidence 0.55–0.65 (genuinely unsure whether to ALLOW) → Sonnet fallback fires.

### Triage order

Execute root cause B first (it is lower risk and verifiable in isolation). Run a local soak smoke after B only:

```
python tools/soak_driver.py --cli-pool-size 2 --total-seconds 600
```

If this alone produces ≥ 1 `governance_fallback_routed` event at rate < 30%, root cause A is deferred (trigger redesign is not needed to hit the soak metric). Ship and go to P2.

If still zero after B: proceed with root cause A (trigger redesign). Re-run soak smoke after A.

### Verdict-path invariant

When `is_ambiguous_block=False` and the new prompts are not in the soak window, behavior MUST be byte-identical to v1.8 P1a. Run `pytest tests/ -m "not slow and not alignment_eval" -q` and confirm fast-tier tests still pass (594 as of P1a baseline).

## DOD

- [ ] Triage order followed (B before A)
- [ ] Root cause B: 2–3 new ambiguous-destructive prompts added to `tools/soak_driver.py::_L2_L3_TRIGGER` (EXTEND, do not reorder)
- [ ] If root cause A implemented: `_looks_ambiguous_block` redesigned; `test_governance_content_detection.py` updated
- [ ] Re-soak smoke (600s, pool-size 2) shows `cli_dispatch_fallback_ms` p95 > 0 AND ≥ 1 `governance_fallback_routed` captured
- [ ] Fallback fire rate < 30%
- [ ] 594 fast-tier tests still passing
- [ ] No edits to `model_router.py`, `cli_governance.py`, `tools/cassette_record.py`, `dashboard/`, alignment-eval golden set, or any v1.7–P1a protected symbol
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1c ships:
- If re-soak smoke shows fire rate ∈ [1%, 30%]: P2 (`phase-2-ship-gate-finalize.md`) is unblocked.
- If fire rate == 0 still: the CLI evaluator is systematically confident on all governance content. Escalate to Sean — this may require a different evaluation model or confidence-extraction redesign outside the P1c scope.
- If fire rate > 30%: pivot to `phase-1b-fallback-floor-tuning.md`.

Report back when PR is open with: which root cause(s) addressed, deliverable(s) shipped, re-soak smoke summary (fallback fire count + percent + `cli_dispatch_fallback_ms` p95), 594 fast-tier confirmation.
