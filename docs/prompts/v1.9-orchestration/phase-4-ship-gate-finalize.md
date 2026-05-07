You are implementing **Phase P4 — v1.9 ship-gate + ADR-5 v1.9 baseline + lever-effect measurement** from the streamManager v1.9 cycle.

> **Historical record.** Symbols protected by this ship-gate's
> do-not-touch list — verdict-fallback retry path + Haiku fastpath
> router consumer — were decommissioned at v2.0 P3 after the v2.0 P1
> A/B falsified the warm-process-reuse revival hypothesis. See
> `docs/adr/ADR-18-mvp-surface-freeze.md` §"Decommissioned" +
> §"Amendments". This prompt is preserved for history.

## Branch + base

- Base: `main` with v1.9 P1 + P2 + P3 all merged.
- PR target: `main`.
- Branch: `ship/v1.9-shipgate-finalize` (or operator's choice).
- If ANY of P1, P2, P3 is not merged, ABORT — the ship-gate must measure the full v1.9 feature set in one soak.
- If P1 local soak smoke showed `cli_dispatch_fallback_ms` p95 == 0 and a `phase-1a-corpus-check.md` was minted, ABORT — the mint must land before P4 cuts.

## ⚠️ CRITICAL: Do-not-touch guard

P4 is **finalize only** — soak run, alignment-eval gate, report, ADR-5 re-baseline, CHANGELOG, tag. Do NOT modify engine code, soak driver report logic, `session_watcher.py`, `learn_mode.py`, or any v1.0–v1.8 protected symbol. Diff PR head vs `main` on `src/` and `tools/`:

```
git --no-pager diff origin/main..HEAD -- src tools
```

Expect empty output (or trivial whitespace only). Any code hunks: STOP — the finalize PR has absorbed implementation work.

Per memory `feedback_no_self_monitor.md`: do NOT run governance over the SM's own JSONL/bus during the ship-gate. Use the standard `tools/soak_driver.py --cli-pool-size 2` cassette path.

Per memory `feedback_soak_cli_pool_flag.md`: **always** pass `--cli-pool-size 2`. Default 0 silently reproduces the v1.0 cold-start regression.

Per memory `feedback_subagent_long_task_abandonment.md`: the ~32-min soak MUST run from the main session via `run_in_background` + `ScheduleWakeup`. NEVER delegate to a subagent.

## Task brief

This is the first ship-gate since v1.7 P2 where the fallback lever might actually fire: v1.9 P1 replaced the confidence-floor trigger with a verdict-based trigger (BLOCK/INTERVENE → Sonnet retry). P1 local soak smoke showed `cli_dispatch_fallback_ms` p95 > 0, confirming the mechanism works. P4 measures the actual lever effect under the full 32-min Tier-3 load mix.

Seven deliverables (mirror v1.8 P2).

### 1. Tier-3 ship-gate soak

```
python tools/soak_driver.py --cli-pool-size 2
```

Match the v1.8 ship-gate parameter set (32-min wall-clock, same seed, ~ALLOW n=49, L2/L3 n=7+, L4 n=4+, LM n=10) so v1.9 numbers diff cleanly against the v1.8 baseline.

Launch with `run_in_background=true` from the main session. Use `ScheduleWakeup` to poll for completion (~32 min wall-clock). Do NOT delegate to a subagent.

Report file: `reports/soak-<UTC-timestamp>Z.md`. Verify the report contains ALL THREE legacy breakout blocks (back-compat):
- `### ALLOW publish-path phase breakout (v1.4)`
- `### ALLOW _evaluate_inner sub-phase breakout (v1.5)`
- `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` (6 rows including `cli_dispatch_fallback_ms`)

**Critical lever check:** if `cli_dispatch_fallback_ms` p95 == 0.00 in this run despite P1 wiring, STOP and mint `phase-4a-fallback-still-dormant.md` BEFORE updating ADR-5. The ADR-5 v1.9 baseline must reflect a soak where the lever fires; if it does not fire here, the v1.7 lever falsification finding re-applies under the v1.9 mechanism. ADR-5 must not lie.

### 2. Alignment-eval gate

```
python tools/alignment_eval.py --ci-gate
```

Attach `reports/alignment-eval-<UTC>Z.md` to the PR. Ship-gate FAILS if exit is non-zero on FR-OG-7 rows (`model_floor == "sonnet"`). The verdict-based trigger only fires when `fallback_model_id is not None` (ambiguous-block / HITL-synthesis path); FR-OG-7 rows have `requires_alignment=True` and never reach Haiku-first routing, so regression should be impossible by construction.

### 3. ADR-5 v1.9 baseline

Append `## v1.9 ship-gate baseline` to `docs/adr/ADR-5-latency-budget.md`. Update the ADR header `Status:` line. Append-only — do NOT touch prior baseline sections.

Required subsections (mirror v1.8 baseline §):
- Source / Date / Ship SHA / Driver / Runtime / Events / Verdict
- Latency targets (overall, n=60)
- Per-band split
- ALLOW _evaluate_inner CLI residue breakout (6 rows; `cli_dispatch_fallback_ms` row must show non-zero p95 if lever fires)
- Fallback routing summary (v1.9 measurement): `governance_fallback_routed` envelope count; `cli_dispatch_fallback_ms` p95; per-band fallback rate (ambiguous-BLOCK vs HITL synthesis); trigger mode distribution (`"verdict"` vs `"confidence"`); Haiku verdict distribution on ambiguous-block events (BLOCK / INTERVENE / ALLOW / SUGGEST counts)
- Session watcher observation (v1.9 NEW): external sessions registered during soak (expected: 0 — no external sessions run during a standard soak); bg task tokens pending (expected: 0); confirm session watcher ran without error (check dashboard log for `session_watcher` ERROR lines)
- Alignment-eval result: Sonnet pass rate; Haiku pass rate; Haiku regressions vs Sonnet; FR-OG-7 row gate result
- Delta vs v1.8 ship-gate (`reports/soak-20260506T101746Z.md`): overall p50/p95/max/mean, ALLOW p95, L2/L3 p95, L4 alignment p95, LM p95, RSS drift, `cli_pool_send_ms` p95 (v1.8 baseline = 6470.35 ms), fallback fire rate (v1.8 = 0%)
- Budget (carry forward unless lever success justifies tightening)
- Status: ACCEPTED
- Caveats (per §4 below)

Update v1.8 §"Caveats" lever bullet — annotate disposition: "LEVER ACTIVATED in v1.9 (verdict-based trigger; see §'v1.9 ship-gate baseline' §Caveats for measured magnitude)" if fire rate > 0%; otherwise "lever remains dormant under production load; see §'v1.9 ship-gate baseline' §Caveats".

### 4. Lever-effect measurement — data-driven §"Caveats" findings

Document in §"Caveats". Data-driven only — do NOT predict:

- **Fallback fire rate.** Share of ambiguous-BLOCK / HITL-synthesis L4 events triggering Sonnet retry via verdict-based trigger. Report n + percent. Target: > 0% (proves trigger works AND the soak load mix contains content where Haiku returns BLOCK/INTERVENE).
- **Haiku verdict distribution.** On ambiguous-block routing events: how many BLOCK, INTERVENE, ALLOW, SUGGEST? This tells us how "decisive" Haiku is on destructive-command content under the soak seed.
- **`cli_pool_send_ms` p95 trend.** vs v1.8 baseline 6470.35 ms. Earned improvement only if fire rate > 0% AND p95 drops; v1.8's +26% regression was upstream variance (and v1.7's −19% drop also variance). Haiku TTFT on the retry path (Sonnet) should be longer than a direct Sonnet call by Haiku TTFT overhead — net effect on `cli_pool_send_ms` p95 depends on the fire rate.
- **ALLOW p95 trend.** vs v1.8 6.48 s. Non-ambiguous-block ALLOW events are unaffected by P1; any change is upstream variance.
- **L4 alignment p95 trend.** vs v1.8 11.85 s. FR-OG-7 cells still on Sonnet; should be unchanged.
- **Lever falsification re-check.** If fire rate > 0% AND `cli_pool_send_ms` p95 drops materially → lever effect confirmed for first time since v1.7 P2; document magnitude. If fire rate > 0% but p95 does NOT drop or increases → Haiku TTFT on these prompts is not faster than a direct Sonnet call; document and consider scope reduction for Haiku fastpath in v2.0. If fire rate == 0% → mint `phase-4a-fallback-still-dormant.md` BEFORE this step.
- **Session watcher neutrality.** Confirm that the session watcher background thread did not contribute to latency regression (ALLOW p95 is the clearest signal — should be ≤ 1 s delta from upstream variance). If ALLOW p95 regressed > 2 s vs v1.8 without upstream variance explanation: session watcher has a hot-path side effect; STOP and debug before tagging.

