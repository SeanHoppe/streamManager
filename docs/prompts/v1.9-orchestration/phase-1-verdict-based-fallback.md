You are implementing **Phase P1 — Verdict-based fallback trigger** from the streamManager v1.9 cycle.

## Branch + base

- Base: `main` with v1.9 P0 (`docs/v1.9-cycle-frame`) merged.
- PR target: `main`.
- Branch: `feat/v1.9-verdict-based-fallback` (or operator's choice).
- If P0 is not merged, ABORT (the task plan + phase prompts must be on `main` first).

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.8 protected-symbol set in `docs/v1.9-task-plan.md` §"CRITICAL: do-not-touch list" applies. P1 must touch ONLY:

- `src/stream_manager/cli_governance.py` — retry trigger logic; new mode constant; `governance_fallback_routed` envelope metadata extension
- `tests/test_governance_fallback_routing.py` — extend with verdict-mode scenarios (do NOT modify existing test cases)

NO edits to `governance.py`, `model_router.py`, `cli_pool.py`, `tools/soak_driver.py`, `dashboard/`, or any v1.7 / v1.8 protected symbol. The v1.8 P1 content-detection wiring (`_looks_ambiguous_block`, `is_ambiguous_block` / `is_hitl_synthesis` computation, `_DESTRUCTIVE_PATTERNS` or equivalent) is load-bearing — do not touch.

Pre-flight grep (run before any edit; if any symbol is missing, STOP — silent-revert trap):

```
grep -nE 'FALLBACK_CONFIDENCE_ENV|FALLBACK_CONFIDENCE_DEFAULT|_fallback_confidence_floor|_evaluate_once|_publish_bus_message|_parse_envelope_with_meta|governance_fallback_routed|governance_envelope_missing_confidence|fallback_model_id' src/stream_manager/cli_governance.py
```

Also verify the v1.8 content-detection surface is intact:

```
grep -nE '_looks_ambiguous_block|is_ambiguous_block|is_hitl_synthesis|_DESTRUCTIVE_PATTERNS' src/stream_manager/governance.py
```

If `_looks_ambiguous_block` is named differently in your working tree, use whatever name the grep returns — do not assume the name.

## Task brief

v1.7 P2 shipped the L4 sub-band Haiku-fastpath router with a confidence-floor retry trigger (`BRIDGE_L4_FALLBACK_CONFIDENCE` = 0.70). v1.8 P1 wired `is_ambiguous_block` / `is_hitl_synthesis` at the pre-routing call site, activating the Haiku-first routing path. v1.8 ship-gate (`reports/soak-20260506T101746Z.md`) still recorded 0 fallback fires: Haiku returned confidence ≥ 0.70 on all 2/2 ambiguous-block events. Two corpus-fix attempts also failed. Root cause: Haiku consistently returns high-confidence verdicts on short destructive commands regardless of their ambiguity.

P1 replaces the confidence-floor trigger with a verdict-based trigger: when Haiku returns BLOCK or INTERVENE on ambiguous-block content, auto-retry with Sonnet for a second opinion. This is option 3 from `docs/v1.9-backlog.md`.

### Deliverables

1. **`src/stream_manager/cli_governance.py`** — add verdict-based retry mode:

   - **New constants:**
     ```python
     BRIDGE_L4_FALLBACK_MODE_ENV: str = "BRIDGE_L4_FALLBACK_MODE"
     FALLBACK_MODE_DEFAULT: str = "verdict"
     ```
   - **`_fallback_mode()` helper** — reads `os.getenv(BRIDGE_L4_FALLBACK_MODE_ENV, FALLBACK_MODE_DEFAULT)`. Returns `"verdict"` or `"confidence"`. Any other value → warn + default to `"verdict"`.
   - **Retry trigger** — in the retry-decision code path (wherever `_fallback_confidence_floor()` is currently checked), apply mode dispatch:
     - `"verdict"` mode: fire retry if `primary_verdict in {"BLOCK", "INTERVENE"}` AND `fallback_model_id is not None`.
     - `"confidence"` mode: fire retry if `primary_confidence < _fallback_confidence_floor()` AND `fallback_model_id is not None` (original v1.7 P2 behavior, unchanged).
   - **`FALLBACK_CONFIDENCE_ENV`, `FALLBACK_CONFIDENCE_DEFAULT`, `_fallback_confidence_floor()`** remain present, functional, and unmodified. They are load-bearing protected symbols and are used in confidence mode.
   - **`governance_fallback_routed` envelope** — extend metadata with `trigger_mode: str` field (value `"verdict"` or `"confidence"`) — additive only; existing fields (`primary_model`, `fallback_model`, `primary_confidence`, `fallback_confidence`, `fallback_ms`) are unchanged and their key names must not be altered.
   - **When both flags are False** (non-ambiguous-block, non-HITL path, `fallback_model_id is None`): behavior is byte-identical to v1.8 regardless of mode — `_evaluate_once` with no fallback, same verdict path, same envelope counts.

2. **Tests** — extend `tests/test_governance_fallback_routing.py` (append new test functions; do not modify any existing test):
   - `test_verdict_mode_block_fires_retry` — ambiguous-block content + Haiku returns BLOCK verdict → Sonnet retry fires; `governance_fallback_routed` emitted with `trigger_mode="verdict"`.
   - `test_verdict_mode_intervene_fires_retry` — Haiku returns INTERVENE → retry fires.
   - `test_verdict_mode_allow_no_retry` — Haiku returns ALLOW → retry does NOT fire; no `governance_fallback_routed` emitted.
   - `test_verdict_mode_suggest_no_retry` — Haiku returns SUGGEST → retry does NOT fire.
   - `test_confidence_mode_preserved` — `BRIDGE_L4_FALLBACK_MODE=confidence`, Haiku returns BLOCK but confidence ≥ 0.70 → retry does NOT fire (original v1.7 P2 behavior preserved).
   - `test_confidence_mode_fires_on_low_confidence` — `BRIDGE_L4_FALLBACK_MODE=confidence`, confidence < 0.70 → retry fires.
   - `test_non_ambiguous_block_no_fallback_model` — content does not match `_looks_ambiguous_block`, `fallback_model_id is None` → no retry regardless of mode or Haiku verdict.
   - `test_fallback_routed_envelope_has_trigger_mode` — `governance_fallback_routed` envelope includes `trigger_mode` field; existing fields still present.

   Existing v1.7 + v1.8 fast-tier tests MUST stay green:
   `tests/test_governance_content_detection.py`, `tests/test_model_router_l4_subband.py`, `tests/test_cli_governance.py`, `tests/test_model_router.py`, `tests/test_soak_driver_v17_residue_block.py`, `tests/test_alignment_eval_harness.py` (schema test).

3. **Alignment-eval `--ci-gate`** — run `python tools/alignment_eval.py --ci-gate` against the new trigger logic. Must exit 0 on FR-OG-7 rows. Attach `reports/alignment-eval-<UTC>Z.md` to the PR. FR-OG-7 rows never reach Haiku-first path (`requires_alignment` keeps them on Sonnet at the routing layer), so regression should be impossible by construction.

4. **Local soak smoke** — drive a short run (`python tools/soak_driver.py --cli-pool-size 2 --total-seconds 300` or similar) with the existing destructive-content items in `_L2_L3_TRIGGER`. Verify in the resulting report:
   - `cli_dispatch_fallback_ms` p95 > 0 (verdict-based trigger fires for the first time).
   - At least one `governance_fallback_routed` envelope captured (verify via dashboard log or bus capture).
   - Fallback fire rate on the smoke mix is > 0% and < 50% (> 0% proves the trigger works; < 50% confirms Haiku-first is still the primary path, not always-retry).

   If `cli_dispatch_fallback_ms` p95 == 0 after P1 wiring: Haiku is returning ALLOW/SUGGEST on all ambiguous-block soak content (not BLOCK/INTERVENE). Mint `phase-1a-corpus-check.md` (sample the actual Haiku verdicts on the soak content; if Haiku consistently returns ALLOW on destructive commands, promote option 4 corpus expansion as a v1.9 follow-up). Do NOT proceed to P4 until at least one fallback fires.

### Verdict-path invariant

When `fallback_model_id is None` (the common path: all non-ambiguous-block, non-HITL events), behavior MUST be byte-identical to v1.8:
- `_evaluate_once` called with no fallback → same verdict, same residue keys, same envelope counts.
- 550+ fast-tier tests must pass: `pytest tests/ -m "not slow and not alignment_eval" -q`.

### No new bus envelopes

P1 reuses the v1.7 P2 `governance_fallback_routed` and `governance_envelope_missing_confidence` envelopes. The `trigger_mode` field is a metadata extension, not a new envelope type. Verify:

```
grep -rn 'governance_' src/stream_manager/ | grep -v 'governance_call\|governance_fallback_routed\|governance_envelope_missing_confidence'
```

Should return zero matches outside legitimate code paths.

### Memory feedback applied

- `feedback_subagent_stale_mental_model.md` — pre-flight grep before any edit
- `feedback_cli_over_sdk.md` — alignment-eval `--ci-gate` drives real `claude -p`
- `feedback_subagent_long_task_abandonment.md` — `--ci-gate` (~42 min) launched from main thread w/ `run_in_background` + `ScheduleWakeup`
- `feedback_cassette_must_cover_new_envelopes.md` — verified P1 introduces NO new envelope types (extends existing `governance_fallback_routed` metadata only)
- `feedback_cross_pr_seam_review.md` — verify: v1.8 P1 content-detection wiring (`is_ambiguous_block=True` for destructive content) ↔ v1.7 P2 router (`fallback_model_id` set) ↔ v1.9 P1 trigger (BLOCK/INTERVENE → retry fires) ↔ soak smoke (`cli_dispatch_fallback_ms` p95 > 0)

## DOD

- [ ] `src/stream_manager/cli_governance.py` has `BRIDGE_L4_FALLBACK_MODE_ENV`, `FALLBACK_MODE_DEFAULT = "verdict"`, `_fallback_mode()`, verdict-based retry trigger
- [ ] `FALLBACK_CONFIDENCE_ENV`, `FALLBACK_CONFIDENCE_DEFAULT`, `_fallback_confidence_floor()` unchanged and functional in `"confidence"` mode
- [ ] `governance_fallback_routed` envelope has `trigger_mode` field; existing fields unchanged
- [ ] 8 new test scenarios in `tests/test_governance_fallback_routing.py`; all pass
- [ ] `pytest tests/ -m "not slow and not alignment_eval" -q` → all pass (no v1.7/v1.8 regression)
- [ ] Alignment-eval `--ci-gate` baseline run: exit 0, 0 FR-OG-7 regressions, report attached
- [ ] Local soak smoke shows `cli_dispatch_fallback_ms` p95 > 0 AND ≥ 1 `governance_fallback_routed` envelope emitted
- [ ] No edits to `governance.py`, `model_router.py`, `cli_pool.py`, `tools/soak_driver.py`, `dashboard/`, or any v1.7/v1.8 protected symbol — verify with `git --no-pager diff origin/main..HEAD --stat -- src/stream_manager/governance.py src/stream_manager/model_router.py src/stream_manager/cli_pool.py tools/soak_driver.py dashboard`
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1 local soak smoke completes, scan before ticking DOD:
- If `cli_dispatch_fallback_ms` p95 == 0: Haiku returns ALLOW/SUGGEST on all soak ambiguous-block content — mint `phase-1a-corpus-check.md` (sample Haiku verdicts; determine if option 4 corpus expansion is the right next step). BLOCKS P4.
- If fallback fire rate > 50% on the smoke: the verdict trigger is too broad (INTERVENE alone is causing excessive retries) — consider restricting to BLOCK-only; mint `phase-1b-trigger-narrowing.md`.
- If alignment-eval `--ci-gate` fires on FR-OG-7 rows (should be impossible): ABORT — debug routing precedence (`requires_alignment` must keep FR-OG-7 on Sonnet).
- If neither: P4 (`phase-4-ship-gate-finalize.md`) is unblocked (after P2 + P3 also merge).

Report back when PR is open with: PR URL, diff stat, alignment-eval gate result, local soak smoke summary (fallback fire count + percent + `cli_dispatch_fallback_ms` p95, Haiku verdict distribution on ambiguous-block events).
