You are implementing **Phase P3 — v1.7 ship-gate + ADR-5 v1.7 baseline + LM watch resolution** from the streamManager v1.7 cycle.

## Branch + base

- Base: `main` with P2 (`feat/v1.7-haiku-fastpath-router`) merged.
- PR target: `main`.
- Branch: `ship/v1.7-shipgate-finalize` (or operator's choice).
- If P2 is not merged, ABORT — P3 ship-gate depends on the v1.7 Haiku fastpath router landing first.
- If P1 alignment-eval harness is not merged, ABORT (P2 cannot ship without it; cycle integrity broken).

## ⚠️ CRITICAL: Do-not-touch guard

P3 is **finalize only** — soak run, alignment-eval gate, report, ADR-5 re-baseline, CHANGELOG, tag. Do not modify engine code, soak driver report logic, or any v1.0–v1.6 protected symbols. Per memory `feedback_subagent_stale_mental_model.md`, diff PR head vs `main` on `src/` and `tools/` and confirm zero hunks before merging.

```
git --no-pager diff origin/main..HEAD -- src tools
```

Expect empty output (or trivial whitespace only). Any code hunks: STOP — finalize PR has accidentally absorbed P2 follow-up work.

Per memory `feedback_no_self_monitor.md`: do NOT run governance over the SM's own JSONL/bus during the ship-gate. Use the standard `tools/soak_driver.py --cli-pool-size 2` cassette path.

Per memory `feedback_soak_cli_pool_flag.md`: **always** pass `--cli-pool-size 2` to `tools/soak_driver.py`. Default 0 silently reproduces the v1.0 cold-start regression and invalidates the ship-gate.

Per memory `feedback_subagent_long_task_abandonment.md`: the 32-min soak MUST run from the main session via `run_in_background` + `ScheduleWakeup` polling. NEVER launch the soak from a subagent — subagents abandon long-running Bash tasks (>5 min) and the ship-gate report will not land.

## Task brief

Finalize v1.7. Five deliverables.

### 1. Ship-gate soak

Run a Tier-3 soak per ADR-17 with the v1.7 Haiku fastpath router enabled:

```
python tools/soak_driver.py --cli-pool-size 2 [other v1.6 ship-gate flags from reports/soak-20260505T073943Z.md]
```

Match the v1.6 ship-gate parameter set exactly (32-min wall-clock, ALLOW n=50, L2/L3 n=5, L4 n=5, LM n=10) so the v1.7 numbers diff cleanly against the v1.6 baseline.

Launch the soak with `run_in_background=true` from the main session. Use `ScheduleWakeup` to poll for completion (~32 min wall-clock). Do NOT delegate this run to a subagent.

Report file: `reports/soak-<UTC-timestamp>Z.md`. Verify the report contains ALL THREE blocks (the v1.6 CLI residue block now renders 6 rows including `cli_dispatch_fallback_ms`):
- `### ALLOW publish-path phase breakout (v1.4)` (back-compat)
- `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` (back-compat)
- `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` (back-compat — now 6 rows: `cli_setup_ms`, `cli_dispatch_ms`, `cli_pool_acquire_ms`, `cli_pool_send_ms`, `cli_parse_ms`, `cli_dispatch_fallback_ms`)

If the 6th row (`cli_dispatch_fallback_ms`) is missing, the soak driver did not pick up P2 instrumentation — STOP and audit P2 merge before proceeding.

### 2. Alignment-eval gate

Run `python tools/alignment_eval.py --ci-gate` against the merged v1.7 router config. Attach `reports/alignment-eval-<UTC>Z.md` to the ship-gate report references. Ship-gate FAILS if the alignment-eval gate is non-zero on FR-OG-7 rows (`model_floor == "sonnet"`).

If non-FR-OG-7 rows regress, document in §"Caveats" (do not block ship for non-protected-band regressions, but record the candidate pass rate explicitly).

### 3. ADR-5 v1.7 baseline

Append `## v1.7 ship-gate baseline` to `docs/adr/ADR-5-latency-budget.md`. Update the ADR header `Status:` line. Append-only — do NOT touch prior baseline sections.

Required subsections (mirror v1.6 baseline §):
- Source / Date / Ship SHA / Driver / Runtime / Events / Verdict
- Latency targets (overall, n=60)
- Per-band split
- ALLOW _evaluate_inner CLI residue breakout (now 6 rows)
- Fallback routing summary (v1.7 NEW): n / share of L4 calls firing fallback / per-band fallback rate (ambiguous-BLOCK vs HITL synthesis)
- Alignment-eval result: control vs candidate pass rate; FR-OG-7 row gate result; regressing-row list (if any)
- Delta vs v1.6 ship-gate (`reports/soak-20260505T073943Z.md`): overall p50/p95/max/mean, ALLOW p95, L2/L3 p95, L4 alignment p95, LM categorize p95, RSS drift
- Budget (carry forward unchanged from v1.6 unless the lever success justifies tightening)
- Status: ACCEPTED
- Caveats (per §4 below)

### 4. Driver lever effect — data-driven §"Caveats" findings

Document in §"Caveats". Data-driven only — do NOT predict:

- **`cli_pool_send_ms` p95 trend.** Did it drop vs v1.6 (6328.07 ms)? Compute Δ and classify (improvement / parity / regression). Note that more L4 envelopes riding Haiku is the intended lever — the metric should improve only if Haiku TTFT < Sonnet TTFT and fallback fire rate is low.
- **L4 alignment p95 trend.** Did the L4 band p95 drop vs v1.6 (13.98 s)? Report Δ. Caveat n=5 noise.
- **Fallback fire rate.** What share of L4 ambiguous-BLOCK / HITL synthesis rows triggered the Sonnet retry? Report n + percent. High fire rate (> 30%) means Haiku is mostly retrying — minimal latency win, possible quality loss; document and seed v1.8 as `phase-3a-fallback-floor-tuning.md` follow-up.
- **Alignment-eval result.** Per-row regression count on Haiku vs Sonnet; FR-OG-7 row gate result. If gate fired on FR-OG-7: SHIP BLOCKED — abort merge, abandon Haiku fastpath, rewrite as pool sizing per `docs/v1.7-task-plan.md` abandonment rule.
- **Lever falsification check.** If `cli_pool_send_ms` p95 did NOT drop and L4 p95 did NOT drop AND fallback fire rate is low: the Haiku fastpath did not move the needle. Record as falsification, re-open Haiku fastpath as a v1.8 watch item, and consider promoting 🟢 CLI pool sizing >2 (v1.7 backlog item 2) to primary in v1.8.

### 5. LM (categorize) p95 trend resolution

v1.6 §"Caveats" closed the LM watch as ship-with-v1.7-watch (18.60 s vs ceiling 18 s; +3.21 s vs v1.5). Resolve per v1.7 backlog rubric:

- **v1.7 LM p95 < 18 s** → watch closed; document the close in `## [1.7.0]` CHANGELOG section and ADR-5 v1.7 §"Caveats".
- **v1.7 LM p95 ≥ 18 s AND magnitude > 1 s over ceiling** → sustained regression. Mint `phase-3b-lm-regression-triage.md` (categorizer prompt audit; Sonnet upstream queueing investigation; cassette drift check). Add v1.8 backlog item if triage defers.
- **v1.7 LM p95 < 18 s but variance still wide (spread p50→p95 > 5 s)** → extend watch into v1.8 with sample-size bump (n>10). Add v1.8 backlog item.

### 6. CHANGELOG

Append `## [1.7.0]` section to `CHANGELOG.md`. Mirror v1.6.0 prose style (Highlights bullets + Notes). Cover:
- P1 alignment eval harness (PR #<m>)
- P2 Haiku fastpath router (PR #<n>) with confidence-gated Sonnet fallback
- Ship-gate verdict (PASS / BLOCKED)
- Lever effect (cli_pool_send_ms p95 Δ, L4 p95 Δ, fallback fire rate)
- LM watch resolution (close / triage / extend)
- ADR-5 cross-link

### 7. Tag

Tag `v1.7.0` on the merge commit. Push tag to origin.

## Cross-PR seam audit (memory: `feedback_cross_pr_seam_review.md`)

Verify the full chain before merging:
- P1 harness (`tools/alignment_eval.py`, `tests/golden/l4_alignment.jsonl`)
- ↔ P2 router writer (`model_router.RoutingDecision.fallback_model_id`, `cli_governance.CliGovernor.evaluate` retry)
- ↔ P2 governance writer (`_last_phase_timings_ms.cli_dispatch_fallback_ms`, `governance_fallback_routed` envelope)
- ↔ P3 reader (soak driver `### ALLOW _evaluate_inner CLI residue breakout (v1.6)` block — now 6 rows)
- ↔ ADR-5 v1.7 baseline table

Any seam mismatch (e.g. soak driver missing the 6th row, alignment-eval gate not running on PR CI): STOP and patch BEFORE the v1.7.0 tag.

## Subagent escape-hatch detection (memory: `feedback_subagent_escape_hatches.md`)

If any subagent return uses "deferred to a follow-up" phrasing, demand authorization or in-PR landing.

## DOD

- [ ] Tier-3 soak completed from main session, report at `reports/soak-<UTC>Z.md`
- [ ] All three ALLOW breakout blocks present; v1.6 CLI residue block has 6 rows including `cli_dispatch_fallback_ms`
- [ ] Alignment-eval `--ci-gate` run; report at `reports/alignment-eval-<UTC>Z.md`; FR-OG-7 row gate exits zero
- [ ] `docs/adr/ADR-5-latency-budget.md` has `## v1.7 ship-gate baseline` appended; ADR header `Status:` updated; prior baseline sections untouched
- [ ] §"Caveats" documents driver lever effect (data-driven), fallback fire rate, alignment-eval result, lever falsification check
- [ ] LM watch resolved per rubric (close / triage / extend); decision recorded in §"Caveats" and CHANGELOG
- [ ] `## [1.7.0]` CHANGELOG section appended
- [ ] Tag `v1.7.0` created on merge commit; pushed to origin
- [ ] No `src/` or `tools/` hunks in the finalize PR (verify with diff)
- [ ] Living checklist `docs/prompts/v1.7-shipgate-checklist.md` updated as phases close (mirror v1.6 S1–S12 pattern)

## Mint-new-phase rule

After each P3 sub-step completes, scan for follow-ups before ticking:
- **Soak done** → if residue rows missing/zero on CLI escalation OR `cli_dispatch_fallback_ms` zero everywhere despite fallback fire (envelope count > 0), mint `phase-3-residue-debug.md` (instrumentation bug, BLOCKS ADR-5 update).
- **Alignment-eval done** → if gate fires on FR-OG-7 rows: ABORT MERGE; mint `phase-3-abandon-haiku-fastpath.md` and rewrite P2 as pool sizing per `docs/v1.7-task-plan.md`.
- **Lever effect documented** → if `cli_pool_send_ms` p95 did NOT drop AND L4 p95 did NOT drop: mint v1.8 backlog item (Haiku fastpath falsification).
- **LM trend re-checked** → if LM p95 ≥ 18 s + magnitude > 1 s, mint `phase-3b-lm-regression-triage.md`.
- **PR review** → if blockers surface, mint `phase-3-ship-pr-fixups.md`.
- **Tag step** → if tag push fails or post-tag smoke breaks, mint `phase-3-tag-recovery.md`.

Report back when v1.7.0 tag pushes with: tag SHA, ship PR URL, ship-gate verdict, lever Δ summary (cli_pool_send_ms p95 v1.6 → v1.7, L4 p95 v1.6 → v1.7, fallback fire rate), alignment-eval gate result, LM watch resolution.
