You are implementing **Phase P2 — v1.8 ship-gate + ADR-5 v1.8 baseline + lever-effect measurement** from the streamManager v1.8 cycle.

> **Historical record.** Symbols protected by this ship-gate's
> do-not-touch list — Haiku fastpath router consumer + verdict-fallback
> retry path — were decommissioned at v2.0 P3. See
> `docs/adr/ADR-18-mvp-surface-freeze.md` §"Decommissioned". Content-
> detection helpers (`_looks_ambiguous_block`, `_looks_hitl_synthesis`,
> `_AMBIGUOUS_BLOCK_PATTERNS`) remain FROZEN. This prompt is preserved
> for history.

## Branch + base

- Base: `main` with v1.8 P1 (`feat/v1.8-content-detection-wiring`) merged.
- PR target: `main`.
- Branch: `ship/v1.8-shipgate-finalize` (or operator's choice).
- If P1 is not merged, ABORT — P2 ship-gate depends on the v1.8 content-detection wiring landing first.
- If P1 local soak smoke did not show `cli_dispatch_fallback_ms` p95 > 0, ABORT — P1's mint rule must fire first (lever still dormant).

## ⚠️ CRITICAL: Do-not-touch guard

P2 is **finalize only** — soak run, alignment-eval gate, report, ADR-5 re-baseline, CHANGELOG, tag. Do NOT modify engine code, soak driver report logic, or any v1.0–v1.7 protected symbol. Per memory `feedback_subagent_stale_mental_model.md`, diff PR head vs `main` on `src/` and `tools/` and confirm zero hunks before merging:

```
git --no-pager diff origin/main..HEAD -- src tools
```

Expect empty output (or trivial whitespace only). Any code hunks: STOP — finalize PR has accidentally absorbed P1 follow-up work.

Per memory `feedback_no_self_monitor.md`: do NOT run governance over the SM's own JSONL/bus during the ship-gate. Use the standard `tools/soak_driver.py --cli-pool-size 2` cassette path.

Per memory `feedback_soak_cli_pool_flag.md`: **always** pass `--cli-pool-size 2` to `tools/soak_driver.py`. Default 0 silently reproduces the v1.0 cold-start regression and invalidates the ship-gate.

Per memory `feedback_subagent_long_task_abandonment.md`: the 32-min soak MUST run from the main session via `run_in_background` + `ScheduleWakeup` polling. NEVER launch the soak from a subagent.

## Task brief

Finalize v1.8. Seven deliverables (mirror v1.7 P3).

### 1. Tier-3 ship-gate soak

```
python tools/soak_driver.py --cli-pool-size 2
```

Match the v1.7 ship-gate parameter set exactly (32-min wall-clock, ALLOW n=50, L2/L3 n=5, L4 n=5, LM n=10) so the v1.8 numbers diff cleanly against the v1.7 baseline.

Launch the soak with `run_in_background=true` from the main session. Use `ScheduleWakeup` to poll for completion (~32 min wall-clock). Do NOT delegate this run to a subagent.

Report file: `reports/soak-<UTC-timestamp>Z.md`. Verify the report contains ALL THREE blocks (the v1.6 CLI residue block still renders 6 rows including `cli_dispatch_fallback_ms`):
- `### ALLOW publish-path phase breakout (v1.4)` (back-compat)
- `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` (back-compat)
- `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` (back-compat — 6 rows)

If `cli_dispatch_fallback_ms` p95 is **0.00** in this run despite P1 wiring (i.e. the soak load mix did not contain content matching the heuristic), the lever did not fire under the ship-gate shape — STOP and mint `phase-2a-soak-prompt-coverage.md` BEFORE updating ADR-5. The ADR-5 v1.8 baseline must reflect a soak that exercises the lever; otherwise the falsification rule re-fires from v1.7.

### 2. Alignment-eval gate

```
python tools/alignment_eval.py --ci-gate
```

Run against the merged v1.8 router/wiring. Attach `reports/alignment-eval-<UTC>Z.md` to the ship-gate report references. Ship-gate FAILS if the gate is non-zero on FR-OG-7 rows (`model_floor == "sonnet"`).

### 3. ADR-5 v1.8 baseline

Append `## v1.8 ship-gate baseline` to `docs/adr/ADR-5-latency-budget.md`. Update the ADR header `Status:` line. Append-only.

Required subsections (mirror v1.7 baseline §):
- Source / Date / Ship SHA / Driver / Runtime / Events / Verdict
- Latency targets (overall, n=60)
- Per-band split
- ALLOW _evaluate_inner CLI residue breakout (still 6 rows; `cli_dispatch_fallback_ms` row should now show non-zero p95 if lever fires)
- Fallback routing summary (NEW v1.8 measurement): n / share of L4 calls firing fallback / per-band fallback rate (ambiguous-BLOCK vs HITL synthesis) / `governance_fallback_routed` envelope count
- Alignment-eval result: control vs candidate pass rate; FR-OG-7 row gate result
- Delta vs v1.7 ship-gate (`reports/soak-20260505T125741Z.md`): overall p50/p95/max/mean, ALLOW p95, L2/L3 p95, L4 alignment p95, LM categorize p95, RSS drift, **`cli_pool_send_ms` p95** (the v1.7 baseline = 5128.96 ms; v1.8 earned improvement only if fallback fire rate is non-zero AND p95 dropped further)
- Budget (carry forward unchanged from v1.7 unless lever success justifies tightening)
- Status: ACCEPTED
- Caveats (per §4 below)

Update v1.7 §"Caveats" lever bullet — annotate the disposition (lever ACTIVATED in v1.8, see §"v1.8 ship-gate baseline" §Caveats lever-effect bullet for the measured magnitude).

### 4. Lever effect — data-driven §"Caveats" findings

Document in §"Caveats". Data-driven only — do NOT predict:

- **Fallback fire rate.** Share of L4 ambig-BLOCK / HITL-synthesis rows triggering Sonnet retry. Report n + percent. Target: > 0% (proves wiring) AND < 30% (Haiku-first is helping, not just retrying).
- **`cli_pool_send_ms` p95 trend.** vs v1.7 baseline 5128.96 ms. Earned improvement only if fallback fire rate is non-zero AND p95 dropped further than expected from upstream variance. Note v1.7 P3 already recorded a -19% drop attributable to upstream variance (no lever); v1.8 must show MORE than upstream variance can explain.
- **L4 alignment p95 trend.** vs v1.7 13.41 s. Should be unchanged (FR-OG-7 cells still on Sonnet only). Any drop here would be sample noise.
- **ALLOW p95 trend.** vs v1.7 5.13 s. Earned improvement when fallback fire rate is non-zero.
- **Lever falsification re-check.** If fallback fires AND p95 drops materially → v1.7 lever effect now confirmed, document magnitude. If fallback fires but p95 does NOT drop → Haiku TTFT is not faster than Sonnet's on this content shape; document and consider raising `BRIDGE_L4_FALLBACK_CONFIDENCE` floor (Haiku-first more aggressive) OR narrowing Haiku surface (more selective is_ambiguous_block heuristic) in v1.9.
- **Alignment-eval result.** Per-row regression count on Haiku vs Sonnet; FR-OG-7 row gate result. If gate fired on FR-OG-7: SHIP BLOCKED — abort merge, debug routing precedence (`requires_alignment` should keep FR-OG-7 on Sonnet).

### 5. LM (categorize) p95 trend re-check

v1.7 §"Caveats" closed the LM watch (v1.7 LM p95 = 11.95 s, well under 18 s ceiling). v1.8 confirms stability or re-opens:

- **v1.8 LM p95 < 18 s** → watch stays closed; document in `## [1.8.0]` CHANGELOG.
- **v1.8 LM p95 ≥ 18 s AND magnitude > 1 s over ceiling** → re-open watch as v1.9 backlog item; mint `phase-2b-lm-regression-triage.md` if magnitude is large.

### 6. CHANGELOG

Append `## [1.8.0]` section to `CHANGELOG.md`. Mirror v1.7.0 prose style. Cover:
- P1 content-detection wiring (PR #<m>)
- Ship-gate verdict (PASS / BLOCKED)
- Lever effect (`cli_pool_send_ms` p95 Δ vs v1.7, fallback fire rate, alignment-eval)
- LM trend re-check
- ADR-5 cross-link

### 7. Tag

Tag `v1.8.0` on the merge commit. Push tag to origin.

## Cross-PR seam audit (memory: `feedback_cross_pr_seam_review.md`)

Verify the full chain before merging:
- v1.7 P1 harness (`tools/alignment_eval.py`, `tests/golden/l4_alignment.jsonl`)
- ↔ v1.7 P2 router (`model_router.RoutingDecision.fallback_model_id`, `cli_governance.CliGovernor.evaluate` retry)
- ↔ v1.7 P2 governance (`_last_phase_timings_ms.cli_dispatch_fallback_ms`, `governance_fallback_routed` envelope)
- ↔ v1.8 P1 wiring (`governance._evaluate_inner_core` pre-routing flags computed from content)
- ↔ v1.8 P2 reader (soak driver `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` 6th row now non-zero)
- ↔ ADR-5 v1.8 baseline table

Any seam mismatch (e.g. wiring fires but envelope count is zero, or envelope count is non-zero but `cli_dispatch_fallback_ms` p95 is still zero): STOP and patch BEFORE the v1.8.0 tag.

## DOD

- [ ] Tier-3 soak completed from main session, report at `reports/soak-<UTC>Z.md`
- [ ] All three ALLOW breakout blocks present; v1.6 CLI residue block has 6 rows; `cli_dispatch_fallback_ms` p95 > 0 (lever fires)
- [ ] Alignment-eval `--ci-gate` run; report at `reports/alignment-eval-<UTC>Z.md`; FR-OG-7 row gate exits zero
- [ ] `docs/adr/ADR-5-latency-budget.md` has `## v1.8 ship-gate baseline` appended; ADR header `Status:` updated; v1.7 §"Caveats" lever bullet annotated; prior baseline sections untouched
- [ ] §"Caveats" documents lever effect (data-driven), fallback fire rate, alignment-eval result, lever falsification re-check
- [ ] LM trend re-checked; decision recorded in §"Caveats" + CHANGELOG
- [ ] `## [1.8.0]` CHANGELOG section appended
- [ ] Tag `v1.8.0` created on merge commit; pushed to origin
- [ ] No `src/` or `tools/` hunks in the finalize PR (verify with diff)

## Mint-new-phase rule

After each P2 sub-step completes, scan for follow-ups before ticking:
- **Soak done** → if `cli_dispatch_fallback_ms` p95 == 0 despite P1 wiring (soak load mix did not exercise the heuristic), mint `phase-2a-soak-prompt-coverage.md` (BLOCKS ADR-5 update — falsification rule re-fires).
- **Alignment-eval done** → if gate fires on `model_floor == "sonnet"` rows: ABORT MERGE; debug routing precedence (`requires_alignment` should keep FR-OG-7 on Sonnet — if it does not, the v1.8 wiring corrupted `model_router.route()` call ordering).
- **Lever effect documented** → if fallback fire rate > 30%, mint `phase-2c-fallback-floor-tuning.md` (raise BRIDGE_L4_FALLBACK_CONFIDENCE floor or narrow Haiku surface). If `cli_pool_send_ms` p95 did NOT drop materially despite non-zero fire rate: mint v1.9 backlog item (Haiku TTFT not faster than Sonnet on this content shape — falsification of "Haiku is faster" axiom on the relevant prompt distribution).
- **LM trend re-checked** → if LM p95 ≥ 18 s + magnitude > 1 s, mint `phase-2b-lm-regression-triage.md`.
- **PR review** → if blockers surface, mint `phase-2d-ship-pr-fixups.md`.
- **Tag step** → if tag push fails or post-tag smoke breaks, mint `phase-2e-tag-recovery.md`.

Report back when v1.8.0 tag pushes with: tag SHA, ship PR URL, ship-gate verdict, lever Δ summary (`cli_pool_send_ms` p95 v1.7 → v1.8, ALLOW p95 v1.7 → v1.8, fallback fire rate, alignment-eval gate result), LM trend re-check.
