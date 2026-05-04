You are implementing **Phase P2 — v1.5 ship-gate + ADR-5 v1.5 baseline + LM trend re-check** from the streamManager v1.5 cycle.

## Branch + base

- Base: `main` with P1 (`feat/v1.5-evaluate-inner-phase-timings`) merged.
- PR target: `main`.
- Branch: `ship/v1.5-shipgate-finalize` (or operator's choice).
- If P1 is not merged, ABORT — P2 ship-gate depends on the v1.5 sub-phase instrumentation landing first.

## ⚠️ CRITICAL: Do-not-touch guard

P2 is **finalize only** — soak run, report, ADR-5 re-baseline, CHANGELOG, tag. Do not modify engine code, soak driver report logic, or any v1.0–v1.4 protected symbols. Per memory `feedback_subagent_stale_mental_model.md`, diff PR head vs `main` on `src/` and `tools/` and confirm zero hunks before merging.

```
git --no-pager diff origin/main..HEAD -- src tools
```

Expect empty output (or trivial whitespace only). Any code hunks: STOP — finalize PR has accidentally absorbed P1 follow-up work.

Per memory `feedback_no_self_monitor.md`: do NOT run governance over the SM's own JSONL/bus during the ship-gate. Use the standard `tools/soak_driver.py --cli-pool-size 2` cassette path.

Per memory `feedback_soak_cli_pool_flag.md`: **always** pass `--cli-pool-size 2` to `tools/soak_driver.py`. Default 0 silently reproduces the v1.0 cold-start regression and invalidates the ship-gate.

## Task brief

Finalize v1.5. Three deliverables:

### 1. Ship-gate soak

Run a Tier-3 soak per ADR-17 with the v1.5 sub-phase instrumentation enabled:

```
python tools/soak_driver.py --cli-pool-size 2 [other v1.4 ship-gate flags from reports/soak-20260504T182027Z.md]
```

Match the v1.4 ship-gate parameter set exactly (32-min wall-clock, ALLOW n=50, L2/L3 n=5, L4 n=5, LM n=10) so the v1.5 numbers diff cleanly against the v1.4 baseline.

Report file: `reports/soak-<UTC-timestamp>Z.md`. Verify the report contains BOTH:
- `### ALLOW publish-path phase breakout (v1.4)` block (back-compat, unchanged columns)
- `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block (new, five rows: `og7_check`, `fast_precheck`, `graph_classify`, `hydrator_state_read`, `routing_dispatch`)

If either block is missing, the soak driver did not pick up P1 instrumentation — STOP and audit P1 merge before proceeding.

### 2. ADR-5 v1.5 baseline

Append a new section `## v1.5 ship-gate baseline` to `docs/adr/ADR-5-latency-budget.md` mirroring the v1.4 baseline section's structure:

- Soak source-of-truth report path
- Driver invocation line
- Measured table (overall p50 / p95 / max + per-band p50/p95)
- New `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` table reproduced from the report with the diagnosing finding paragraph
- Budget table (carry forward v1.4 budget unchanged unless a sub-phase finding justifies a change)
- §"Caveats" — at minimum:
  - The v1.4 `_evaluate_inner` opacity caveat is **resolved** by the new sub-phase breakout. Cite which sub-phase dominates the ALLOW p95 tail (data-driven, do not predict).
  - LM (categorize) p95 trend re-check (see deliverable 3).
- Update the ADR header `Status:` line to add `re-baselined v1.5 (<date>, see §"v1.5 ship-gate baseline")`.

Do NOT alter any prior baseline section. Append-only.

### 3. LM (categorize) p95 trend re-check

ADR-5 v1.4 §"Caveats" flagged LM p95 = 19.26 s vs v1.3.1 = 15.39 s (+3.87 s, n=10). v1.4 marked this as worth a re-measure if the next ship-gate also lands above 18 s.

In the v1.5 §"Caveats" block, document the v1.5 LM p95 number and:
- If ≤ 18 s: state the trend retreated; close the v1.4 watch item; no v1.6 follow-up needed.
- If > 18 s: state the trend persists; open a v1.6 backlog item in `docs/v1.6-backlog.md` (created in P0) titled "🟡 LM (categorize) p95 sustained-elevation investigation" referencing v1.3.1, v1.4, v1.5 measurements.

Do NOT speculate on cause — categorizer p95 is dominated by upstream Sonnet queueing and our local sample is n=10. Report the number, classify against the threshold, ship.

### 4. CHANGELOG + tag

- Append a `## [1.5.0] - <date>` section to `CHANGELOG.md` covering: v1.5 sub-phase instrumentation, ADR-5 v1.5 baseline, sub-phase finding (which component dominates the tail), LM trend disposition.
- After PR merges to `main`, tag `v1.5.0` on the merge commit.

## Cross-PR seam audit

Per memory `feedback_cross_pr_seam_review.md`: before merging this PR, audit the writer↔reader seam between P1 (engine emits new timing keys) and P2 (soak report consumes them) against the v1.5 task plan component table. Specifically verify:

- Engine writes ALL five v1.5 keys on every ALLOW evaluation
- `_ALLOW_PHASE_ORDER` lists ALL five v1.5 keys
- `_format_allow_phase_breakout` (v1.4) and the new `### ALLOW _evaluate_inner sub-phase breakout (v1.5)` block agree on the same source dict
- The soak report file emitted by the ship-gate run contains both blocks with non-zero `n` rows for at least the four sub-phases that fire on every ALLOW (`og7_check`, `fast_precheck`, `graph_classify`, `routing_dispatch`); `hydrator_state_read` may legitimately be n=0 if the hydrator path does not fire under the soak workload — note this in §"Caveats" if so.

Per memory `feedback_subagent_escape_hatches.md`: if any subagent return uses "deferred to a follow-up" phrasing, demand authorization or in-PR landing before accepting.

## DOD

- [ ] `reports/soak-<UTC-timestamp>Z.md` produced with `--cli-pool-size 2`, BOTH v1.4 and v1.5 phase-breakout blocks present
- [ ] `docs/adr/ADR-5-latency-budget.md` appended with `## v1.5 ship-gate baseline` section + §"Caveats" + header `Status:` line updated
- [ ] LM p95 trend re-check disposition recorded in §"Caveats"; v1.6 backlog item opened if and only if LM p95 > 18 s
- [ ] `CHANGELOG.md` `## [1.5.0]` section appended
- [ ] No code touched (`git --no-pager diff origin/main..HEAD -- src tools` empty)
- [ ] `pytest -q` passes (sanity — should be unchanged from P1 merge)
- [ ] PR merged to `main`
- [ ] `git tag v1.5.0 <merge-sha>` applied; tag pushed

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected files:
- `reports/soak-<UTC-timestamp>Z.md` (new)
- `docs/adr/ADR-5-latency-budget.md` (modified — append-only)
- `CHANGELOG.md` (modified — append-only)
- `docs/v1.6-backlog.md` (modified — append-only, ONLY if LM p95 > 18 s; otherwise unchanged)

If diff shows any change under `src/` or `tools/`, STOP — finalize PR has scope creep. Open a separate hotfix PR if a real defect was found.

Report back: PR URL, diff stat, ship-gate p95 numbers (overall + ALLOW + LM), sub-phase breakout finding (which component dominates the tail), LM trend disposition, tag SHA.