### 5. LM (categorize) p95 trend re-check

v1.8 LM p95 = 13.30 s (< 18 s ceiling; watch closed). v1.9 confirms stability or re-opens:
- **v1.9 LM p95 < 18 s** → watch stays closed; document in `## [1.9.0]` CHANGELOG.
- **v1.9 LM p95 ≥ 18 s AND magnitude > 1 s over ceiling** → re-open watch as v2.0 backlog item; mint `phase-4b-lm-regression-triage.md` if magnitude is large.

The v1.9 P3 Learn Mode source expansion only adds external sources when `learn_sources` is non-empty. The soak runs with default config (empty `learn_sources`), so P3 does not affect LM categorise latency in this soak.

### 6. CHANGELOG

Append `## [1.9.0]` section to `CHANGELOG.md`. Mirror v1.8.0 prose style. Cover:
- P1 verdict-based fallback trigger (PR #<m>)
- P2 external session registry + background task token registry (PR #<n>)
- P3 Learn Mode JSONL source expansion (PR #<p>)
- Ship-gate verdict (PASS / BLOCKED)
- Lever effect (`cli_pool_send_ms` p95 Δ vs v1.8, fallback fire rate, Haiku verdict distribution, alignment-eval)
- Session watcher neutrality confirmation
- LM trend re-check
- ADR-5 cross-link

### 7. Tag

Tag `v1.9.0` on the merge commit. Push tag to origin.

## Cross-PR seam audit (memory: `feedback_cross_pr_seam_review.md`)

Verify the full chain before merging:
- v1.8 P1 content-detection wiring (`governance._evaluate_inner_core` → `is_ambiguous_block=True` for destructive content → `route()` returns `fallback_model_id=haiku`)
- ↔ v1.7 P2 router (`RoutingDecision.fallback_model_id` passed to `CliGovernor.evaluate`)
- ↔ v1.9 P1 verdict trigger (`cli_governance._evaluate_once` checks `primary_verdict in {"BLOCK", "INTERVENE"}`)
- ↔ v1.9 P4 soak breakout (`cli_dispatch_fallback_ms` 6th row of v1.6 CLI residue block, now non-zero)
- ↔ ADR-5 v1.9 fallback routing summary table
- ↔ P2 session watcher (background thread; no coupling to governance hot path — verify by absence of `session_watcher` imports in governance/cli_governance path)
- ↔ P3 Learn Mode sources (ingest-only path; no coupling to verdict path — verify by absence of `learn_sources` config read in governance path)

Any seam mismatch (wiring fires but `governance_fallback_routed` count is 0, or count > 0 but `cli_dispatch_fallback_ms` = 0): STOP and patch BEFORE the v1.9.0 tag.

## DOD

- [ ] Tier-3 soak completed from main session, report at `reports/soak-<UTC>Z.md`
- [ ] All three ALLOW breakout blocks present; v1.6 CLI residue block has 6 rows; `cli_dispatch_fallback_ms` p95 > 0 (lever fires for first time)
- [ ] Alignment-eval `--ci-gate` run; report at `reports/alignment-eval-<UTC>Z.md`; FR-OG-7 row gate exits zero
- [ ] `docs/adr/ADR-5-latency-budget.md` has `## v1.9 ship-gate baseline` appended; ADR header `Status:` updated; v1.8 §"Caveats" lever bullet annotated; prior baseline sections untouched
- [ ] §"Caveats" documents: lever effect (data-driven), fallback fire rate, Haiku verdict distribution, session watcher neutrality, lever falsification re-check
- [ ] LM trend re-checked; decision recorded in §"Caveats" + CHANGELOG
- [ ] `## [1.9.0]` CHANGELOG section appended; covers P1 + P2 + P3 + ship-gate verdict
- [ ] Tag `v1.9.0` created on merge commit; pushed to origin
- [ ] No `src/` or `tools/` hunks in the finalize PR (verify with diff)

## Mint-new-phase rule

After each P4 sub-step, scan for follow-ups before ticking:
- **Soak done** → `cli_dispatch_fallback_ms` p95 == 0 despite P1 wiring (soak load mix did not produce Haiku BLOCK/INTERVENE on ambiguous-block content): mint `phase-4a-fallback-still-dormant.md` (BLOCKS ADR-5 update — falsification rule re-fires under v1.9 mechanism).
- **Soak done** → ALLOW p95 regressed > 2 s vs v1.8 6.48 s with no upstream variance explanation: investigate session watcher hot-path side effect; mint `phase-4c-session-watcher-regression.md`.
- **Alignment-eval done** → gate fires on FR-OG-7 rows: ABORT MERGE; debug routing precedence (`requires_alignment` → Sonnet only; if it fires on FR-OG-7 now, the v1.9 P1 trigger is misconfigured and reaching FR-OG-7 content).
- **Lever effect documented** → fire rate > 0% but `cli_pool_send_ms` p95 did NOT drop or increased: Haiku TTFT is not faster than Sonnet on ambiguous-block content — document and mint v2.0 backlog item (Haiku fastpath scope reduction or model selection change).
- **LM trend re-checked** → LM p95 ≥ 18 s + magnitude > 1 s: mint `phase-4b-lm-regression-triage.md`.
- **PR review** → blockers surface: mint `phase-4d-ship-pr-fixups.md`.
- **Tag step** → push fails or post-tag smoke breaks: mint `phase-4e-tag-recovery.md`.

Report back when v1.9.0 tag pushes with: tag SHA, ship PR URL, ship-gate verdict, lever Δ summary (`cli_pool_send_ms` p95 v1.8 → v1.9, fallback fire rate, Haiku verdict distribution, alignment-eval gate result), session watcher neutrality result, LM trend re-check.
